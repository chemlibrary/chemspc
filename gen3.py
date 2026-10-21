"""Reader/writer for English Pokémon Generation III GBA battery saves.

Supported games: Ruby, Sapphire, Emerald, FireRed, and LeafGreen.

The module validates the two 14-sector save slots in a raw 128 KiB .sav file,
selects the newest complete slot, and reads/writes the party and all PC boxes.
Output is written to ``<input path>.new``; the input save is never overwritten.

Each Pokémon keeps its original encrypted record so an unchanged record can be
preserved byte-for-byte. Edits to supported fields are serialized using the
PID-dependent substructure order, XOR encryption, and Pokémon checksum. The
module intentionally refuses to synthesize a new Gen III Pokémon without a
retained source record, as the game's party stats and metadata cannot be inferred
safely from only a species/name.

Format references:
    https://github.com/pret/pokeemerald/blob/master/include/save.h
    https://github.com/pret/pokeemerald/blob/master/src/save.c
    https://github.com/pret/pokefirered/blob/master/include/global.h
    https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV3.cs
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

try:
    from chempy.files import bytes_safe_write
except ModuleNotFoundError:
    def bytes_safe_write(*, path: str | os.PathLike[str], contents: bytes | bytearray) -> None:
        """Minimal atomic writer for standalone use when chempy is unavailable."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        with open(temporary, "wb") as file:
            file.write(contents)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, destination)

from pokemon import Pokemon

SAVE_SIZE = 0x20000             # 128 KiB
SECTOR_SIZE = 0x1000             # 4096 bytes
SECTOR_DATA_SIZE = 0xF80         # 3968 bytes, before the 128-byte footer/pad
SECTOR_FOOTER_ID_OFFSET = 0xFF4
SECTOR_FOOTER_CHECKSUM_OFFSET = 0xFF6
SECTOR_FOOTER_SIGNATURE_OFFSET = 0xFF8
SECTOR_FOOTER_COUNTER_OFFSET = 0xFFC
SECTOR_SIGNATURE = 0x08012025
SECTIONS_PER_SLOT = 14
SLOT_OFFSETS = (0x0000, 0xE000)
PARTY_COUNT_OFFSET = 0x234       # R/S/E: relative to logical section 1
PARTY_RECORDS_OFFSET = 0x238     # R/S/E: relative to logical section 1
PARTY_CAPACITY = 6
PARTY_RECORD_SIZE = 100
BOX_COUNT = 14
BOX_CAPACITY = 30
BOX_RECORD_SIZE = 80
BOX_COUNT_WORD_SIZE = 4
BOX_RECORDS_OFFSET = 4           # relative to concatenated PokémonStorage data
BOX_STORAGE_DATA_SIZE = 33744    # current box + records + names + wallpapers

# Retail variants checksum different used lengths for logical sections 0 and 4.
# The remaining sections have identical checksum ranges for these five English
# versions. All checksum ranges are multiples of four (little-endian u32 sums).
_COMMON_SECTION_CHECKSUM_SIZES = {
    1: 0xF80,
    2: 0xF80,
    3: 0xF80,
    5: 0xF80,
    6: 0xF80,
    7: 0xF80,
    8: 0xF80,
    9: 0xF80,
    10: 0xF80,
    11: 0xF80,
    12: 0xF80,
    13: 0x7D0,
}
SECTION_CHECKSUM_SIZES_BY_PROFILE = {
    "rs": {**_COMMON_SECTION_CHECKSUM_SIZES, 0: 0x890, 4: 0xC40},
    "emerald": {**_COMMON_SECTION_CHECKSUM_SIZES, 0: 0xF2C, 4: 0xF08},
    "frlg": {**_COMMON_SECTION_CHECKSUM_SIZES, 0: 0xF24, 4: 0xEE8},
}
# Backwards-convenient public checksum table (Emerald lengths).
SECTION_CHECKSUM_SIZES = SECTION_CHECKSUM_SIZES_BY_PROFILE["emerald"]

# (party count offset, first party record offset, count width). All listed games
# use a one-byte count and three padding bytes; FRLG's SaveBlock1 starts earlier.
PARTY_LAYOUTS = {
    "rs": (0x234, 0x238, 1),
    "emerald": (0x234, 0x238, 1),
    "frlg": (0x034, 0x038, 1),
}

_GAME_ALIASES = {
    "r": "ruby", "ruby": "ruby",
    "s": "sapphire", "sapphire": "sapphire",
    "rs": "ruby-sapphire", "ruby-sapphire": "ruby-sapphire",
    "ruby/sapphire": "ruby-sapphire",
    "e": "emerald", "emerald": "emerald",
    "fr": "firered", "fire-red": "firered", "fire red": "firered",
    "firered": "firered",
    "lg": "leafgreen", "leaf-green": "leafgreen", "leaf green": "leafgreen",
    "leafgreen": "leafgreen",
    "frlg": "firered-leafgreen", "firered-leafgreen": "firered-leafgreen",
    "fire-red-leaf-green": "firered-leafgreen",
    "auto": "auto", "gen3": "auto", "generation 3": "auto",
}
_GAME_PROFILE = {
    "ruby": "rs", "sapphire": "rs", "ruby-sapphire": "rs",
    "emerald": "emerald",
    "firered": "frlg", "leafgreen": "frlg", "firered-leafgreen": "frlg",
}

