"""Reader/writer for English Generation V retail Pokémon save files.

Supported games: Black, White, Black 2, and White 2.

The input is an unheadered 512 KiB (0x80000-byte) ``.sav``. Black/White use
0x24000-byte primary/backup save regions; Black 2/White 2 use 0x26000-byte
regions. The implementation verifies the mirrored CRC-16/CCITT checksums for
the party and box blocks it reads or modifies, extracts 24 PC boxes and the
party, and writes a separate ``.new`` output file.

Format references:
    https://projectpokemon.org/home/docs/gen-5/bw-save-structure-r60/
    https://projectpokemon.org/home/docs/gen-5/b2w2-save-structure-r72/
    https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/PKM/Util/PokeCrypto.cs
    https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/PKM/PK5.cs
    https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV5.cs

The implementation supports English/international save text most reliably.
It preserves original encrypted Pokémon records and does not synthesize new
Gen V records from edited high-level fields.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

try:
    from chempy.files import bytes_safe_write
except ModuleNotFoundError:
    def bytes_safe_write(*, path: str | os.PathLike[str], contents: bytes | bytearray) -> None:
        """Atomically write bytes, with a fallback when chempy is unavailable."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        with open(temporary, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)

from gen4 import crc16_ccitt, decode_gen4_text
from pokemon import Pokemon

SAVE_SIZE = 0x80000
PARTY_BLOCK_START = 0x18E00
PARTY_BLOCK_LENGTH = 0x534
PARTY_COUNT_OFFSET = 0x18E04
PARTY_RECORDS_OFFSET = 0x18E08
PARTY_CAPACITY = 6
PARTY_RECORD_SIZE = 220
BOX_COUNT = 24
BOX_CAPACITY = 30
BOX_RECORD_SIZE = 136
BOXES_START = 0x400
BOX_STRIDE = 0x1000
BOX_BLOCK_LENGTH = 0xFF0

PROFILES = {
    "black": {"family": "bw", "main_size": 0x24000, "info_length": 0x8C},
    "white": {"family": "bw", "main_size": 0x24000, "info_length": 0x8C},
    "black2": {"family": "b2w2", "main_size": 0x26000, "info_length": 0x94},
    "white2": {"family": "b2w2", "main_size": 0x26000, "info_length": 0x94},
}
GAME_ALIASES = {
    "b": "black", "black": "black",
    "w": "white", "white": "white",
    "b2": "black2", "black2": "black2", "black-2": "black2", "black 2": "black2",
    "w2": "white2", "white2": "white2", "white-2": "white2", "white 2": "white2",
}

# PokeCrypto.BlockPosition. Each row maps an encrypted/stored 32-byte block
# index to its logical block index. Indices 24-31 intentionally repeat 0-7.
BLOCK_POSITION = (
    (0, 1, 2, 3), (0, 1, 3, 2), (0, 2, 1, 3), (0, 3, 1, 2),
    (0, 2, 3, 1), (0, 3, 2, 1), (1, 0, 2, 3), (1, 0, 3, 2),
    (2, 0, 1, 3), (3, 0, 1, 2), (2, 0, 3, 1), (3, 0, 2, 1),
    (1, 2, 0, 3), (1, 3, 0, 2), (2, 1, 0, 3), (3, 1, 0, 2),
    (2, 3, 0, 1), (3, 2, 0, 1), (1, 2, 3, 0), (1, 3, 2, 0),
    (2, 1, 3, 0), (3, 1, 2, 0), (2, 3, 1, 0), (3, 2, 1, 0),
    (0, 1, 2, 3), (0, 1, 3, 2), (0, 2, 1, 3), (0, 3, 1, 2),
    (0, 2, 3, 1), (0, 3, 2, 1), (1, 0, 2, 3), (1, 0, 3, 2),
)


