"""Reader/writer for decrypted Generation VI Pokémon save files.

Supported games: X, Y, Omega Ruby, and Alpha Sapphire.

This module intentionally accepts PKHeX-compatible decrypted save buffers only:
  * X/Y: 0x65600 bytes
  * Omega Ruby/Alpha Sapphire: 0x76000 bytes

These are *not* the encrypted 1 MiB DISA/IVFC cartridge container. The outer
3DS save container uses console-specific authentication/encryption and must be
exported/imported by a save manager that handles those integrity layers.

The handler validates the footer marker and the checksums for the party and PC
box blocks, decrypts PK6 records for SQLite parsing, and preserves original
record bytes when Pokémon remain in their original locations. The extraction
workflow uses it to clear party and PC records only after the SQLite transaction
has committed.

Format references:
  https://projectpokemon.org/docs/gen-6/xy-save-structure-r82/
  https://projectpokemon.org/docs/gen-6/oras-save-structure-r80/
  https://projectpokemon.org/docs/gen-6/pkm-structure-xy-r66/
  https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV6.cs
  https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/Access/SaveBlockAccessor6XY.cs
  https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/Access/SaveBlockAccessor6AO.cs
  https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/PKM/Util/PokeCrypto.cs
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from chempy.files import bytes_safe_write
except ModuleNotFoundError:
    def bytes_safe_write(*, path: str | os.PathLike[str], contents: bytes | bytearray) -> None:
        """Atomically write bytes when the optional project helper is absent."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        with open(temporary, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)

from gen4 import crc16_ccitt
from pokemon import Pokemon

XY_SAVE_SIZE = 0x65600
ORAS_SAVE_SIZE = 0x76000
PARTY_OFFSET = 0x14200
PARTY_CAPACITY = 6
PARTY_RECORD_SIZE = 0x104       # 260 bytes (PK6 plus party statistics)
BOX_COUNT = 31
BOX_CAPACITY = 30
BOX_RECORD_SIZE = 0xE8          # 232 bytes (PK6 stored format)
PARTY_BLOCK_LENGTH = 0x61C
BOX_BLOCK_LENGTH = BOX_COUNT * BOX_CAPACITY * BOX_RECORD_SIZE  # 0x34AD0
BLOCK_INFO_HEADER_LENGTH = 0x14
FOOTER_SIZE = 0x200
BEEF_MAGIC = 0x42454546         # little-endian bytes b"FEEB"

PROFILES = {
    "x": {"family": "xy", "size": XY_SAVE_SIZE, "box_offset": 0x22600,
          "box_block_id": 0x35, "version_id": 24},
    "y": {"family": "xy", "size": XY_SAVE_SIZE, "box_offset": 0x22600,
          "box_block_id": 0x35, "version_id": 25},
    "omegaruby": {"family": "oras", "size": ORAS_SAVE_SIZE, "box_offset": 0x33000,
                  "box_block_id": 0x38, "version_id": 26},
    "alphasapphire": {"family": "oras", "size": ORAS_SAVE_SIZE, "box_offset": 0x33000,
                      "box_block_id": 0x38, "version_id": 27},
}
GAME_ALIASES = {
    "x": "x", "pokemon x": "x", "pokémon x": "x",
    "y": "y", "pokemon y": "y", "pokémon y": "y",
    "or": "omegaruby", "omega-ruby": "omegaruby", "omega ruby": "omegaruby",
    "omegaruby": "omegaruby", "omega ruby": "omegaruby",
    "as": "alphasapphire", "alpha-sapphire": "alphasapphire",
    "alpha sapphire": "alphasapphire", "alphasapphire": "alphasapphire",
}

# Same four-block permutation table used by PKHeX's PokeCrypto.Shuffle67.
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
BLOCK_POSITION_INVERT = (
    0, 1, 2, 4, 3, 5, 6, 7, 12, 18, 13, 19, 8, 10, 14, 20,
    16, 22, 9, 11, 15, 21, 17, 23, 0, 1, 2, 4, 3, 5, 6, 7,
)