# Physical order of the four encrypted 12-byte substructures for PID % 24.
# Canonical names: G=growth, A=attacks, E=EVs/contest, M=miscellaneous.
SUBSTRUCTURE_ORDERS = (
    "GAEM", "GAME", "GEAM", "GEMA", "GMAE", "GMEA",
    "AGEM", "AGME", "AEGM", "AEMG", "AMGE", "AMEG",
    "EGAM", "EGMA", "EAGM", "EAMG", "EMGA", "EMAG",
    "MGAE", "MGEA", "MAGE", "MAEG", "MEGA", "MEAG",
)

# English Generation III glyphs. Unknown characters are displayed explicitly
# as [XX], preserving awareness that they cannot be safely re-encoded as English.
_GEN3_CHAR_MAP: dict[int, str] = {0x00: " "}
_GEN3_CHAR_MAP.update({0xA1 + i: str(i) for i in range(10)})
_GEN3_CHAR_MAP.update({0xBB + i: chr(ord("A") + i) for i in range(26)})
_GEN3_CHAR_MAP.update({0xD5 + i: chr(ord("a") + i) for i in range(26)})
_GEN3_CHAR_MAP.update({
    0x01: "À", 0x02: "Á", 0x03: "Â", 0x04: "Ç", 0x05: "È",
    0x06: "É", 0x07: "Ê", 0x08: "Ë", 0x09: "Ì", 0x0B: "Î",
    0x0C: "Ï", 0x0D: "Ò", 0x0E: "Ó", 0x0F: "Ô", 0x10: "Œ",
    0x11: "Ù", 0x12: "Ú", 0x13: "Û", 0x14: "Ñ", 0x15: "ß",
    0x16: "à", 0x17: "á", 0x19: "ç", 0x1A: "è", 0x1B: "é",
    0x1C: "ê", 0x1D: "ë", 0x1E: "ì", 0x20: "î", 0x21: "ï",
    0x22: "ò", 0x23: "ó", 0x24: "ô", 0x25: "œ", 0x26: "ù",
    0x27: "ú", 0x28: "û", 0x29: "ñ", 0x2A: "º", 0x2B: "ª",
    0x2D: "&", 0x2E: "+", 0x35: "=", 0x36: ";", 0x51: "¿",
    0x52: "¡", 0x5A: "Í", 0x5B: "%", 0x5C: "(", 0x5D: ")",
    0x68: "â", 0x6F: "í", 0xAB: "!", 0xAC: "?", 0xAD: ".",
    0xAE: "-", 0xAF: "·", 0xB0: "…", 0xB7: ":",
})
_GEN3_REVERSE_CHAR_MAP = {value: key for key, value in _GEN3_CHAR_MAP.items()}


def decode_gen3_text(data: bytes | bytearray, *, terminators: tuple[int, ...] = (0xFF,)) -> str:
    """Decode the supported English character subset until a terminator."""
    characters: list[str] = []
    for value in data:
        if value in terminators:
            break
        characters.append(_GEN3_CHAR_MAP.get(value, f"[{value:02X}]"))
    return "".join(characters).rstrip()


def encode_gen3_text(text: str, length: int, *, terminator: int = 0xFF) -> bytes:
    """Encode an English Gen III text field to exactly ``length`` bytes.

    Full-width names may use all available bytes without a terminator, which is
    important for the 10-byte nickname and 7-byte original-trainer name fields.
    """
    if length < 1:
        raise ValueError("Text field length must be positive")
    encoded = bytearray()
    for character in text:
        if character not in _GEN3_REVERSE_CHAR_MAP:
            raise ValueError(
                f"Character not supported by the English Generation III encoder: {character!r}"
            )
        encoded.append(_GEN3_REVERSE_CHAR_MAP[character])
    if len(encoded) > length:
        raise ValueError(f"Text is too long for a {length}-byte Generation III field")
    if len(encoded) == length:
        return bytes(encoded)
    encoded.append(terminator)
    encoded.extend(bytes([terminator]) * (length - len(encoded)))
    return bytes(encoded)


def _u16(data: bytes | bytearray, offset: int = 0) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


def _u32(data: bytes | bytearray, offset: int = 0) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    data[offset:offset + 2] = (value & 0xFFFF).to_bytes(2, "little")


