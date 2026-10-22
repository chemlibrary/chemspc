"""Reader/writer for English Pokémon Red, Blue, and Yellow save files.

Generation I saves are 32 KiB SRAM dumps. Larger dumps are accepted, but only
 their first 32 KiB are meaningful to the supported English Red/Blue/Yellow
 layout. The module reads the live Current Box copy in bank 1, reads the other
 boxes from their SRAM banks, and updates all relevant checksums when writing.

Writing is intended for extraction/clearing existing Pokémon. Retained records
are preserved; new Pokémon cannot be synthesized from only the shared Pokemon
model because the Gen I record contains additional version-specific bytes.

Format references:
    https://savedex.net/reference/gen-1-save-file-format
    https://bulbapedia.bulbagarden.net/wiki/Save_data_structure_(Generation_I)
    https://github.com/pret/pokered/blob/master/engine/menus/save.asm
"""

from __future__ import annotations

import os
from pathlib import Path

from pokemon import Pokemon

SAVE_SIZE = 0x8000
MAIN_DATA_START = 0x2598
MAIN_CHECKSUM_OFFSET = 0x3523
PARTY_OFFSET = 0x2F2C
PARTY_SIZE = 0x194  # 404 bytes
PARTY_CAPACITY = 6
PARTY_RECORD_SIZE = 44
CURRENT_BOX_NUMBER_OFFSET = 0x284C
CURRENT_BOX_OFFSET = 0x30C0
BOX_CAPACITY = 20
BOX_RECORD_SIZE = 33
BOX_SIZE = 0x462  # 1 count + 21 species bytes + 20 records + OT/nickname names
BOX_DATA_START = 22
BOX_OT_NAMES_OFFSET = BOX_DATA_START + BOX_CAPACITY * BOX_RECORD_SIZE
BOX_NICKNAMES_OFFSET = BOX_OT_NAMES_OFFSET + BOX_CAPACITY * 11
BOX_OFFSETS = tuple(
    [0x4000 + i * BOX_SIZE for i in range(6)]
    + [0x6000 + i * BOX_SIZE for i in range(6)]
)
BANK_BOX_CHECKSUM_OFFSET = {
    0x4000: 0x4000 + 6 * BOX_SIZE,
    0x6000: 0x6000 + 6 * BOX_SIZE,
}