def _u16(data: bytes | bytearray, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


def _u32(data: bytes | bytearray, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    data[offset:offset + 2] = (int(value) & 0xFFFF).to_bytes(2, "little")


def _put_u32(data: bytearray, offset: int, value: int) -> None:
    data[offset:offset + 4] = (int(value) & 0xFFFFFFFF).to_bytes(4, "little")


def _crypt_array(data: bytearray, seed: int) -> None:
    """XOR 16-bit words using the Gen VI LCRNG seeded by the EC."""
    state = seed & 0xFFFFFFFF
    for offset in range(0, len(data) - 1, 2):
        state = (0x41C64E6D * state + 0x6073) & 0xFFFFFFFF
        word = _u16(data, offset) ^ (state >> 16)
        data[offset:offset + 2] = (word & 0xFFFF).to_bytes(2, "little")


def _shuffle_blocks(data: bytearray, shuffle_index: int) -> None:
    """Apply PKHeX-compatible in-place 4 x 56-byte substructure shuffling."""
    row = BLOCK_POSITION[shuffle_index & 31]
    perm = [0, 1, 2, 3]
    slot_of = [0, 1, 2, 3]
    block_size = 0x38
    for i in range(3):
        desired = row[i]
        j = slot_of[desired]
        if j == i:
            continue
        a = i * block_size
        b = j * block_size
        temp = data[a:a + block_size]
        data[a:a + block_size] = data[b:b + block_size]
        data[b:b + block_size] = temp
        block_at_i = perm[i]
        perm[j] = block_at_i
        slot_of[block_at_i] = j


def decrypt_gen6_record(record: bytes) -> bytes:
    """Decrypt one 232-byte PK6 or 260-byte party PK6 record and verify it.

    The 8-byte header (encryption constant, sanity, checksum) is unencrypted.
    The stored payload is XOR-encrypted with the encryption constant and has
    four 56-byte blocks shuffled according to bits 13-17 of that constant.
    The party-stat suffix is separately XOR-encrypted with the same constant.
    """
    if len(record) not in (BOX_RECORD_SIZE, PARTY_RECORD_SIZE):
        raise ValueError(
            f"Expected a 232- or 260-byte Generation VI record, got {len(record)}"
        )
    if not any(record):
        return bytes(len(record))

    ec = _u32(record, 0)
    expected_checksum = _u16(record, 6)
    logical = bytearray(record)
    payload = logical[8:BOX_RECORD_SIZE]
    _crypt_array(payload, ec)
    _shuffle_blocks(payload, (ec >> 13) & 31)
    logical[8:BOX_RECORD_SIZE] = payload

    if len(record) > BOX_RECORD_SIZE:
        party_stats = logical[BOX_RECORD_SIZE:]
        _crypt_array(party_stats, ec)
        logical[BOX_RECORD_SIZE:] = party_stats

    calculated_checksum = sum(
        _u16(logical, offset) for offset in range(8, BOX_RECORD_SIZE, 2)
    ) & 0xFFFF
    if calculated_checksum != expected_checksum:
        raise ValueError(
            "Generation VI Pokémon checksum mismatch "
            f"(EC 0x{ec:08X}; stored 0x{expected_checksum:04X}, "
            f"calculated 0x{calculated_checksum:04X})"
        )
    return bytes(logical)


def _decode_gen6_text(data: bytes) -> str:
    """Decode a Generation VI UTF-16LE field through its first NUL terminator."""
    if len(data) % 2:
        data = data[:-1]
    text = data.decode("utf-16-le", errors="replace")
    return text.split("\x00", 1)[0].rstrip("\uffff ")


def _record_present(record: bytes) -> bool:
    if not any(record):
        return False
    logical = decrypt_gen6_record(record)
    species = _u16(logical, 8)
    return species != 0


def _parse_pokemon(
    record: bytes,
    *,
    game_name: str,
    party: bool,
    party_slot: int | None = None,
    box_index: int | None = None,
    box_slot: int | None = None,
) -> Pokemon | None:
    logical = decrypt_gen6_record(record)
    species = _u16(logical, 8)
    if species == 0:
        return None

    held_item = _u16(logical, 0x0A)
    original_trainer = _u32(logical, 0x0C)  # TID16 | SID16
    exp = _u32(logical, 0x10)
    ability = logical[0x14]
    pid = _u32(logical, 0x18)
    nature = logical[0x1C]
    gender = (logical[0x1D] >> 1) & 0x03
    hp_ev, attack_ev, defense_ev, speed_ev, sp_attack_ev, sp_defense_ev = logical[0x1E:0x24]
    pokerus = logical[0x2B]
    nickname = _decode_gen6_text(logical[0x40:0x5A])
    moves = [_u16(logical, 0x5A + 2 * index) for index in range(4)]
    move_pp = list(logical[0x62:0x66])
    iv_word = _u32(logical, 0x74)
    ot_name = _decode_gen6_text(logical[0xB0:0xCA])
    original_trainer_gender = (logical[0xDD] >> 7) & 1
    met_level = logical[0xDD] & 0x7F
    egg_date = int.from_bytes(logical[0xD1:0xD4], "little")
    met_date = int.from_bytes(logical[0xD4:0xD7], "little")
    egg_location = _u16(logical, 0xD8)
    met_location = _u16(logical, 0xDA)
    pokeball = logical[0xDC]
    game_of_origin = logical[0xDF]
    language = logical[0xE3]

    # Gen VI shiny value uses a 4-bit threshold (16 values), unlike earlier gens.
    tid = original_trainer & 0xFFFF
    sid = (original_trainer >> 16) & 0xFFFF
    shiny_value = ((pid & 0xFFFF) ^ (pid >> 16) ^ tid ^ sid)
    is_shiny = shiny_value < 16

    level = status = current_hp = max_hp = attack = defense = speed = sp_attack = sp_defense = None
    if party:
        status = _u32(logical, 0xE8)
        level = logical[0xEC]
        current_hp = _u16(logical, 0xF0)
        max_hp = _u16(logical, 0xF2)
        attack = _u16(logical, 0xF4)
        defense = _u16(logical, 0xF6)
        speed = _u16(logical, 0xF8)
        sp_attack = _u16(logical, 0xFA)
        sp_defense = _u16(logical, 0xFC)

    pokemon = Pokemon(
        generation=6,
        name=nickname,
        species=species,
        held_item=held_item,
        move1=moves[0], move2=moves[1], move3=moves[2], move4=moves[3],
        original_trainer=original_trainer,
        original_trainer_name=ot_name,
        exp=exp,
        hp_ev=hp_ev, attack_ev=attack_ev, defense_ev=defense_ev,
        speed_ev=speed_ev,
        special_ev=sp_attack_ev + sp_defense_ev,
        special_attack_ev=sp_attack_ev, special_defense_ev=sp_defense_ev,
        iv=iv_word & 0x3FFFFFFF,
        move1_pp=move_pp[0], move2_pp=move_pp[1],
        move3_pp=move_pp[2], move4_pp=move_pp[3],
        friendship=logical[0xCA], pokerus=pokerus,
        caught=met_location, level=level,
        status_condition=status, current_hp=current_hp, max_hp=max_hp,
        attack=attack, defense=defense, speed=speed,
        special_attack=sp_attack, special_defense=sp_defense,
        game_of_origin=game_of_origin,
        met_location=met_location, egg_location=egg_location,
        met_level=met_level, pokeball=pokeball, encounter_type=None,
        egg_date=egg_date, met_date=met_date,
        original_trainer_gender=original_trainer_gender,
    )
    pokemon.game_name = game_name
    pokemon.personality = pid
    pokemon.ability = ability
    pokemon.language = language
    pokemon.gender = gender
    pokemon.nature = nature
    pokemon.is_egg = int(bool(iv_word & (1 << 30)))
    pokemon.is_nicknamed = int(bool(iv_word & (1 << 31)))
    pokemon.is_shiny = int(is_shiny)
    pokemon.gen6_record = bytes(record)
    pokemon.gen6_party_slot = party_slot
    pokemon.gen6_box_index = box_index
    pokemon.gen6_box_slot = box_slot
    return pokemon


class Gen6_Save:
    """Read and clear party/PC records from decrypted Gen VI saves.

    ``game`` is required to distinguish X/Y and Omega Ruby/Alpha Sapphire,
    which share their family save layout. This class intentionally supports
    extraction/clearing of existing Pokémon records, not constructing new PK6s
    from high-level fields or re-encoding edited Pokémon attributes.
    """
    generation = 6

    def __init__(self, path: str | os.PathLike[str] | None = None, *, game: str = "x"):
        self.path = os.fspath(path) if path is not None else "./gen6-save.main"
        normalized = str(game).strip().lower().replace("_", "-")
        if normalized not in GAME_ALIASES:
            raise ValueError("Choose x, y, omegaruby, or alphasapphire")
        self.game_name = GAME_ALIASES[normalized]
        self.game = self.game_name
        self.profile = PROFILES[self.game]
        self.save_bytes = bytearray()
        self.party_pokemon: list[Pokemon] = []
        self.box_pokemon: list[list[Pokemon]] = [[] for _ in range(BOX_COUNT)]
        self._original_party_records: list[bytes] = []
        self._original_box_records: dict[tuple[int, int], bytes] = {}
        self._validated = False
        if path is not None:
            self.read_save()

    @property
    def size(self) -> int:
        return self.profile["size"]

    @property
    def box_offset(self) -> int:
        return self.profile["box_offset"]

    @property
    def box_block_id(self) -> int:
        return self.profile["box_block_id"]

    @property
    def metadata_offset(self) -> int:
        return self.size - FOOTER_SIZE

    @property
    def party_count_offset(self) -> int:
        return PARTY_OFFSET + PARTY_CAPACITY * PARTY_RECORD_SIZE

    @staticmethod
    def _block_entry_offset(metadata_offset: int, block_id: int) -> int:
        # Metadata starts with two u64 timestamps and 32-bit "FEEB" magic;
        # each following entry is [u32 data length, u16 block ID, u16 checksum].
        return metadata_offset + BLOCK_INFO_HEADER_LENGTH + block_id * 8

    def _block_valid(self, data: bytes | bytearray, block_id: int,
                     start: int, length: int) -> bool:
        if start < 0 or start + length > len(data):
            return False
        entry = self._block_entry_offset(self.metadata_offset, block_id)
        if entry + 8 > len(data):
            return False
        stored_length = _u32(data, entry)
        stored_id = _u16(data, entry + 4)
        stored_checksum = _u16(data, entry + 6)
        calculated = crc16_ccitt(data[start:start + length])
        return (
            stored_length == length
            and stored_id == block_id
            and stored_checksum == calculated
        )

    def _validate(self, data: bytes | bytearray) -> None:
        if len(data) != self.size:
            raise ValueError(
                f"Expected a decrypted Generation VI {self.game_name} save of "
                f"0x{self.size:X} ({self.size:,}) bytes; got 0x{len(data):X} ({len(data):,})"
            )
        marker_offset = len(data) - 0x1F0
        if _u32(data, marker_offset) != BEEF_MAGIC:
            raise ValueError(
                "Generation VI save footer marker is missing. Use a decrypted "
                "PKHeX-compatible main save (not the encrypted 1 MiB 3DS container)."
            )

        if not self._block_valid(data, 0x12, PARTY_OFFSET, PARTY_BLOCK_LENGTH):
            raise ValueError("Generation VI party block metadata/checksum is invalid")
        if not self._block_valid(data, self.box_block_id, self.box_offset, BOX_BLOCK_LENGTH):
            raise ValueError("Generation VI PC box block metadata/checksum is invalid")

    def read_save(self) -> None:
        try:
            raw = Path(self.path).read_bytes()
        except OSError as exc:
            raise OSError(f"Could not read save file {self.path!r}: {exc}") from exc
        self._validate(raw)
        self.save_bytes = bytearray(raw)
        self._validated = True
        self._extract_party()
        self._extract_boxes()

    def _extract_party(self) -> None:
        count = self.save_bytes[self.party_count_offset]
        if count > PARTY_CAPACITY:
            raise ValueError(f"Invalid Gen VI party count {count}; maximum is {PARTY_CAPACITY}")
        extracted: list[Pokemon] = []
        self._original_party_records = []
        for slot in range(count):
            start = PARTY_OFFSET + slot * PARTY_RECORD_SIZE
            record = bytes(self.save_bytes[start:start + PARTY_RECORD_SIZE])
            if not any(record):
                raise ValueError(
                    f"Party slot {slot + 1} is empty despite party count {count}"
                )
            pokemon = _parse_pokemon(
                record, game_name=self.game_name, party=True, party_slot=slot
            )
            if pokemon is None:
                raise ValueError(f"Party slot {slot + 1} has no species data")
            extracted.append(pokemon)
            self._original_party_records.append(record)
        self.party_pokemon = extracted

    def _extract_boxes(self) -> None:
        all_boxes: list[list[Pokemon]] = []
        self._original_box_records = {}
        for box_index in range(BOX_COUNT):
            box: list[Pokemon] = []
            for slot in range(BOX_CAPACITY):
                start = self.box_offset + (
                    box_index * BOX_CAPACITY + slot
                ) * BOX_RECORD_SIZE
                record = bytes(self.save_bytes[start:start + BOX_RECORD_SIZE])
                if not any(record):
                    continue
                pokemon = _parse_pokemon(
                    record,
                    game_name=self.game_name,
                    party=False,
                    box_index=box_index,
                    box_slot=slot,
                )
                # A valid zero-species record may be an unused slot with leftover
                # bytes. Preserve it exactly rather than treating it as a Pokémon.
                if pokemon is None:
                    continue
                box.append(pokemon)
                self._original_box_records[(box_index, slot)] = record
            all_boxes.append(box)
        self.box_pokemon = all_boxes

    def print_all_pokemon(self) -> None:
        for index, pokemon in enumerate(self.party_pokemon, 1):
            print(f"Party {index}: {pokemon.name} (species {pokemon.species})")
        for box_index, box in enumerate(self.box_pokemon, 1):
            for pokemon in box:
                print(
                    f"Box {box_index}, slot {getattr(pokemon, 'gen6_box_slot', -1) + 1}: "
                    f"{pokemon.name} (species {pokemon.species})"
                )

    def _write_block_checksum(self, output: bytearray, block_id: int,
                              start: int, length: int) -> None:
        entry = self._block_entry_offset(self.metadata_offset, block_id)
        _put_u32(output, entry, length)
        _put_u16(output, entry + 4, block_id)
        _put_u16(output, entry + 6, crc16_ccitt(output[start:start + length]))

    def _make_output(self) -> bytes:
        if not self._validated or len(self.save_bytes) != self.size:
            raise ValueError("Read a valid Generation VI save before writing")
        if len(self.party_pokemon) > PARTY_CAPACITY:
            raise ValueError(f"Party exceeds {PARTY_CAPACITY} Pokémon")
        if len(self.box_pokemon) != BOX_COUNT:
            raise ValueError(f"Expected {BOX_COUNT} PC boxes, got {len(self.box_pokemon)}")
        output = bytearray(self.save_bytes)

        # Compact retained party records in list order. The record bytes are
        # retained verbatim; creating/editing PK6 attributes is intentionally
        # outside this extraction/clearing writer.
        original_party_set = set(self._original_party_records)
        party_records: list[bytes] = []
        for pokemon in self.party_pokemon:
            record = getattr(pokemon, "gen6_record", None)
            if record is None or len(record) != PARTY_RECORD_SIZE or record not in original_party_set:
                raise ValueError(
                    f"No original Gen VI party record available for {pokemon.name!r}; "
                    "new or edited Pokémon records cannot be written by this handler"
                )
            party_records.append(record)
        party_start = PARTY_OFFSET
        output[party_start:party_start + PARTY_CAPACITY * PARTY_RECORD_SIZE] = bytes(
            PARTY_CAPACITY * PARTY_RECORD_SIZE
        )
        for slot, record in enumerate(party_records):
            start = party_start + slot * PARTY_RECORD_SIZE
            output[start:start + PARTY_RECORD_SIZE] = record
        output[self.party_count_offset] = len(party_records)
        self._write_block_checksum(output, 0x12, PARTY_OFFSET, PARTY_BLOCK_LENGTH)

        # PC boxes use fixed positions. Retained records stay in their original
        # box/slot; only original Pokémon no longer present in box_pokemon are
        # cleared. Unknown empty-slot bytes and box layout metadata are preserved.
        retained: set[tuple[int, int]] = set()
        for box_index, box in enumerate(self.box_pokemon):
            if len(box) > BOX_CAPACITY:
                raise ValueError(f"PC box {box_index + 1} exceeds {BOX_CAPACITY} Pokémon")
            for pokemon in box:
                source_box = getattr(pokemon, "gen6_box_index", None)
                source_slot = getattr(pokemon, "gen6_box_slot", None)
                record = getattr(pokemon, "gen6_record", None)
                key = (source_box, source_slot)
                if (
                    source_box != box_index
                    or not isinstance(source_slot, int)
                    or not 0 <= source_slot < BOX_CAPACITY
                    or key not in self._original_box_records
                    or record != self._original_box_records.get(key)
                ):
                    raise ValueError(
                        f"No original Generation VI record available for {pokemon.name!r} "
                        f"in PC box {box_index + 1}; moving or editing Pokémon records is unsupported"
                    )
                if key in retained:
                    raise ValueError(f"Duplicate Pokémon slot in PC box {box_index + 1}, slot {source_slot + 1}")
                retained.add(key)

        for key, _record in self._original_box_records.items():
            if key in retained:
                continue
            box_index, slot = key
            start = self.box_offset + (box_index * BOX_CAPACITY + slot) * BOX_RECORD_SIZE
            output[start:start + BOX_RECORD_SIZE] = bytes(BOX_RECORD_SIZE)
        self._write_block_checksum(
            output, self.box_block_id, self.box_offset, BOX_BLOCK_LENGTH
        )

        # Checksum table entries and the BEEF marker must remain valid after edits.
        marker_offset = len(output) - 0x1F0
        _put_u32(output, marker_offset, BEEF_MAGIC)
        self._validate(output)
        if len(output) != self.size:
            raise AssertionError("Generation VI output length changed unexpectedly")
        return bytes(output)

    def write_save(self) -> str:
        """Write ``<input>.new`` atomically without overwriting the original."""
        output = self._make_output()
        output_path = f"{self.path}.new"
        bytes_safe_write(path=output_path, contents=output)
        return output_path


Generation6Save = Gen6_Save