def _calculate_section_checksum(
    data: bytes | bytearray,
    section_id: int,
    profile: str = "emerald",
) -> int:
    """Calculate a Gen III sector checksum with the game's correct block size."""
    try:
        size = SECTION_CHECKSUM_SIZES_BY_PROFILE[profile][section_id]
    except KeyError as exc:
        raise ValueError(f"Unknown checksum profile {profile!r} or section {section_id}") from exc
    if len(data) < size:
        raise ValueError(f"Section {section_id} needs {size} bytes; got {len(data)}")
    if size % 4:
        raise AssertionError("Section checksum sizes must be multiples of four")
    total = 0
    for offset in range(0, size, 4):
        total = (total + _u32(data, offset)) & 0xFFFFFFFF
    return ((total >> 16) + (total & 0xFFFF)) & 0xFFFF


def _is_newer_counter(left: int, right: int) -> bool:
    """Compare wrapping unsigned 32-bit save counters."""
    difference = (left - right) & 0xFFFFFFFF
    return difference != 0 and difference < 0x80000000


def _decode_gen3_record(raw: bytes, *, party_record: bool) -> Pokemon | None:
    """Decode a boxed (80-byte) or party (100-byte) Gen III Pokémon record."""
    expected_size = PARTY_RECORD_SIZE if party_record else BOX_RECORD_SIZE
    if len(raw) != expected_size:
        raise ValueError(f"Expected a {expected_size}-byte record, received {len(raw)} bytes")

    personality = _u32(raw, 0)
    ot_id = _u32(raw, 4)
    flags = raw[0x13]
    has_species = bool(flags & 0x02)
    if not has_species:
        return None

    xor_key = personality ^ ot_id
    encrypted_payload = raw[0x20:0x50]
    if len(encrypted_payload) != 48:
        raise ValueError("Incomplete Generation III encrypted Pokémon payload")
    shuffled = bytearray()
    for offset in range(0, 48, 4):
        shuffled.extend((_u32(encrypted_payload, offset) ^ xor_key).to_bytes(4, "little"))

    order = SUBSTRUCTURE_ORDERS[personality % 24]
    blocks = {name: bytes(shuffled[i * 12:(i + 1) * 12]) for i, name in enumerate(order)}
    growth, attacks, evs, misc = (blocks[key] for key in "GAEM")
    species = _u16(growth, 0)
    held_item = _u16(growth, 2)
    experience = _u32(growth, 4)
    pp_bonus = growth[8]

    canonical = growth + attacks + evs + misc
    calculated_checksum = sum(
        _u16(canonical, offset) for offset in range(0, len(canonical), 2)
    ) & 0xFFFF
    stored_checksum = _u16(raw, 0x1C)

    pokemon = Pokemon()
    pokemon.generation = 3
    pokemon.species = species
    pokemon.name = decode_gen3_text(raw[0x08:0x12])
    pokemon.original_trainer_name = decode_gen3_text(raw[0x14:0x1B])
    pokemon.original_trainer = ot_id
    pokemon.personality = personality
    pokemon.language = raw[0x12]
    pokemon.gen3_flags = flags
    pokemon.gen3_bad_egg = bool(flags & 0x01)
    pokemon.gen3_has_species = has_species
    pokemon.gen3_markings = raw[0x1B]

    pokemon.held_item = held_item
    pokemon.exp = experience
    pokemon.friendship = growth[9]
    pokemon.gen3_pp_bonuses = pp_bonus
    pokemon.move1, pokemon.move2, pokemon.move3, pokemon.move4 = (
        _u16(attacks, 0), _u16(attacks, 2), _u16(attacks, 4), _u16(attacks, 6)
    )
    pokemon.move1_pp, pokemon.move2_pp, pokemon.move3_pp, pokemon.move4_pp = attacks[8:12]
    pokemon.hp_ev, pokemon.attack_ev, pokemon.defense_ev = evs[0], evs[1], evs[2]
    pokemon.speed_ev = evs[3]
    pokemon.special_attack_ev, pokemon.special_defense_ev = evs[4], evs[5]
    # The legacy shared schema has one Special EV property; keep the sum there
    # while retaining each Gen III value on its own object attribute.
    pokemon.special_ev = evs[4] + evs[5]
    pokemon.pokerus = misc[0]
    pokemon.gen3_met_location = misc[1]
    pokemon.caught = _u16(misc, 2)  # origin/met data retained in legacy field
    pokemon.gen3_origin_info = _u16(misc, 2)
    pokemon.iv = _u32(misc, 4)
    pokemon.gen3_ivs_word = _u32(misc, 4)
    pokemon.gen3_checksum_valid = stored_checksum == calculated_checksum
    pokemon.gen3_growth_block = growth
    pokemon.gen3_attacks_block = attacks
    pokemon.gen3_evs_block = evs
    pokemon.gen3_misc_block = misc

    if party_record:
        pokemon.status_condition = _u32(raw, 0x50)
        pokemon.level = raw[0x54]
        pokemon.gen3_mail_id = raw[0x55]
        pokemon.current_hp = _u16(raw, 0x56)
        pokemon.max_hp = _u16(raw, 0x58)
        pokemon.attack = _u16(raw, 0x5A)
        pokemon.defense = _u16(raw, 0x5C)
        pokemon.speed = _u16(raw, 0x5E)
        pokemon.special_attack = _u16(raw, 0x60)
        pokemon.special_defense = _u16(raw, 0x62)
        pokemon.gen3_party_record = bytes(raw)
    else:
        # Box records store EXP, but not calculated level or battle stats.
        pokemon.level = None
        pokemon.status_condition = 0
        pokemon.current_hp = 0
        pokemon.max_hp = 0
        pokemon.attack = 0
        pokemon.defense = 0
        pokemon.speed = 0
        pokemon.special_attack = 0
        pokemon.special_defense = 0

    pokemon.gen3_box_record = bytes(raw[:BOX_RECORD_SIZE])
    pokemon._gen3_record_size = expected_size
    pokemon._gen3_original_snapshot_box = _snapshot_pokemon(pokemon, party_record=False)
    if party_record:
        pokemon._gen3_original_snapshot_party = _snapshot_pokemon(pokemon, party_record=True)
    return pokemon