# English Red/Blue/Yellow internal species index -> National Pokédex number.
# Unused slots and glitch species are omitted and are recorded as dex #0 while
# their actual internal ID is retained in Pokemon.gen1_internal_species.
INTERNAL_TO_DEX = {
    0x01: 112, 0x02: 115, 0x03: 32, 0x04: 35, 0x05: 21, 0x06: 100,
    0x07: 34, 0x08: 80, 0x09: 2, 0x0A: 103, 0x0B: 108, 0x0C: 102,
    0x0D: 88, 0x0E: 94, 0x0F: 29, 0x10: 31, 0x11: 104, 0x12: 111,
    0x13: 131, 0x14: 59, 0x15: 151, 0x16: 130, 0x17: 90, 0x18: 72,
    0x19: 92, 0x1A: 123, 0x1B: 120, 0x1C: 9, 0x1D: 127, 0x1E: 114,
    0x21: 58, 0x22: 95, 0x23: 22, 0x24: 16, 0x25: 79, 0x26: 64,
    0x27: 75, 0x28: 113, 0x29: 67, 0x2A: 122, 0x2B: 106, 0x2C: 107,
    0x2D: 24, 0x2E: 47, 0x2F: 54, 0x30: 96, 0x31: 76, 0x33: 126,
    0x35: 125, 0x36: 82, 0x37: 109, 0x39: 56, 0x3A: 86, 0x3B: 50,
    0x3C: 128, 0x40: 83, 0x41: 48, 0x42: 149, 0x46: 84, 0x47: 60,
    0x48: 124, 0x49: 146, 0x4A: 144, 0x4B: 145, 0x4C: 132, 0x4D: 52,
    0x4E: 98, 0x52: 37, 0x53: 38, 0x54: 25, 0x55: 26, 0x58: 147,
    0x59: 148, 0x5A: 140, 0x5B: 141, 0x5C: 116, 0x5D: 117,
    0x60: 27, 0x61: 28, 0x62: 138, 0x63: 139, 0x64: 39, 0x65: 40,
    0x66: 133, 0x67: 136, 0x68: 135, 0x69: 134, 0x6A: 66, 0x6B: 41,
    0x6C: 23, 0x6D: 46, 0x6E: 61, 0x6F: 62, 0x70: 13, 0x71: 14,
    0x72: 15, 0x74: 85, 0x75: 57, 0x76: 51, 0x77: 49, 0x78: 87,
    0x7B: 10, 0x7C: 11, 0x7D: 12, 0x7E: 68, 0x80: 55, 0x81: 97,
    0x82: 42, 0x83: 150, 0x84: 143, 0x85: 129, 0x88: 89, 0x8A: 99,
    0x8B: 91, 0x8D: 101, 0x8E: 36, 0x8F: 110, 0x90: 53, 0x91: 105,
    0x93: 93, 0x94: 63, 0x95: 65, 0x96: 17, 0x97: 18, 0x98: 121,
    0x99: 1, 0x9A: 3, 0x9B: 73, 0x9D: 118, 0x9E: 119,
    0xA3: 77, 0xA4: 78, 0xA5: 19, 0xA6: 20, 0xA7: 33, 0xA8: 30,
    0xA9: 74, 0xAA: 137, 0xAB: 142, 0xAD: 81, 0xB0: 4, 0xB1: 7,
    0xB2: 5, 0xB3: 8, 0xB4: 6,
}

# Decoding for the standard English Gen I character map. Uncommon glyph/control
# codes are rendered as a replacement marker instead of being mistaken for ASCII.
_GEN1_CHAR_MAP = {}
_GEN1_CHAR_MAP.update({0x80 + i: chr(ord("A") + i) for i in range(26)})
_GEN1_CHAR_MAP.update({0xA0 + i: chr(ord("a") + i) for i in range(26)})
_GEN1_CHAR_MAP.update({0xF6 + i: str(i) for i in range(10)})
_GEN1_CHAR_MAP.update({
    0x7F: " ", 0x9A: "(", 0x9B: ")", 0x9C: ":", 0x9D: ";",
    0x9E: "[", 0x9F: "]", 0xBA: "é", 0xE0: "'", 0xE1: "PK",
    0xE2: "MN", 0xE3: "-", 0xE4: "'r", 0xE5: "'m", 0xE6: "?",
    0xE7: "!", 0xE8: ".", 0xEF: "♂", 0xF0: "¥", 0xF1: "×",
    0xF2: ".", 0xF3: "/", 0xF4: ",", 0xF5: "♀",
})
_GEN1_REVERSE_CHAR_MAP = {value: key for key, value in _GEN1_CHAR_MAP.items()}


def decode_gen1_text(data: bytes) -> str:
    """Decode an English Gen I fixed-width text field up to its 0x50 terminator."""
    decoded = []
    for value in data:
        if value == 0x50:
            break
        decoded.append(_GEN1_CHAR_MAP.get(value, "?"))
    return "".join(decoded).rstrip()


def _decode_name_field(data: bytes) -> str:
    if len(data) != 11:
        raise ValueError(f"Expected 11-byte Gen I name field, got {len(data)}")
    # A maximum-length name contains 10 glyphs and then the final terminator.
    return decode_gen1_text(data[:10])


def _checksum(data: bytes | bytearray) -> int:
    """Generation I checksum: one's complement of the byte sum, modulo 256."""
    return (~sum(data)) & 0xFF


def _empty_box() -> bytes:
    box = bytearray(BOX_SIZE)
    box[1:22] = b"\xFF" * 21
    return bytes(box)


