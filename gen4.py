"""Reader/writer for English Pokémon Generation IV retail save files.

Supported layouts: Diamond, Pearl, Platinum, HeartGold, and SoulSilver.
The module reads a raw 512 KiB Nintendo DS ``.sav`` file, validates Gen IV
small/storage blocks and their CRC-16-CCITT checksums, extracts party and PC
Pokémon, and writes a ``.new`` copy. In keeping with chemspc's extraction
workflow, existing Pokémon records are preserved verbatim when retained; the
application can clear records after committing them to SQLite.

Format references:
    https://bulbapedia.bulbagarden.net/wiki/Save_data_structure_(Generation_IV)
    https://bulbapedia.bulbagarden.net/wiki/Pok%C3%A9mon_data_structure_in_Generation_IV
    https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV4.cs
    https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV4Sinnoh.cs
    https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV4HGSS.cs
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

try:
    from chempy.files import bytes_safe_write
except ModuleNotFoundError:
    def bytes_safe_write(*, path: str | os.PathLike[str], contents: bytes | bytearray) -> None:
        """Small atomic file writer fallback for standalone/testing use."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        with open(temporary, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)

from pokemon import Pokemon

SAVE_SIZE = 0x80000          # 512 KiB
PARTITION_SIZE = 0x40000     # primary/backup partition distance
PARTY_COUNT_OFFSET = 0x94
PARTY_RECORDS_OFFSET = 0x98
PARTY_CAPACITY = 6
PARTY_RECORD_SIZE = 236
BOX_COUNT = 18
BOX_CAPACITY = 30
BOX_RECORD_SIZE = 136
BLOCK_MAGICS = (0x20060623, 0x20070903)  # international/Japanese, Korean

# Small/general size, storage start relative to partition, storage block size,
# footer bytes excluded from CRC, and storage layout kind.
PROFILES = {
    "diamond":   {"profile": "dp",   "general_size": 0xC100, "storage_start": 0xC100, "storage_size": 0x121E0, "footer_size": 0x14, "storage_kind": "sinnoh"},
    "pearl":     {"profile": "dp",   "general_size": 0xC100, "storage_start": 0xC100, "storage_size": 0x121E0, "footer_size": 0x14, "storage_kind": "sinnoh"},
    "platinum":  {"profile": "pt",   "general_size": 0xCF2C, "storage_start": 0xCF2C, "storage_size": 0x121E4, "footer_size": 0x14, "storage_kind": "sinnoh"},
    "heartgold": {"profile": "hgss", "general_size": 0xF628, "storage_start": 0xF700, "storage_size": 0x12310, "footer_size": 0x10, "storage_kind": "hgss"},
    "soulsilver":{ "profile": "hgss", "general_size": 0xF628, "storage_start": 0xF700, "storage_size": 0x12310, "footer_size": 0x10, "storage_kind": "hgss"},
}
GAME_ALIASES = {
    "d": "diamond", "diamond": "diamond", "dp": "diamond", "diamond-pearl": "diamond",
    "p": "pearl", "pearl": "pearl",
    "pt": "platinum", "platinum": "platinum",
    "hg": "heartgold", "heartgold": "heartgold", "heart-gold": "heartgold", "heart gold": "heartgold",
    "ss": "soulsilver", "soulsilver": "soulsilver", "soul-silver": "soulsilver", "soul silver": "soulsilver",
}

# Order of the 4 logical 32-byte substructures after decrypting the payload.
# This is the Generation IV personality-derived permutation table.
SUBSTRUCTURE_ORDERS = (
    "ABCD", "ABDC", "ACBD", "ACDB", "ADBC", "ADCB",
    "BACD", "BADC", "BCAD", "BCDA", "BDAC", "BDCA",
    "CABD", "CADB", "CBAD", "CBDA", "CDAB", "CDBA",
    "DABC", "DACB", "DBAC", "DBCA", "DCAB", "DCBA",
)

# The English alphabet and digits have fixed IDs in the shared Gen IV 16-bit
# character set. This handles ordinary names and common punctuation. Unknown
# special-language characters become '?' rather than leaking raw code points.
_CHAR_MAP: dict[int, str] = {0xFFFF: "", 0x0000: "", 0x0001: " "}
for _i, _ch in enumerate("0123456789"):
    _CHAR_MAP[0x0121 + _i] = _ch