def _snapshot_pokemon(pokemon: Pokemon, *, party_record: bool) -> dict[str, object]:
    names = (
        "personality", "original_trainer", "name", "original_trainer_name",
        "language", "gen3_flags", "gen3_markings", "species", "held_item",
        "exp", "move1", "move2", "move3", "move4", "move1_pp",
        "move2_pp", "move3_pp", "move4_pp", "friendship", "pokerus",
        "caught", "iv", "hp_ev", "attack_ev", "defense_ev", "speed_ev",
        "special_attack_ev", "special_defense_ev", "special_ev", "gen3_pp_bonuses",
    )
    snapshot = {name: getattr(pokemon, name, None) for name in names}
    if party_record:
        for name in (
            "status_condition", "level", "current_hp", "max_hp", "attack",
            "defense", "speed", "special_attack", "special_defense", "gen3_mail_id",
        ):
            snapshot[name] = getattr(pokemon, name, None)
    return snapshot


def _write_uint(buffer: bytearray, offset: int, length: int, value: int, field: str) -> None:
    value = int(value)
    if value < 0 or value >= (1 << (8 * length)):
        raise ValueError(f"{field} value {value} does not fit in {length} bytes")
    buffer[offset:offset + length] = value.to_bytes(length, "little")


def _serialize_gen3_record(pokemon: Pokemon, *, party_record: bool) -> bytes:
    """Serialize a retained record, re-encrypting supported changed fields."""
    expected_size = PARTY_RECORD_SIZE if party_record else BOX_RECORD_SIZE
    original = getattr(
        pokemon,
        "gen3_party_record" if party_record else "gen3_box_record",
        None,
    )
    if original is None and not party_record:
        party_raw = getattr(pokemon, "gen3_party_record", None)
        if party_raw is not None:
            original = party_raw[:BOX_RECORD_SIZE]
    if original is None:
        raise ValueError(
            f"{getattr(pokemon, 'name', 'Pokémon')!r} has no retained Gen III record; "
            "creating new Pokémon records is not implemented"
        )
    if len(original) != expected_size:
        raise ValueError(f"Retained record has length {len(original)}, expected {expected_size}")

    snapshot_key = "_gen3_original_snapshot_party" if party_record else "_gen3_original_snapshot_box"
    snapshot = getattr(pokemon, snapshot_key, None)
    if snapshot is None:
        return bytes(original)
    if _snapshot_pokemon(pokemon, party_record=party_record) == snapshot:
        return bytes(original)

    raw = bytearray(original)
    growth = bytearray(pokemon.gen3_growth_block)
    attacks = bytearray(pokemon.gen3_attacks_block)
    evs = bytearray(pokemon.gen3_evs_block)
    misc = bytearray(pokemon.gen3_misc_block)

    _write_uint(raw, 0x00, 4, pokemon.personality, "personality")
    _write_uint(raw, 0x04, 4, pokemon.original_trainer, "original trainer ID")
    if pokemon.name != snapshot["name"]:
        raw[0x08:0x12] = encode_gen3_text(pokemon.name, 10)
    if pokemon.original_trainer_name != snapshot["original_trainer_name"]:
        raw[0x14:0x1B] = encode_gen3_text(pokemon.original_trainer_name, 7)
    if pokemon.language != snapshot["language"]:
        _write_uint(raw, 0x12, 1, pokemon.language, "language")
    if pokemon.gen3_flags != snapshot["gen3_flags"]:
        _write_uint(raw, 0x13, 1, pokemon.gen3_flags, "record flags")
    if pokemon.gen3_markings != snapshot["gen3_markings"]:
        _write_uint(raw, 0x1B, 1, pokemon.gen3_markings, "markings")

    _write_uint(growth, 0, 2, pokemon.species, "species")
    _write_uint(growth, 2, 2, pokemon.held_item, "held item")
    _write_uint(growth, 4, 4, pokemon.exp, "experience")
    if pokemon.gen3_pp_bonuses != snapshot["gen3_pp_bonuses"]:
        _write_uint(growth, 8, 1, pokemon.gen3_pp_bonuses, "PP bonuses")
    _write_uint(growth, 9, 1, pokemon.friendship, "friendship")

    for index, field in enumerate(("move1", "move2", "move3", "move4")):
        _write_uint(attacks, index * 2, 2, getattr(pokemon, field), field)
    for index, field in enumerate(("move1_pp", "move2_pp", "move3_pp", "move4_pp")):
        _write_uint(attacks, 8 + index, 1, getattr(pokemon, field), field)

    _write_uint(evs, 0, 1, pokemon.hp_ev, "HP EV")
    _write_uint(evs, 1, 1, pokemon.attack_ev, "Attack EV")
    _write_uint(evs, 2, 1, pokemon.defense_ev, "Defense EV")
    _write_uint(evs, 3, 1, pokemon.speed_ev, "Speed EV")
    if pokemon.special_ev != snapshot["special_ev"] and (
        pokemon.special_attack_ev == snapshot["special_attack_ev"]
        and pokemon.special_defense_ev == snapshot["special_defense_ev"]
    ):
        raise ValueError(
            "Gen III Special EVs are separate; edit special_attack_ev and/or "
            "special_defense_ev instead of the combined special_ev field"
        )
    _write_uint(evs, 4, 1, pokemon.special_attack_ev, "Special Attack EV")
    _write_uint(evs, 5, 1, pokemon.special_defense_ev, "Special Defense EV")

    _write_uint(misc, 0, 1, pokemon.pokerus, "Pokérus")
    _write_uint(misc, 2, 2, pokemon.caught, "origin/met data")
    _write_uint(misc, 4, 4, pokemon.iv, "IV word")

    canonical = bytes(growth + attacks + evs + misc)
    checksum = sum(_u16(canonical, offset) for offset in range(0, 48, 2)) & 0xFFFF
    _write_uint(raw, 0x1C, 2, checksum, "Pokémon checksum")

    # Restore canonical blocks to the PID-dependent order and re-encrypt u32s.
    blocks = {"G": bytes(growth), "A": bytes(attacks), "E": bytes(evs), "M": bytes(misc)}
    order = SUBSTRUCTURE_ORDERS[pokemon.personality % 24]
    shuffled = b"".join(blocks[name] for name in order)
    key = pokemon.personality ^ pokemon.original_trainer
    encrypted = bytearray()
    for offset in range(0, 48, 4):
        encrypted.extend((_u32(shuffled, offset) ^ key).to_bytes(4, "little"))
    raw[0x20:0x50] = encrypted

    if party_record:
        _write_uint(raw, 0x50, 4, pokemon.status_condition, "status condition")
        _write_uint(raw, 0x54, 1, pokemon.level, "level")
        _write_uint(raw, 0x55, 1, getattr(pokemon, "gen3_mail_id", 0), "mail ID")
        for offset, field in (
            (0x56, "current_hp"), (0x58, "max_hp"), (0x5A, "attack"),
            (0x5C, "defense"), (0x5E, "speed"), (0x60, "special_attack"),
            (0x62, "special_defense"),
        ):
            _write_uint(raw, offset, 2, getattr(pokemon, field), field)

    # Update the retained representation and snapshot so repeat writes are stable.
    pokemon.gen3_growth_block = bytes(growth)
    pokemon.gen3_attacks_block = bytes(attacks)
    pokemon.gen3_evs_block = bytes(evs)
    pokemon.gen3_misc_block = bytes(misc)
    pokemon.gen3_origin_info = pokemon.caught
    pokemon.gen3_ivs_word = pokemon.iv
    pokemon.gen3_checksum_valid = True
    updated = bytes(raw)
    if party_record:
        pokemon.gen3_party_record = updated
        pokemon.gen3_box_record = updated[:BOX_RECORD_SIZE]
    else:
        pokemon.gen3_box_record = updated
        if getattr(pokemon, "gen3_party_record", None) is not None:
            pokemon.gen3_party_record = updated + pokemon.gen3_party_record[BOX_RECORD_SIZE:]
    pokemon._gen3_original_snapshot_box = _snapshot_pokemon(pokemon, party_record=False)
    if getattr(pokemon, "gen3_party_record", None) is not None:
        pokemon._gen3_original_snapshot_party = _snapshot_pokemon(pokemon, party_record=True)
    return updated