def _field_bytes(pokemon: Pokemon, attribute: str, expected: int) -> bytes:
    value = getattr(pokemon, attribute, None)
    if not isinstance(value, (bytes, bytearray)) or len(value) != expected:
        raise ValueError(
            f"Cannot serialize a new Generation I Pokémon without its original "
            f"{attribute} ({expected} bytes); this handler supports preserving "
            "or removing existing Pokémon."
        )
    return bytes(value)


class Gen1_Save:
    """Reader/writer for English Pokémon Red, Blue, and Yellow SRAM saves."""

    def __init__(self, path: str | os.PathLike[str], game: str = "red"):
        normalized_game = game.strip().lower().replace("_", "-")
        if normalized_game not in {"red", "blue", "yellow"}:
            raise ValueError("Generation I supports only the English Red, Blue, and Yellow games")
        self.game_name = normalized_game
        self.path = os.fspath(path)
        if not os.path.isfile(self.path):
            raise FileNotFoundError(f"Save file not found: {self.path}")

        with open(self.path, "rb") as handle:
            raw = handle.read()
        if len(raw) < SAVE_SIZE:
            raise ValueError(
                f"Expected at least a {SAVE_SIZE}-byte (32 KiB) Generation I save, got {len(raw)} bytes"
            )
        # Some Yellow cartridge dumpers emit 128 KiB; SRAM is the first 32 KiB.
        self.save_bytes = bytearray(raw[:SAVE_SIZE])
        if not self.validate_main_checksum():
            raise ValueError(
                "Invalid Generation I main checksum at 0x3523; refusing to modify a potentially corrupt save"
            )

        selected_box = self.save_bytes[CURRENT_BOX_NUMBER_OFFSET] & 0x7F
        if selected_box >= len(BOX_OFFSETS):
            raise ValueError(f"Invalid selected PC box number: {selected_box}")
        self.current_box_index = selected_box
        self._box_bank_valid = {
            base: (
                self.save_bytes[BANK_BOX_CHECKSUM_OFFSET[base]]
                == _checksum(self.save_bytes[base:BANK_BOX_CHECKSUM_OFFSET[base]])
            )
            for base in BANK_BOX_CHECKSUM_OFFSET
        }

        self.party_pokemon = self.extract_party()
        self.box_pokemon = self.extract_boxes()
        self._original_party_signature = self._party_signature(self.party_pokemon)
        self._original_box_signatures = [self._party_signature(box) for box in self.box_pokemon]

    @staticmethod
    def _party_signature(pokemon_list: list[Pokemon]) -> tuple[int, ...]:
        return tuple(id(pokemon) for pokemon in pokemon_list)

    def validate_main_checksum(self) -> bool:
        if len(self.save_bytes) != SAVE_SIZE:
            return False
        return self.save_bytes[MAIN_CHECKSUM_OFFSET] == _checksum(
            self.save_bytes[MAIN_DATA_START:MAIN_CHECKSUM_OFFSET]
        )

    def _parse_pokemon(
        self,
        record: bytes,
        ot_name_bytes: bytes,
        nickname_bytes: bytes,
        *,
        party: bool,
    ) -> Pokemon:
        expected = PARTY_RECORD_SIZE if party else BOX_RECORD_SIZE
        if len(record) != expected:
            raise ValueError(f"Expected {expected}-byte Gen I Pokémon record, got {len(record)}")
        internal_species = record[0]
        level = record[0x21] if party else record[0x03]
        pokemon = Pokemon(
            generation=1,
            name=_decode_name_field(nickname_bytes),
            species=INTERNAL_TO_DEX.get(internal_species, 0),
            held_item=record[0x07],  # Gen I stores catch rate in this byte.
            move1=record[0x08], move2=record[0x09], move3=record[0x0A], move4=record[0x0B],
            original_trainer=int.from_bytes(record[0x0C:0x0E], "big"),
            original_trainer_name=_decode_name_field(ot_name_bytes),
            exp=int.from_bytes(record[0x0E:0x11], "big"),
            hp_ev=int.from_bytes(record[0x11:0x13], "big"),
            attack_ev=int.from_bytes(record[0x13:0x15], "big"),
            defense_ev=int.from_bytes(record[0x15:0x17], "big"),
            speed_ev=int.from_bytes(record[0x17:0x19], "big"),
            special_ev=int.from_bytes(record[0x19:0x1B], "big"),
            iv=int.from_bytes(record[0x1B:0x1D], "big"),
            move1_pp=record[0x1D], move2_pp=record[0x1E],
            move3_pp=record[0x1F], move4_pp=record[0x20],
            friendship=None, pokerus=None, caught=None,
            level=level,
            status_condition=record[0x04],
            current_hp=int.from_bytes(record[0x01:0x03], "big") if party else None,
            max_hp=int.from_bytes(record[0x22:0x24], "big") if party else None,
            attack=int.from_bytes(record[0x24:0x26], "big") if party else None,
            defense=int.from_bytes(record[0x26:0x28], "big") if party else None,
            speed=int.from_bytes(record[0x28:0x2A], "big") if party else None,
            special_attack=int.from_bytes(record[0x2A:0x2C], "big") if party else None,
            special_defense=None,
            gen1_internal_species=internal_species,
        )
        # Retain the exact source bytes so records can be moved within their
        # supported container or left unchanged without lossy reconstruction.
        pokemon._gen1_species_index = internal_species
        pokemon._gen1_party_record = bytes(record) if party else None
        pokemon._gen1_box_record = bytes(record[:BOX_RECORD_SIZE])
        pokemon._gen1_ot_name_bytes = bytes(ot_name_bytes)
        pokemon._gen1_nickname_bytes = bytes(nickname_bytes)
        return pokemon

    def _parse_party_region(self, data: bytes | bytearray) -> list[Pokemon]:
        if len(data) != PARTY_SIZE:
            raise ValueError(f"Party region must be {PARTY_SIZE} bytes")
        count = data[0]
        if count > PARTY_CAPACITY:
            raise ValueError(f"Invalid Generation I party count: {count}")
        species_list = data[1:8]
        pokemon: list[Pokemon] = []
        ot_names_offset = 0x110
        nicknames_offset = 0x152
        for index in range(count):
            start = 8 + index * PARTY_RECORD_SIZE
            record = bytes(data[start:start + PARTY_RECORD_SIZE])
            if record[0] == 0:
                raise ValueError(f"Invalid empty species in party slot {index + 1}")
            if species_list[index] not in (record[0], 0xFF):
                raise ValueError(
                    f"Party species list and record disagree in slot {index + 1}"
                )
            ot_start = ot_names_offset + index * 11
            nickname_start = nicknames_offset + index * 11
            pokemon.append(self._parse_pokemon(
                record,
                bytes(data[ot_start:ot_start + 11]),
                bytes(data[nickname_start:nickname_start + 11]),
                party=True,
            ))
        return pokemon

    def _parse_box_region(self, data: bytes | bytearray, box_number: int) -> list[Pokemon]:
        if len(data) != BOX_SIZE:
            raise ValueError(f"Box {box_number + 1} must be {BOX_SIZE} bytes")
        count = data[0]
        if count > BOX_CAPACITY:
            raise ValueError(f"Invalid Pokémon count {count} in PC box {box_number + 1}")
        species_list = data[1:22]
        pokemon: list[Pokemon] = []
        for index in range(count):
            start = BOX_DATA_START + index * BOX_RECORD_SIZE
            record = bytes(data[start:start + BOX_RECORD_SIZE])
            if record[0] == 0:
                raise ValueError(f"Invalid empty species in PC box {box_number + 1}, slot {index + 1}")
            if species_list[index] not in (record[0], 0xFF):
                raise ValueError(
                    f"PC box {box_number + 1} species list and record disagree in slot {index + 1}"
                )
            ot_start = BOX_OT_NAMES_OFFSET + index * 11
            nickname_start = BOX_NICKNAMES_OFFSET + index * 11
            pokemon.append(self._parse_pokemon(
                record,
                bytes(data[ot_start:ot_start + 11]),
                bytes(data[nickname_start:nickname_start + 11]),
                party=False,
            ))
        return pokemon

    def extract_party(self) -> list[Pokemon]:
        start = PARTY_OFFSET
        return self._parse_party_region(self.save_bytes[start:start + PARTY_SIZE])

    def extract_boxes(self) -> list[list[Pokemon]]:
        boxes: list[list[Pokemon]] = []
        for index, offset in enumerate(BOX_OFFSETS):
            if index == self.current_box_index:
                # The copy in bank 1 is live; the numbered box may be stale.
                region = self.save_bytes[CURRENT_BOX_OFFSET:CURRENT_BOX_OFFSET + BOX_SIZE]
                boxes.append(self._parse_box_region(region, index))
                continue

            bank_base = 0x4000 if index < 6 else 0x6000
            if not self._box_bank_valid[bank_base]:
                # The retail game treats never-initialized PC SRAM banks as
                # empty. The current box above remains authoritative regardless.
                boxes.append([])
                continue

            checksum_offset = BANK_BOX_CHECKSUM_OFFSET[bank_base]
            within_bank = index % 6
            stored_checksum = self.save_bytes[checksum_offset + 1 + within_bank]
            region = self.save_bytes[offset:offset + BOX_SIZE]
            if stored_checksum != _checksum(region):
                raise ValueError(
                    f"Checksum mismatch for PC box {index + 1}; refusing to risk losing Pokémon"
                )
            boxes.append(self._parse_box_region(region, index))
        return boxes

    def print_all_pokemon(self) -> None:
        for pokemon in self.party_pokemon:
            print(f"{pokemon.name} (#{pokemon.species}) - lvl {pokemon.level}")
        for box_number, box in enumerate(self.box_pokemon, start=1):
            for pokemon in box:
                print(f"Box {box_number}: {pokemon.name} (#{pokemon.species}) - lvl {pokemon.level}")

    def _serialize_party(self, pokemon_list: list[Pokemon]) -> bytes:
        if len(pokemon_list) > PARTY_CAPACITY:
            raise ValueError("A Generation I party cannot contain more than 6 Pokémon")
        data = bytearray(PARTY_SIZE)
        data[0] = len(pokemon_list)
        data[1:8] = b"\xFF" * 7
        for index, pokemon in enumerate(pokemon_list):
            record = _field_bytes(pokemon, "_gen1_party_record", PARTY_RECORD_SIZE)
            internal_species = getattr(pokemon, "_gen1_species_index", None)
            if internal_species is None:
                raise ValueError("Generation I Pokémon is missing its internal species index")
            if record[0] != internal_species:
                raise ValueError("Generation I party record species does not match its index")
            data[1 + index] = internal_species
            start = 8 + index * PARTY_RECORD_SIZE
            data[start:start + PARTY_RECORD_SIZE] = record
            ot_start = 0x110 + index * 11
            nick_start = 0x152 + index * 11
            data[ot_start:ot_start + 11] = _field_bytes(pokemon, "_gen1_ot_name_bytes", 11)
            data[nick_start:nick_start + 11] = _field_bytes(pokemon, "_gen1_nickname_bytes", 11)
        return bytes(data)

    def _serialize_box(self, pokemon_list: list[Pokemon]) -> bytes:
        if len(pokemon_list) > BOX_CAPACITY:
            raise ValueError("A Generation I PC box cannot contain more than 20 Pokémon")
        data = bytearray(BOX_SIZE)
        data[0] = len(pokemon_list)
        data[1:22] = b"\xFF" * 21
        for index, pokemon in enumerate(pokemon_list):
            record = _field_bytes(pokemon, "_gen1_box_record", BOX_RECORD_SIZE)
            internal_species = getattr(pokemon, "_gen1_species_index", None)
            if internal_species is None:
                raise ValueError("Generation I Pokémon is missing its internal species index")
            if record[0] != internal_species:
                raise ValueError("Generation I box record species does not match its index")
            data[1 + index] = internal_species
            start = BOX_DATA_START + index * BOX_RECORD_SIZE
            data[start:start + BOX_RECORD_SIZE] = record
            ot_start = BOX_OT_NAMES_OFFSET + index * 11
            nick_start = BOX_NICKNAMES_OFFSET + index * 11
            data[ot_start:ot_start + 11] = _field_bytes(pokemon, "_gen1_ot_name_bytes", 11)
            data[nick_start:nick_start + 11] = _field_bytes(pokemon, "_gen1_nickname_bytes", 11)
        return bytes(data)

    def _pokemon_layout_changed(self) -> bool:
        if self._party_signature(self.party_pokemon) != self._original_party_signature:
            return True
        if len(self.box_pokemon) != len(self._original_box_signatures):
            return True
        return any(
            self._party_signature(box) != original
            for box, original in zip(self.box_pokemon, self._original_box_signatures)
        )

    def update_checksums(self) -> None:
        self.save_bytes[MAIN_CHECKSUM_OFFSET] = _checksum(
            self.save_bytes[MAIN_DATA_START:MAIN_CHECKSUM_OFFSET]
        )
        for bank_base, checksum_offset in BANK_BOX_CHECKSUM_OFFSET.items():
            bank_end = checksum_offset
            self.save_bytes[checksum_offset] = _checksum(
                self.save_bytes[bank_base:bank_end]
            )
            for index in range(6):
                start = bank_base + index * BOX_SIZE
                end = start + BOX_SIZE
                self.save_bytes[checksum_offset + 1 + index] = _checksum(
                    self.save_bytes[start:end]
                )

    def write_save(self) -> str:
        """Write ``<input>.new`` without modifying the original file."""
        if len(self.save_bytes) != SAVE_SIZE:
            raise ValueError(f"Save data must be exactly {SAVE_SIZE} bytes")
        if len(self.box_pokemon) != len(BOX_OFFSETS):
            raise ValueError(f"Expected 12 PC boxes, got {len(self.box_pokemon)}")

        if self._pokemon_layout_changed():
            party = self._serialize_party(self.party_pokemon)
            self.save_bytes[PARTY_OFFSET:PARTY_OFFSET + PARTY_SIZE] = party

            serialized_boxes = []
            for index, box_pokemon in enumerate(self.box_pokemon):
                serialized = self._serialize_box(box_pokemon)
                offset = BOX_OFFSETS[index]
                self.save_bytes[offset:offset + BOX_SIZE] = serialized
                serialized_boxes.append(serialized)

            # Keep the live Current Box copy synchronized with its stored box.
            selected = self.save_bytes[CURRENT_BOX_NUMBER_OFFSET] & 0x7F
            if selected >= len(serialized_boxes):
                raise ValueError(f"Invalid selected PC box number: {selected}")
            current = serialized_boxes[selected]
            self.save_bytes[CURRENT_BOX_OFFSET:CURRENT_BOX_OFFSET + BOX_SIZE] = current
            self.update_checksums()

        output_path = f"{self.path}.new"
        temporary = f"{output_path}.tmp"
        with open(temporary, "wb") as handle:
            handle.write(self.save_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output_path)

        # Allow repeated writes from this instance without treating unchanged
        # Pokémon lists as edits on every subsequent call.
        self._original_party_signature = self._party_signature(self.party_pokemon)
        self._original_box_signatures = [self._party_signature(box) for box in self.box_pokemon]
        return output_path