def _u16(data: bytes | bytearray, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


def _u32(data: bytes | bytearray, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    data[offset:offset + 2] = (int(value) & 0xFFFF).to_bytes(2, "little")


def _put_u32(data: bytearray, offset: int, value: int) -> None:
    data[offset:offset + 4] = (int(value) & 0xFFFFFFFF).to_bytes(4, "little")


def _lcg_xor(data: bytes | bytearray, seed: int) -> bytes:
    """XOR little-endian words using the Gen IV/V 32-bit LCRNG."""
    output = bytearray(data)
    state = seed & 0xFFFFFFFF
    for offset in range(0, len(output) - 1, 2):
        state = (0x41C64E6D * state + 0x6073) & 0xFFFFFFFF
        word = _u16(output, offset) ^ (state >> 16)
        output[offset:offset + 2] = word.to_bytes(2, "little")
    return bytes(output)


def decrypt_gen5_record(record: bytes) -> tuple[bytes, int, int, bytes]:
    """Return plaintext 128-byte payload, PID, checksum, and plaintext party stats.

    A valid Gen V record is 136 bytes in a box or 220 bytes in the party. A
    non-zero record with a bad checksum raises ValueError rather than being
    silently skipped, because a skipped Pokémon could otherwise be deleted.
    """
    if len(record) not in (BOX_RECORD_SIZE, PARTY_RECORD_SIZE):
        raise ValueError(f"Expected 136- or 220-byte Gen V record, got {len(record)}")
    pid = _u32(record, 0)
    checksum = _u16(record, 6)
    if not any(record):
        return bytes(128), pid, checksum, bytes(max(0, len(record) - BOX_RECORD_SIZE))

    encrypted_payload = _lcg_xor(record[8:BOX_RECORD_SIZE], checksum)
    shuffle_index = (pid >> 13) & 31
    logical_payload = bytearray(128)
    row = BLOCK_POSITION[shuffle_index]
    for stored_index, logical_index in enumerate(row):
        logical_payload[logical_index * 32:(logical_index + 1) * 32] = encrypted_payload[
            stored_index * 32:(stored_index + 1) * 32
        ]

    calculated_checksum = sum(_u16(logical_payload, off) for off in range(0, 128, 2)) & 0xFFFF
    if calculated_checksum != checksum:
        raise ValueError(
            f"Generation V Pokémon checksum mismatch (PID 0x{pid:08X}; "
            f"stored 0x{checksum:04X}, calculated 0x{calculated_checksum:04X})"
        )

    party_stats = _lcg_xor(record[BOX_RECORD_SIZE:], pid) if len(record) > BOX_RECORD_SIZE else b""
    return bytes(logical_payload), pid, checksum, party_stats


def _record_present(record: bytes) -> bool:
    if not any(record):
        return False
    logical, _pid, _checksum, _stats = decrypt_gen5_record(record)
    return _u16(logical, 0) != 0


def _parse_pokemon(
    record: bytes,
    *,
    game_name: str,
    party: bool,
    party_slot: int | None = None,
    box_index: int | None = None,
    box_slot: int | None = None,
) -> Pokemon:
    logical, pid, checksum, stats = decrypt_gen5_record(record)
    species = _u16(logical, 0)
    if species == 0:
        raise ValueError("Cannot parse an empty Generation V Pokémon record")

    held_item = _u16(logical, 2)
    original_trainer = _u32(logical, 4)  # low 16 bits TID, high 16 bits SID
    exp = _u32(logical, 8)
    friendship = logical[0x0C]
    ability = logical[0x0D]
    language = logical[0x0F]
    hp_ev, attack_ev, defense_ev, speed_ev, sp_attack_ev, sp_defense_ev = logical[0x10:0x16]
    moves = [_u16(logical, 0x20 + i * 2) for i in range(4)]
    move_pp = list(logical[0x28:0x2C])
    iv_word = _u32(logical, 0x30)
    nickname = decode_gen4_text(logical[0x40:0x56])
    game_of_origin = logical[0x57]
    ot_name = decode_gen4_text(logical[0x60:0x70])
    egg_date = int.from_bytes(logical[0x70:0x73], "little")
    met_date = int.from_bytes(logical[0x73:0x76], "little")
    egg_location = _u16(logical, 0x76)
    met_location = _u16(logical, 0x78)
    pokerus = logical[0x7A]
    pokeball = logical[0x7B]
    met_level_gender = logical[0x7C]
    met_level = met_level_gender & 0x7F
    original_trainer_gender = (met_level_gender >> 7) & 1

    # Gen V does not have an in-record encounter-type field matching later
    # generations; byte 0x7D is ground-tile data and is deliberately not mapped.
    level = None  # populated from the party-stat payload for party records
    status = current_hp = max_hp = attack = defense = speed = sp_attack = sp_defense = None
    if party:
        if len(stats) < 20:
            raise ValueError("Party record is missing its battle-stat payload")
        status = _u32(stats, 0)
        level = stats[4]
        current_hp = _u16(stats, 6)
        max_hp = _u16(stats, 8)
        attack = _u16(stats, 10)
        defense = _u16(stats, 12)
        speed = _u16(stats, 14)
        sp_attack = _u16(stats, 16)
        sp_defense = _u16(stats, 18)
    else:
        # A boxed PK5 does not contain calculated party battle stats or level.
        # Keep them NULL in SQLite rather than implying that the Pokémon is level 0.
        level = None
        status = current_hp = max_hp = attack = defense = speed = sp_attack = sp_defense = None

    is_egg = bool(iv_word & (1 << 30))
    is_nicknamed = bool(iv_word & (1 << 31))
    is_shiny = (
        ((original_trainer & 0xFFFF) ^ (original_trainer >> 16) ^ (pid & 0xFFFF) ^ (pid >> 16)) < 8
    )

    pokemon = Pokemon(
        generation=5,
        name=nickname,
        species=species,
        held_item=held_item,
        move1=moves[0], move2=moves[1], move3=moves[2], move4=moves[3],
        original_trainer=original_trainer,
        original_trainer_name=ot_name,
        exp=exp,
        hp_ev=hp_ev, attack_ev=attack_ev, defense_ev=defense_ev, speed_ev=speed_ev,
        special_ev=sp_attack_ev + sp_defense_ev,
        special_attack_ev=sp_attack_ev, special_defense_ev=sp_defense_ev,
        iv=iv_word & 0x3FFFFFFF,
        move1_pp=move_pp[0], move2_pp=move_pp[1], move3_pp=move_pp[2], move4_pp=move_pp[3],
        friendship=friendship, pokerus=pokerus, caught=met_location, level=level,
        status_condition=status, current_hp=current_hp, max_hp=max_hp,
        attack=attack, defense=defense, speed=speed,
        special_attack=sp_attack, special_defense=sp_defense,
        game_of_origin=game_of_origin, met_location=met_location,
        egg_location=egg_location, met_level=met_level, pokeball=pokeball,
        encounter_type=None, egg_date=egg_date, met_date=met_date,
        original_trainer_gender=original_trainer_gender,
    )
    pokemon.game_name = game_name
    pokemon.personality = pid
    pokemon.ability = ability
    pokemon.language = language
    # Gender depends on both species gender ratio and PID in Gen V. Preserve it
    # as unknown here rather than incorrectly guessing it from a flag byte.
    pokemon.gender = None
    pokemon.nature = pid % 25
    pokemon.is_egg = int(is_egg)
    pokemon.is_nicknamed = int(is_nicknamed)
    pokemon.is_shiny = int(is_shiny)
    pokemon.gen5_checksum = checksum
    pokemon.gen5_box_record = bytes(record[:BOX_RECORD_SIZE])
    pokemon.gen5_party_record = bytes(record) if party else None
    pokemon.gen5_party_slot = party_slot
    pokemon.gen5_box_index = box_index
    pokemon.gen5_box_slot = box_slot
    return pokemon


def _box_block_start(box_index: int) -> int:
    if not 0 <= box_index < BOX_COUNT:
        raise ValueError(f"Invalid PC box index: {box_index}")
    return BOXES_START + box_index * BOX_STRIDE


class Gen5_Save:
    """Read, extract, and write Black/White/Black 2/White 2 saves.

    The constructor requires the game because Black/White and Black 2/White 2
    use different save-copy sizes and footer checksum locations.
    """
    generation = 5

    def __init__(self, path: str | os.PathLike[str] | None = None, *, game: str = "black"):
        self.path = os.fspath(path) if path is not None else "./gen5-save.sav"
        normalized = str(game).strip().lower().replace("_", "-")
        if normalized not in GAME_ALIASES:
            raise ValueError("Choose black, white, black2, or white2")
        self.game_name = GAME_ALIASES[normalized]
        self.game = self.game_name
        self.profile = PROFILES[self.game]
        self.save_bytes = bytearray()
        self.party_pokemon: list[Pokemon] = []
        self.box_pokemon: list[list[Pokemon]] = [[] for _ in range(BOX_COUNT)]
        self.valid_copy_bases: list[int] = []
        self.active_copy_base: int | None = None
        if path is not None:
            self.read_save()

    @property
    def main_size(self) -> int:
        return self.profile["main_size"]

    @property
    def info_length(self) -> int:
        return self.profile["info_length"]

    @property
    def footer_offset(self) -> int:
        return self.main_size - 0x100

    def _footer_valid(self, data: bytes | bytearray, base: int) -> bool:
        start = base + self.footer_offset
        footer_info = data[start:start + self.info_length]
        if len(footer_info) != self.info_length:
            return False
        stored = _u16(data, start + self.info_length + 0x0E)
        return stored == crc16_ccitt(footer_info)

    def _block_checksum_valid(self, data: bytes | bytearray, base: int,
                              block_start: int, block_length: int,
                              checksum_offset: int, mirror_id: int) -> bool:
        start = base + block_start
        checksum = crc16_ccitt(data[start:start + block_length])
        stored = _u16(data, base + checksum_offset)
        mirror = _u16(data, base + self.footer_offset + mirror_id * 2)
        return stored == checksum and mirror == stored

    def _copy_valid(self, data: bytes | bytearray, base: int) -> bool:
        if not self._footer_valid(data, base):
            return False
        # Check all 24 box checksums and the party block before allowing the
        # save to be modified. A bad source block must not be silently erased.
        for box_index in range(BOX_COUNT):
            start = _box_block_start(box_index)
            if not self._block_checksum_valid(
                data, base, start, BOX_BLOCK_LENGTH,
                start + BOX_BLOCK_LENGTH + 2, box_index + 1,
            ):
                return False
        if not self._block_checksum_valid(
            data, base, PARTY_BLOCK_START, PARTY_BLOCK_LENGTH,
            PARTY_BLOCK_START + PARTY_BLOCK_LENGTH + 2, 26,
        ):
            return False
        return True

    def read_save(self) -> None:
        try:
            raw = Path(self.path).read_bytes()
        except OSError as exc:
            raise OSError(f"Could not read save file {self.path!r}: {exc}") from exc
        if len(raw) != SAVE_SIZE:
            raise ValueError(f"Expected a 512 KiB Generation V save ({SAVE_SIZE} bytes), got {len(raw)}")
        self.save_bytes = bytearray(raw)
        candidates = [base for base in (0, self.main_size) if self._copy_valid(self.save_bytes, base)]
        if not candidates:
            raise ValueError(
                f"No valid Generation V save copy found for {self.game_name}. "
                "Check the game selection and ensure this is an unheadered 512 KiB save."
            )
        # Retail files normally contain both copies. Prefer the primary when
        # it is fully valid, and fall back to backup only when needed.
        self.valid_copy_bases = candidates
        self.active_copy_base = candidates[0]
        self._extract_party()
        self._extract_boxes()

    def _extract_party(self) -> None:
        assert self.active_copy_base is not None
        base = self.active_copy_base
        count = _u32(self.save_bytes, base + PARTY_COUNT_OFFSET)
        if count > PARTY_CAPACITY:
            raise ValueError(f"Invalid Gen V party count {count} (maximum {PARTY_CAPACITY})")
        party = []
        for slot in range(count):
            start = base + PARTY_RECORDS_OFFSET + slot * PARTY_RECORD_SIZE
            record = bytes(self.save_bytes[start:start + PARTY_RECORD_SIZE])
            if not _record_present(record):
                raise ValueError(f"Party slot {slot} is empty or corrupt despite party count {count}")
            party.append(_parse_pokemon(record, game_name=self.game_name, party=True, party_slot=slot))
        self.party_pokemon = party

    def _extract_boxes(self) -> None:
        assert self.active_copy_base is not None
        base = self.active_copy_base
        all_boxes: list[list[Pokemon]] = []
        for box_index in range(BOX_COUNT):
            start = base + _box_block_start(box_index)
            box_data = self.save_bytes[start:start + BOX_BLOCK_LENGTH]
            records = []
            for slot in range(BOX_CAPACITY):
                record = bytes(box_data[slot * BOX_RECORD_SIZE:(slot + 1) * BOX_RECORD_SIZE])
                if not any(record):
                    continue
                if not _record_present(record):
                    raise ValueError(
                        f"PC box {box_index + 1}, slot {slot + 1} contains a non-empty invalid Pokémon record"
                    )
                records.append(_parse_pokemon(
                    record, game_name=self.game_name, party=False,
                    box_index=box_index, box_slot=slot,
                ))
            all_boxes.append(records)
        self.box_pokemon = all_boxes

    def print_all_pokemon(self) -> None:
        for index, pokemon in enumerate(self.party_pokemon, 1):
            print(f"Party {index}: {pokemon.name} (species {pokemon.species})")
        for box_index, box in enumerate(self.box_pokemon, 1):
            for pokemon in box:
                print(f"Box {box_index}, slot {getattr(pokemon, 'gen5_box_slot', -1) + 1}: "
                      f"{pokemon.name} (species {pokemon.species})")

    def _set_block_checksum(self, data: bytearray, base: int, block_start: int,
                            block_length: int, checksum_offset: int, mirror_id: int) -> None:
        checksum = crc16_ccitt(data[base + block_start:base + block_start + block_length])
        _put_u16(data, base + checksum_offset, checksum)
        _put_u16(data, base + self.footer_offset + mirror_id * 2, checksum)

    def _make_output(self) -> bytes:
        if not self.save_bytes or self.active_copy_base is None:
            raise ValueError("Read a valid Generation V save before writing")
        if not self.valid_copy_bases:
            raise ValueError("No validated Generation V save copies available to update")
        if len(self.party_pokemon) > PARTY_CAPACITY:
            raise ValueError(f"Party exceeds {PARTY_CAPACITY} Pokémon")
        if len(self.box_pokemon) != BOX_COUNT:
            raise ValueError(f"Expected {BOX_COUNT} PC boxes, got {len(self.box_pokemon)}")

        output = bytearray(self.save_bytes)
        for base in self.valid_copy_bases:
            # Rebuild the party block without changing its fixed outer layout.
            _put_u32(output, base + PARTY_COUNT_OFFSET, len(self.party_pokemon))
            party_start = base + PARTY_RECORDS_OFFSET
            output[party_start:party_start + PARTY_CAPACITY * PARTY_RECORD_SIZE] = bytes(
                PARTY_CAPACITY * PARTY_RECORD_SIZE
            )
            for slot, pokemon in enumerate(self.party_pokemon):
                record = getattr(pokemon, "gen5_party_record", None)
                if record is None or len(record) != PARTY_RECORD_SIZE:
                    box_record = getattr(pokemon, "gen5_box_record", None)
                    if box_record is None or len(box_record) != BOX_RECORD_SIZE:
                        raise ValueError(f"No retained Gen V record available for {pokemon.name!r}")
                    record = bytes(box_record) + bytes(PARTY_RECORD_SIZE - BOX_RECORD_SIZE)
                start = party_start + slot * PARTY_RECORD_SIZE
                output[start:start + PARTY_RECORD_SIZE] = record
            self._set_block_checksum(
                output, base, PARTY_BLOCK_START, PARTY_BLOCK_LENGTH,
                PARTY_BLOCK_START + PARTY_BLOCK_LENGTH + 2, 26,
            )

            for box_index, box in enumerate(self.box_pokemon):
                if len(box) > BOX_CAPACITY:
                    raise ValueError(f"PC box {box_index + 1} exceeds {BOX_CAPACITY} Pokémon")
                block_start = _box_block_start(box_index)
                block_abs = base + block_start
                output[block_abs:block_abs + BOX_BLOCK_LENGTH] = bytes(BOX_BLOCK_LENGTH)
                used_slots: set[int] = set()
                for pokemon in box:
                    original_box = getattr(pokemon, "gen5_box_index", None)
                    original_slot = getattr(pokemon, "gen5_box_slot", None)
                    if (original_box == box_index and isinstance(original_slot, int)
                            and 0 <= original_slot < BOX_CAPACITY and original_slot not in used_slots):
                        slot = original_slot
                    else:
                        slot = next((i for i in range(BOX_CAPACITY) if i not in used_slots), -1)
                    if slot < 0:
                        raise ValueError(f"PC box {box_index + 1} has no free slot")
                    record = getattr(pokemon, "gen5_box_record", None)
                    if record is None or len(record) != BOX_RECORD_SIZE:
                        party_record = getattr(pokemon, "gen5_party_record", None)
                        if party_record is not None and len(party_record) >= BOX_RECORD_SIZE:
                            record = party_record[:BOX_RECORD_SIZE]
                    if record is None or len(record) != BOX_RECORD_SIZE:
                        raise ValueError(f"No retained Gen V record available for {pokemon.name!r}")
                    output[block_abs + slot * BOX_RECORD_SIZE:block_abs + (slot + 1) * BOX_RECORD_SIZE] = record
                    used_slots.add(slot)
                self._set_block_checksum(
                    output, base, block_start, BOX_BLOCK_LENGTH,
                    block_start + BOX_BLOCK_LENGTH + 2, box_index + 1,
                )

            # Recompute the checksum for the mirror table/footer after all local
            # block-checksum values and their mirror values have been updated.
            footer_start = base + self.footer_offset
            footer_crc = crc16_ccitt(output[footer_start:footer_start + self.info_length])
            _put_u16(output, footer_start + self.info_length + 0x0E, footer_crc)

            if not self._footer_valid(output, base):
                raise ValueError(f"Updated Gen V footer at 0x{footer_start:X} failed validation")
            if not self._copy_valid(output, base):
                raise ValueError(f"Updated Gen V save copy at 0x{base:X} failed validation")

        if len(output) != SAVE_SIZE:
            raise AssertionError("Output size changed unexpectedly")
        return bytes(output)

    def write_save(self) -> str:
        """Write a separate ``<input>.new`` file; never overwrite the input."""
        output = self._make_output()
        output_path = f"{self.path}.new"
        bytes_safe_write(path=output_path, contents=output)
        return output_path


Generation5Save = Gen5_Save