for _i, _ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _CHAR_MAP[0x012B + _i] = _ch
for _i, _ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _CHAR_MAP[0x0145 + _i] = _ch
_CHAR_MAP.update({
    0x01AC: "!", 0x01AD: "?", 0x01AE: ",", 0x01AF: ".",
    0x01B1: "/", 0x01B3: "'", 0x01B9: "(", 0x01BA: ")",
    0x01BD: "+", 0x01BE: "-", 0x01BF: "*", 0x01C0: "#",
    0x01C1: "=", 0x01C2: "&", 0x01C3: "~", 0x01C4: ":",
    0x01C5: ";", 0x01A1: "œ", 0x01A2: "Ş", 0x01A3: "ş",
    0x01A4: "ª", 0x01A5: "º", 0x01AA: "¡", 0x01AB: "¿",
})


def _u16(data: bytes | bytearray, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


def _u32(data: bytes | bytearray, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    data[offset:offset + 2] = int(value).to_bytes(2, "little")


def _put_u32(data: bytearray, offset: int, value: int) -> None:
    data[offset:offset + 4] = int(value).to_bytes(4, "little")


def crc16_ccitt(data: bytes | bytearray | memoryview, initial: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE used for Generation IV save block checksums."""
    crc = initial & 0xFFFF
    for byte in data:
        crc ^= int(byte) << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def decode_gen4_text(data: bytes | bytearray, *, stop_at_terminator: bool = True) -> str:
    """Decode a little-endian Gen IV string using the shared DS character set."""
    chars: list[str] = []
    for offset in range(0, len(data) - 1, 2):
        value = _u16(data, offset)
        if stop_at_terminator and value == 0xFFFF:
            break
        if value == 0x0000 and stop_at_terminator:
            break
        chars.append(_CHAR_MAP.get(value, "?"))
    return "".join(chars).rstrip()


def _decrypt_gen4_pokemon(record: bytes) -> tuple[bytes, int, int]:
    """Return logical unencrypted 128-byte payload, PID, and checksum.

    Gen IV records consist of an unencrypted 8-byte header, a 128-byte encrypted
    and PID-shuffled payload, and (for party records) 100 extra stat bytes.
    """
    if len(record) not in (BOX_RECORD_SIZE, PARTY_RECORD_SIZE):
        raise ValueError(f"Expected a 136- or 236-byte Gen IV record; got {len(record)}")
    personality = _u32(record, 0)
    checksum = _u16(record, 6)
    encrypted = record[8:0x88]
    if not any(record):
        return bytes(128), personality, checksum
    decrypted = bytearray(128)
    seed = checksum
    for offset in range(0, 128, 2):
        seed = (0x41C64E6D * seed + 0x6073) & 0xFFFFFFFF
        word = _u16(encrypted, offset) ^ (seed >> 16)
        decrypted[offset:offset + 2] = word.to_bytes(2, "little")

    permutation = SUBSTRUCTURE_ORDERS[((personality & 0x3E000) >> 13) % 24]
    logical = bytearray(128)
    for stored_block, block_name in enumerate(permutation):
        logical_index = ord(block_name) - ord("A")
        logical[logical_index * 32:(logical_index + 1) * 32] = decrypted[stored_block * 32:(stored_block + 1) * 32]

    calc = sum(_u16(logical, offset) for offset in range(0, 128, 2)) & 0xFFFF
    if calc != checksum:
        raise ValueError(
            f"Generation IV Pokémon checksum mismatch (PID 0x{personality:08X}; "
            f"stored 0x{checksum:04X}, calculated 0x{calc:04X})"
        )
    return bytes(logical), personality, checksum


def _record_present(record: bytes) -> bool:
    """Check species/checksum for a stored PK4; all-zero records are empty."""
    if not any(record):
        return False
    logical, _pid, _checksum = _decrypt_gen4_pokemon(record)
    return _u16(logical, 0) != 0


def _parse_pokemon(record: bytes, *, party: bool, game_name: str,
                   party_slot: int | None = None, box_index: int | None = None,
                   box_slot: int | None = None) -> Pokemon:
    logical, personality, checksum = _decrypt_gen4_pokemon(record)
    if _u16(logical, 0) == 0:
        raise ValueError("Cannot parse an empty Generation IV Pokémon record")

    species = _u16(logical, 0)
    held_item = _u16(logical, 2)
    original_trainer = _u32(logical, 4)  # TID16 | SID16
    exp = _u32(logical, 8)
    friendship = logical[0x0C]
    ability = logical[0x0D]
    language = logical[0x0F]
    hp_ev, attack_ev, defense_ev, speed_ev, sp_attack_ev, sp_defense_ev = logical[0x10:0x16]
    moves = [_u16(logical, 0x20 + i * 2) for i in range(4)]
    move_pp = list(logical[0x28:0x2C])
    iv_word = _u32(logical, 0x30)
    # Nicknames occupy 22 bytes (11 UTF-16-like code units); the following
    # byte is unused and then comes the game-of-origin byte. Avoid decoding it
    # as part of an unterminated full-length nickname.
    nickname = decode_gen4_text(logical[0x40:0x56])
    ot_name = decode_gen4_text(logical[0x60:0x70])
    game_of_origin = logical[0x57]
    egg_date = int.from_bytes(logical[0x70:0x73], "little")
    met_date = int.from_bytes(logical[0x73:0x76], "little")
    egg_location = _u16(logical, 0x76)
    met_location = _u16(logical, 0x78)
    # D/P/Pt store the ball at 0x83; HG/SS use the added field at 0x86.
    pokeball = logical[0x7E] if game_name in ("heartgold", "soulsilver") else logical[0x7B]
    met_level_gender = logical[0x7C]
    met_level = met_level_gender & 0x7F
    original_trainer_gender = (met_level_gender >> 7) & 1
    encounter_type = logical[0x7D]
    pokerus = logical[0x7A]
    # Flags are encoded in block B at global record offset 0x40.
    flag_byte = logical[0x38]
    gender = 2 if (flag_byte & 0x04) else (1 if (flag_byte & 0x02) else 0)
    is_egg = bool(iv_word & (1 << 30))
    is_nicknamed = bool(iv_word & (1 << 31))
    # The trailing party-battle-stat area uses the PID as its XOR key too.
    party_stats = bytearray(record[BOX_RECORD_SIZE:]) if party else bytearray()
    if party:
        seed = personality
        for offset in range(0, len(party_stats), 2):
            seed = (0x41C64E6D * seed + 0x6073) & 0xFFFFFFFF
            word = _u16(party_stats, offset) ^ (seed >> 16)
            party_stats[offset:offset + 2] = word.to_bytes(2, "little")
    level = party_stats[4] if party else None
    status = _u32(party_stats, 0) if party else None
    current_hp = _u16(party_stats, 6) if party else None
    max_hp = _u16(party_stats, 8) if party else None
    attack = _u16(party_stats, 10) if party else None
    defense = _u16(party_stats, 12) if party else None
    speed = _u16(party_stats, 14) if party else None
    special_attack = _u16(party_stats, 16) if party else None
    special_defense = _u16(party_stats, 18) if party else None

    pokemon = Pokemon(
        generation=4, name=nickname, species=species, held_item=held_item,
        move1=moves[0], move2=moves[1], move3=moves[2], move4=moves[3],
        original_trainer=original_trainer, original_trainer_name=ot_name,
        exp=exp, hp_ev=hp_ev, attack_ev=attack_ev, defense_ev=defense_ev,
        speed_ev=speed_ev, special_ev=sp_attack_ev + sp_defense_ev,
        special_attack_ev=sp_attack_ev, special_defense_ev=sp_defense_ev,
        iv=iv_word & 0x3FFFFFFF, move1_pp=move_pp[0], move2_pp=move_pp[1],
        move3_pp=move_pp[2], move4_pp=move_pp[3], friendship=friendship,
        pokerus=pokerus, caught=met_location, level=level, status_condition=status,
        current_hp=current_hp, max_hp=max_hp, attack=attack, defense=defense,
        speed=speed, special_attack=special_attack, special_defense=special_defense,
    )
    pokemon.game_name = game_name
    pokemon.personality = personality
    pokemon.ability = ability
    pokemon.language = language
    pokemon.gender = gender
    pokemon.nature = personality % 25
    pokemon.is_egg = int(is_egg)
    pokemon.is_nicknamed = int(is_nicknamed)
    pokemon.is_shiny = int(((original_trainer & 0xFFFF) ^ (original_trainer >> 16) ^ (personality & 0xFFFF) ^ (personality >> 16)) < 8)
    pokemon.gen4_checksum = checksum
    pokemon.game_of_origin = game_of_origin
    pokemon.egg_date = egg_date
    pokemon.met_date = met_date
    pokemon.egg_location = egg_location
    pokemon.met_location = met_location
    pokemon.met_level = met_level
    pokemon.pokeball = pokeball
    pokemon.encounter_type = encounter_type
    pokemon.original_trainer_gender = original_trainer_gender
    pokemon.gen4_box_record = bytes(record[:BOX_RECORD_SIZE])
    pokemon.gen4_party_record = bytes(record) if party else None
    pokemon.gen4_party_slot = party_slot
    pokemon.gen4_box_index = box_index
    pokemon.gen4_box_slot = box_slot
    return pokemon


def _footer_info(block: bytes | bytearray, expected_size: int, footer_size: int,
                 *, check_crc: bool = True) -> dict | None:
    if len(block) != expected_size or expected_size < max(footer_size, 0x14):
        return None
    size = _u32(block, len(block) - 0xC)
    magic = _u32(block, len(block) - 8)
    if size != expected_size or magic not in BLOCK_MAGICS:
        return None
    checksum = _u16(block, len(block) - 2)
    calculated = crc16_ccitt(block[:-footer_size])
    if check_crc and checksum != calculated:
        return None
    return {
        "link": _u32(block, len(block) - 0x14),
        "counter": _u32(block, len(block) - 0x10),
        "size": size,
        "magic": magic,
        "checksum": checksum,
        "checksum_valid": checksum == calculated,
    }


def _update_block_checksum(data: bytearray, start: int, size: int, footer_size: int) -> None:
    block = data[start:start + size]
    if len(block) != size:
        raise ValueError("Block lies outside the save file")
    _put_u16(data, start + size - 2, crc16_ccitt(block[:-footer_size]))


class Gen4_Save:
    """Read, extract, and write Diamond/Pearl/Platinum/HGSS save files.

    The constructor requires a game label because save block sizes differ among
    D/P, Platinum, and HGSS. The input must be a raw 512 KiB retail save.
    """
    generation = 4

    def __init__(self, path: str | os.PathLike[str] | None = None, *, game: str = "diamond"):
        self.path = os.fspath(path) if path is not None else "./gen4-save.sav"
        normalized = str(game).strip().lower().replace("_", "-")
        if normalized not in GAME_ALIASES:
            raise ValueError("Choose diamond, pearl, platinum, heartgold, or soulsilver")
        self.game_name = GAME_ALIASES[normalized]
        self.game = self.game_name
        self.profile = PROFILES[self.game]
        self.save_bytes = bytearray()
        self.party_pokemon: list[Pokemon] = []
        self.box_pokemon: list[list[Pokemon]] = [[] for _ in range(BOX_COUNT)]
        self.active_general_offset: int | None = None
        self.active_storage_offset: int | None = None
        self.valid_general_offsets: list[int] = []
        self.valid_storage_offsets: list[int] = []

        if path is not None:
            self.read_save()

    def _block_at(self, start: int, size: int) -> bytes:
        return bytes(self.save_bytes[start:start + size])

    def _scan_blocks(self, data: bytes | bytearray | None = None) -> tuple[list[dict], list[dict]]:
        blob = self.save_bytes if data is None else data
        general_blocks: list[dict] = []
        storage_blocks: list[dict] = []
        for partition in (0, PARTITION_SIZE):
            gstart = partition
            gblock = bytes(blob[gstart:gstart + self.profile["general_size"]])
            gfooter = _footer_info(gblock, self.profile["general_size"], self.profile["footer_size"])
            if gfooter is not None:
                general_blocks.append({"start": gstart, "data": gblock, **gfooter})

            sstart = partition + self.profile["storage_start"]
            sblock = bytes(blob[sstart:sstart + self.profile["storage_size"]])
            sfooter = _footer_info(sblock, self.profile["storage_size"], self.profile["footer_size"])
            if sfooter is not None:
                storage_blocks.append({"start": sstart, "data": sblock, **sfooter})
        return general_blocks, storage_blocks

    def read_save(self) -> None:
        try:
            data = Path(self.path).read_bytes()
        except OSError as exc:
            raise OSError(f"Could not read save file {self.path!r}: {exc}") from exc
        if len(data) != SAVE_SIZE:
            raise ValueError(
                f"Expected a raw 512 KiB Generation IV save ({SAVE_SIZE} bytes), got {len(data)}"
            )
        self.save_bytes = bytearray(data)
        general_blocks, storage_blocks = self._scan_blocks()
        pairs = []
        for general in general_blocks:
            for storage in storage_blocks:
                if general["link"] == storage["link"]:
                    # Small-block save count is the primary freshness discriminator;
                    # storage count breaks ties for independently saved boxes.
                    pairs.append((general["counter"], storage["counter"], general, storage))
        if not pairs:
            raise ValueError(
                f"No valid, checksum-correct linked Generation IV save blocks found for {self.game_name}. "
                "Check the game selection and ensure this is an unheadered 512 KiB .sav file."
            )
        pairs.sort(key=lambda pair: (pair[0], pair[1]), reverse=True)
        _gcount, _scount, general, storage = pairs[0]
        self.active_general_offset = general["start"]
        self.active_storage_offset = storage["start"]
        self.valid_general_offsets = [entry["start"] for entry in general_blocks]
        self.valid_storage_offsets = [entry["start"] for entry in storage_blocks]
        self._extract_party()
        self._extract_boxes()

    def _extract_party(self) -> None:
        assert self.active_general_offset is not None
        base = self.active_general_offset
        count = self.save_bytes[base + PARTY_COUNT_OFFSET]
        if count > PARTY_CAPACITY:
            raise ValueError(f"Invalid Gen IV party count {count}; expected 0-{PARTY_CAPACITY}")
        result: list[Pokemon] = []
        for slot in range(count):
            start = base + PARTY_RECORDS_OFFSET + slot * PARTY_RECORD_SIZE
            record = bytes(self.save_bytes[start:start + PARTY_RECORD_SIZE])
            if not _record_present(record[:BOX_RECORD_SIZE]):
                raise ValueError(f"Party slot {slot + 1} claims a Pokémon but its record is empty")
            result.append(_parse_pokemon(record, party=True, game_name=self.game_name, party_slot=slot))
        self.party_pokemon = result

    def _box_record_offset(self, box_index: int, slot_index: int) -> int:
        if self.profile["storage_kind"] == "hgss":
            return box_index * 0x1000 + slot_index * BOX_RECORD_SIZE
        return 4 + (box_index * BOX_CAPACITY + slot_index) * BOX_RECORD_SIZE

    def _extract_boxes(self) -> None:
        assert self.active_storage_offset is not None
        base = self.active_storage_offset
        boxes: list[list[Pokemon]] = []
        for box_index in range(BOX_COUNT):
            entries: list[Pokemon] = []
            for slot_index in range(BOX_CAPACITY):
                start = base + self._box_record_offset(box_index, slot_index)
                record = bytes(self.save_bytes[start:start + BOX_RECORD_SIZE])
                if not any(record):
                    continue
                if _record_present(record):
                    entries.append(_parse_pokemon(
                        record, party=False, game_name=self.game_name,
                        box_index=box_index, box_slot=slot_index,
                    ))
            boxes.append(entries)
        self.box_pokemon = boxes

    def print_all_pokemon(self) -> None:
        print("Party Pokémon:")
        for pokemon in self.party_pokemon:
            print(f"  {pokemon.name or '(unnamed)'} (species {pokemon.species}, level {pokemon.level or 'stored'})")
        for index, box in enumerate(self.box_pokemon, start=1):
            print(f"Box {index}:")
            for pokemon in box:
                print(f"  {pokemon.name or '(unnamed)'} (species {pokemon.species}, level {pokemon.level or 'stored'})")

    def _make_output(self) -> bytearray:
        if len(self.save_bytes) != SAVE_SIZE:
            raise ValueError("No complete Generation IV save is loaded")
        output = bytearray(self.save_bytes)
        general_blocks, storage_blocks = self._scan_blocks()
        valid_general = {entry["start"] for entry in general_blocks}
        valid_storage = {entry["start"] for entry in storage_blocks}

        if len(self.party_pokemon) > PARTY_CAPACITY:
            raise ValueError(f"Party can contain at most {PARTY_CAPACITY} Pokémon")
        if len(self.box_pokemon) != BOX_COUNT:
            raise ValueError(f"Expected {BOX_COUNT} PC boxes, got {len(self.box_pokemon)}")
        if any(len(box) > BOX_CAPACITY for box in self.box_pokemon):
            raise ValueError(f"Each Generation IV PC box can contain at most {BOX_CAPACITY} Pokémon")

        # Keep all checksum-valid general copies consistent, not just the newest
        # one: a game may use a backup general block if power was lost on save.
        for base in valid_general:
            output[base + PARTY_COUNT_OFFSET] = len(self.party_pokemon)
            party_start = base + PARTY_RECORDS_OFFSET
            output[party_start:party_start + PARTY_CAPACITY * PARTY_RECORD_SIZE] = bytes(PARTY_CAPACITY * PARTY_RECORD_SIZE)
            for slot, pokemon in enumerate(self.party_pokemon):
                record = getattr(pokemon, "gen4_party_record", None)
                if record is None or len(record) != PARTY_RECORD_SIZE:
                    raise ValueError(
                        f"Cannot serialize party Pokémon {pokemon.name!r}: no retained 236-byte Gen IV party record"
                    )
                start = party_start + slot * PARTY_RECORD_SIZE
                output[start:start + PARTY_RECORD_SIZE] = record
            _update_block_checksum(output, base, self.profile["general_size"], self.profile["footer_size"])

        # Clear/rebuild the PC records in every valid storage copy. Non-Pokémon
        # data, including box names/wallpapers and footer linkage, stays intact.
        for base in valid_storage:
            for box_index, box in enumerate(self.box_pokemon):
                for slot_index in range(BOX_CAPACITY):
                    start = base + self._box_record_offset(box_index, slot_index)
                    output[start:start + BOX_RECORD_SIZE] = bytes(BOX_RECORD_SIZE)
                used_slots: set[int] = set()
                for sequence_index, pokemon in enumerate(box):
                    original_slot = getattr(pokemon, "gen4_box_slot", None)
                    original_box = getattr(pokemon, "gen4_box_index", None)
                    if original_box == box_index and isinstance(original_slot, int) and 0 <= original_slot < BOX_CAPACITY and original_slot not in used_slots:
                        slot_index = original_slot
                    else:
                        slot_index = next((i for i in range(BOX_CAPACITY) if i not in used_slots), -1)
                    if slot_index < 0:
                        raise ValueError(f"PC box {box_index + 1} is full")
                    record = getattr(pokemon, "gen4_box_record", None)
                    if record is None or len(record) != BOX_RECORD_SIZE:
                        party_record = getattr(pokemon, "gen4_party_record", None)
                        if party_record is not None and len(party_record) >= BOX_RECORD_SIZE:
                            record = party_record[:BOX_RECORD_SIZE]
                    if record is None or len(record) != BOX_RECORD_SIZE:
                        raise ValueError(
                            f"Cannot serialize boxed Pokémon {pokemon.name!r}: no retained 136-byte Gen IV record"
                        )
                    start = base + self._box_record_offset(box_index, slot_index)
                    output[start:start + BOX_RECORD_SIZE] = record
                    used_slots.add(slot_index)
            # The total count field in HGSS is maintained for game consistency.
            if self.profile["storage_kind"] == "hgss":
                stored_count = sum(len(box) for box in self.box_pokemon)
                _put_u32(output, base + 0x12004, stored_count)
            _update_block_checksum(output, base, self.profile["storage_size"], self.profile["footer_size"])

        # Sanity-check every block just rewritten; malformed/invalid stale blocks
        # not selected by the game are left alone instead of manufacturing footers.
        for base in valid_general:
            block = bytes(output[base:base + self.profile["general_size"]])
            info = _footer_info(block, self.profile["general_size"], self.profile["footer_size"])
            if info is None:
                raise ValueError(f"Updated general block at 0x{base:X} failed checksum validation")
        for base in valid_storage:
            block = bytes(output[base:base + self.profile["storage_size"]])
            info = _footer_info(block, self.profile["storage_size"], self.profile["footer_size"])
            if info is None:
                raise ValueError(f"Updated storage block at 0x{base:X} failed checksum validation")
        return output

    def write_save(self) -> str:
        """Write the current party/box lists to ``<input>.new`` without overwriting input."""
        output = self._make_output()
        output_path = f"{self.path}.new"
        bytes_safe_write(path=output_path, contents=output)
        return output_path


Generation4Save = Gen4_Save