class Gen3_Save:
    """Reader/writer for English Ruby, Sapphire, Emerald, FireRed, LeafGreen saves.

    ``path`` must identify a raw 128 KiB (131072-byte) GBA ``.sav`` file.
    Pass a game label if known: ``ruby``, ``sapphire``, ``emerald``, ``firered``,
    or ``leafgreen``. ``game='auto'`` validates all checksum profiles and works
    when one profile is unambiguous. If checksum ranges leave both RSE and FRLG
    layouts plausible, it raises rather than interpreting the party at the wrong
    offset; in that case supply the game's explicit label.
    """

    generation = 3

    def __init__(self, path: str | os.PathLike[str] | None = None, *, game: str = "auto"):
        self.save_size = SAVE_SIZE
        self.path = os.fspath(path) if path is not None else "./gen3-save.sav"
        normalized = str(game).strip().lower().replace("_", "-")
        if normalized not in _GAME_ALIASES:
            raise ValueError(
                "Unsupported Generation III game. Choose ruby, sapphire, emerald, "
                "firered, leafgreen, ruby-sapphire, firered-leafgreen, or auto."
            )
        self.game = _GAME_ALIASES[normalized]
        self.game_name = self.game if self.game != "auto" else "generation-3"
        self.layout_profile: str | None = _GAME_PROFILE.get(self.game)
        (
            self.party_count_offset,
            self.party_records_offset,
            self.party_count_size,
        ) = PARTY_LAYOUTS[self.layout_profile] if self.layout_profile else (PARTY_COUNT_OFFSET, PARTY_RECORDS_OFFSET, 1)

        self.save_bytes = bytearray()
        self.party_pokemon: list[Pokemon] = []
        self.box_pokemon: list[list[Pokemon]] = [[] for _ in range(BOX_COUNT)]
        self.active_slot: int | None = None
        self.active_save_index: int | None = None
        self.section_offsets: dict[int, int] = {}
        self.section_data: dict[int, bytearray] = {}
        self.section_checksum_valid: dict[int, bool] = {}
        self.section_profile_candidates: list[str] = []
        self._current_box = 0

        if path is None:
            return
        if not os.path.isfile(self.path):
            raise FileNotFoundError(f"Save file not found: {self.path}")
        with open(self.path, "rb") as file:
            raw = file.read()
        if len(raw) != SAVE_SIZE:
            raise ValueError(
                f"Expected a {SAVE_SIZE}-byte (128 KiB) Generation III save, got {len(raw)} bytes"
            )
        self.save_bytes = bytearray(raw)
        self._load_active_slot()
        self.party_pokemon = self.extract_gen3_party_pokemon()
        self.box_pokemon = self.extract_gen3_pokemon_boxes()

    @staticmethod
    def read_gen3_save(path: str | os.PathLike[str]) -> bytes:
        with open(path, "rb") as file:
            data = file.read()
        if len(data) != SAVE_SIZE:
            raise ValueError(f"Expected a {SAVE_SIZE}-byte Generation III save, got {len(data)} bytes")
        return data

    def _inspect_slot(self, slot_number: int, profile: str) -> dict | None:
        slot_start = SLOT_OFFSETS[slot_number]
        sections: dict[int, int] = {}
        counters: list[int] = []
        valid = True
        checksum_sizes = SECTION_CHECKSUM_SIZES_BY_PROFILE[profile]

        for physical_index in range(SECTIONS_PER_SLOT):
            sector_offset = slot_start + physical_index * SECTOR_SIZE
            sector = self.save_bytes[sector_offset:sector_offset + SECTOR_SIZE]
            section_id = _u16(sector, SECTOR_FOOTER_ID_OFFSET)
            if (
                _u32(sector, SECTOR_FOOTER_SIGNATURE_OFFSET) != SECTOR_SIGNATURE
                or section_id not in checksum_sizes
                or section_id in sections
            ):
                valid = False
                continue
            stored = _u16(sector, SECTOR_FOOTER_CHECKSUM_OFFSET)
            calculated = _calculate_section_checksum(sector[:SECTOR_DATA_SIZE], section_id, profile)
            if stored != calculated:
                valid = False
            sections[section_id] = sector_offset
            counters.append(_u32(sector, SECTOR_FOOTER_COUNTER_OFFSET))

        if not valid or set(sections) != set(range(SECTIONS_PER_SLOT)) or len(set(counters)) != 1:
            return None
        return {"slot": slot_number, "index": counters[0], "offsets": sections, "profile": profile}

    def _load_active_slot(self) -> None:
        profiles = [self.layout_profile] if self.layout_profile else ["emerald", "rs", "frlg"]
        matches_by_slot: dict[int, list[dict]] = {0: [], 1: []}
        for slot_number in range(2):
            for profile in profiles:
                candidate = self._inspect_slot(slot_number, profile)
                if candidate is not None:
                    matches_by_slot[slot_number].append(candidate)

        usable = [slot for slot, matches in matches_by_slot.items() if matches]
        if not usable:
            raise ValueError(
                "No complete valid Generation III save slot was found for the selected game. "
                "Ensure this is a raw 128 KiB .sav file and that the game label is correct."
            )
        chosen_slot = usable[0]
        for slot_number in usable[1:]:
            left = matches_by_slot[slot_number][0]["index"]
            right = matches_by_slot[chosen_slot][0]["index"]
            if _is_newer_counter(left, right):
                chosen_slot = slot_number

        candidates = matches_by_slot[chosen_slot]
        candidate_profiles = {item["profile"] for item in candidates}
        party_layouts = {PARTY_LAYOUTS[profile] for profile in candidate_profiles}
        if len(party_layouts) > 1:
            names = ", ".join(sorted(candidate_profiles))
            raise ValueError(
                f"The save matches multiple incompatible Gen III layouts ({names}). "
                "Specify game='ruby', 'sapphire', 'emerald', 'firered', or 'leafgreen'."
            )
        priority = {"emerald": 0, "rs": 1, "frlg": 2}
        selected = min(candidates, key=lambda item: priority[item["profile"]])
        self.layout_profile = selected["profile"]
        (
            self.party_count_offset,
            self.party_records_offset,
            self.party_count_size,
        ) = PARTY_LAYOUTS[self.layout_profile]
        self.section_profile_candidates = sorted(candidate_profiles)
        self.active_slot = selected["slot"]
        self.active_save_index = selected["index"]
        self.section_offsets = dict(selected["offsets"])
        self.section_data = {
            section_id: bytearray(self.save_bytes[offset:offset + SECTOR_DATA_SIZE])
            for section_id, offset in self.section_offsets.items()
        }
        self.section_checksum_valid = {section_id: True for section_id in self.section_offsets}

    def _refresh_storage_sections(self) -> bytearray:
        storage = bytearray()
        for section_id in range(5, 14):
            storage.extend(self.section_data[section_id])
        if len(storage) != 9 * SECTOR_DATA_SIZE or len(storage) < BOX_STORAGE_DATA_SIZE:
            raise ValueError("Incomplete Generation III PC storage data")
        return storage

    def _store_storage_sections(self, storage: bytes | bytearray) -> None:
        if len(storage) != 9 * SECTOR_DATA_SIZE:
            raise ValueError(f"Storage stream must be {9 * SECTOR_DATA_SIZE} bytes")
        for index, section_id in enumerate(range(5, 14)):
            start = index * SECTOR_DATA_SIZE
            self.section_data[section_id][:] = storage[start:start + SECTOR_DATA_SIZE]

    def print_all_pokemon(self) -> None:
        for pokemon in self.party_pokemon:
            print(f"{pokemon.name} (#{pokemon.species}) - lvl {pokemon.level}")
        for box_number, box in enumerate(self.box_pokemon, start=1):
            for pokemon in box:
                level_text = f"lvl {pokemon.level}" if pokemon.level else "level stored in EXP"
                print(f"Box {box_number}: {pokemon.name} (#{pokemon.species}) - {level_text}")

    def extract_gen3_party_pokemon(self) -> list[Pokemon]:
        if not self.section_data:
            raise ValueError("No valid Generation III save slot has been loaded")
        block = self.section_data[1]
        count = block[self.party_count_offset]
        if count > PARTY_CAPACITY:
            raise ValueError(f"Invalid Generation III party count: {count}")
        result = []
        for index in range(count):
            start = self.party_records_offset + index * PARTY_RECORD_SIZE
            pokemon = _decode_gen3_record(bytes(block[start:start + PARTY_RECORD_SIZE]), party_record=True)
            if pokemon is not None:
                result.append(pokemon)
        return result

    def extract_gen3_pokemon_boxes(self) -> list[list[Pokemon]]:
        storage = self._refresh_storage_sections()
        self._current_box = _u32(storage, 0)
        if self._current_box >= BOX_COUNT:
            raise ValueError(f"Invalid Generation III current-box index: {self._current_box}")
        boxes: list[list[Pokemon]] = []
        for box_index in range(BOX_COUNT):
            box: list[Pokemon] = []
            for slot_index in range(BOX_CAPACITY):
                start = BOX_RECORDS_OFFSET + (box_index * BOX_CAPACITY + slot_index) * BOX_RECORD_SIZE
                raw = bytes(storage[start:start + BOX_RECORD_SIZE])
                pokemon = _decode_gen3_record(raw, party_record=False)
                if pokemon is not None:
                    # Preserve each occupied slot's original position. Removing
                    # one Pokémon must not compact the remaining box records.
                    pokemon.gen3_box_number = box_index
                    pokemon.gen3_box_slot = slot_index
                    box.append(pokemon)
            boxes.append(box)
        return boxes

    @staticmethod
    def _serialize_party(pokemon_list: Sequence[Pokemon]) -> bytes:
        if len(pokemon_list) > PARTY_CAPACITY:
            raise ValueError(f"A Generation III party may contain at most {PARTY_CAPACITY} Pokémon")
        records = bytearray(PARTY_CAPACITY * PARTY_RECORD_SIZE)
        for index, pokemon in enumerate(pokemon_list):
            record = _serialize_gen3_record(pokemon, party_record=True)
            start = index * PARTY_RECORD_SIZE
            records[start:start + PARTY_RECORD_SIZE] = record
        # First four bytes are count + padding, followed by six party records.
        return bytes([len(pokemon_list), 0, 0, 0]) + bytes(records)

    @staticmethod
    def _serialize_boxes(boxes: Sequence[Sequence[Pokemon]], current_box: int) -> bytes:
        if len(boxes) != BOX_COUNT:
            raise ValueError(f"Expected {BOX_COUNT} PC boxes, got {len(boxes)}")
        if not 0 <= current_box < BOX_COUNT:
            raise ValueError(f"Invalid current PC box index: {current_box}")
        storage = bytearray(9 * SECTOR_DATA_SIZE)
        storage[:BOX_COUNT_WORD_SIZE] = current_box.to_bytes(4, "little")
        for box_index, box in enumerate(boxes):
            if len(box) > BOX_CAPACITY:
                raise ValueError(f"PC box {box_index + 1} exceeds {BOX_CAPACITY} Pokémon")
            assigned: dict[int, Pokemon] = {}
            pending: list[Pokemon] = []
            for pokemon in box:
                old_box = getattr(pokemon, "gen3_box_number", None)
                old_slot = getattr(pokemon, "gen3_box_slot", None)
                if (
                    old_box == box_index and isinstance(old_slot, int)
                    and 0 <= old_slot < BOX_CAPACITY and old_slot not in assigned
                ):
                    assigned[old_slot] = pokemon
                else:
                    pending.append(pokemon)
            free_slots = (slot for slot in range(BOX_CAPACITY) if slot not in assigned)
            for pokemon in pending:
                try:
                    assigned[next(free_slots)] = pokemon
                except StopIteration as exc:
                    raise ValueError(f"PC box {box_index + 1} is full") from exc
            for slot_index, pokemon in assigned.items():
                record = _serialize_gen3_record(pokemon, party_record=False)
                start = BOX_RECORDS_OFFSET + (box_index * BOX_CAPACITY + slot_index) * BOX_RECORD_SIZE
                storage[start:start + BOX_RECORD_SIZE] = record
                pokemon.gen3_box_number = box_index
                pokemon.gen3_box_slot = slot_index
        return bytes(storage)

    def export_gen3_party_list(self) -> bytes:
        """Return one count byte, three padding bytes, and six party records."""
        return self._serialize_party(self.party_pokemon)

    def export_gen3_boxes(self) -> bytes:
        """Return storage with records updated and names/wallpapers preserved."""
        storage = self._refresh_storage_sections()
        current_box = _u32(storage, 0)
        if current_box >= BOX_COUNT:
            raise ValueError(f"Invalid Generation III current-box index: {current_box}")
        serialized = self._serialize_boxes(self.box_pokemon, current_box)
        records_end = BOX_RECORDS_OFFSET + BOX_COUNT * BOX_CAPACITY * BOX_RECORD_SIZE
        storage[BOX_RECORDS_OFFSET:records_end] = serialized[BOX_RECORDS_OFFSET:records_end]
        return bytes(storage)

    def update_gen3_checksums(self) -> bool:
        """Recalculate checksums for the active slot using its game profile."""
        if len(self.save_bytes) != SAVE_SIZE:
            raise ValueError(f"Save data must be exactly {SAVE_SIZE} bytes")
        if len(self.section_offsets) != SECTIONS_PER_SLOT or not self.layout_profile:
            raise ValueError("No complete active Generation III save slot is loaded")
        for section_id, sector_offset in self.section_offsets.items():
            sector = self.save_bytes[sector_offset:sector_offset + SECTOR_SIZE]
            checksum = _calculate_section_checksum(
                sector[:SECTOR_DATA_SIZE], section_id, self.layout_profile
            )
            _put_u16(self.save_bytes, sector_offset + SECTOR_FOOTER_CHECKSUM_OFFSET, checksum)
            self.section_checksum_valid[section_id] = True
        return True

    def write_save(self) -> str:
        """Write the modified save to ``<input path>.new`` without overwriting input."""
        if len(self.save_bytes) != SAVE_SIZE:
            raise ValueError(f"Save data must be exactly {SAVE_SIZE} bytes")
        if self.active_slot is None or len(self.section_offsets) != SECTIONS_PER_SLOT:
            raise ValueError("No complete active Generation III save slot is loaded")

        party_data = self.export_gen3_party_list()
        section1 = self.section_data[1]
        section1[self.party_count_offset] = len(self.party_pokemon)
        party_records = party_data[4:]
        section1[
            self.party_records_offset:self.party_records_offset + len(party_records)
        ] = party_records

        self._store_storage_sections(self.export_gen3_boxes())

        # Section IDs rotate across physical sectors; write via the footer map.
        for section_id, sector_offset in self.section_offsets.items():
            self.save_bytes[sector_offset:sector_offset + SECTOR_DATA_SIZE] = self.section_data[section_id]
        self.update_gen3_checksums()

        output_path = f"{self.path}.new"
        bytes_safe_write(path=output_path, contents=self.save_bytes)
        return output_path


Generation3Save = Gen3_Save
