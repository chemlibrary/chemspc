"""Reader/writer for English Pokémon Gold, Silver, and Crystal saves.

The supported games use the 32 KiB English Generation II SRAM layout. The
``Gen2_Save`` class handles Gold/Silver; ``Crystal_Save`` applies Crystal's
slightly different party/current-box offsets and checksum/backup layout.
Writing always produces ``<input path>.new`` so the input file is preserved.
"""

from __future__ import annotations

import os
from typing import Sequence

from chempy.files import bytes_safe_write
from pokemon import Pokemon

SAVE_SIZE = 0x8000
PARTY_OFFSET = 0x288A
CRYSTAL_PARTY_OFFSET = 0x2865
PARTY_SIZE = 428
CURRENT_BOX_NUMBER_OFFSET = 0x2724
CRYSTAL_CURRENT_BOX_NUMBER_OFFSET = 0x2700
CURRENT_BOX_OFFSET = 0x2D6C
CRYSTAL_CURRENT_BOX_OFFSET = 0x2D10
BOX_CAPACITY = 20
BOX_RECORD_SIZE = 32
BOX_DATA_SIZE = 1102  # Stored box list, excluding the FF00 trailer.
BOX_SIZE = 1104       # Stored box list plus the FF00 trailer.
BOX_OFFSETS = tuple(
    [0x4000 + i * BOX_SIZE for i in range(7)]
    + [0x6000 + i * BOX_SIZE for i in range(7)]
)

# Gold/Silver copies five primary-save regions into non-contiguous backup
# locations. Each tuple is (primary start, inclusive primary end, backup start).
_GS_BACKUP_REGIONS = (
    (0x2009, 0x222E, 0x15C7),
    (0x222F, 0x23D8, 0x3D96),
    (0x23D9, 0x2855, 0x0C6B),
    (0x2856, 0x2889, 0x7E39),
    (0x288A, 0x2D68, 0x10E8),
)


def _write_checksum(save: bytearray, offset: int, value: int) -> None:
    save[offset:offset + 2] = (value & 0xFFFF).to_bytes(2, "little")


def _fixed_name_field(name: str) -> bytes:
    """Encode an English Gen II Pokémon/OT name into its 11-byte field.

    The first ten bytes contain text followed by 0x50 padding, and byte 11 is
    0xFF. 0xFF can also encode the digit '9' in the first ten bytes, so the
    decoder must exclude the final field byte from the text.
    """
    encoded = encode_gen2_text(name, add_terminator=False)
    if len(encoded) > 10:
        raise ValueError(
            f"Generation II names are limited to 10 encoded bytes: {name!r}"
        )
    return encoded + (b"\x50" * (10 - len(encoded))) + b"\xFF"


def _decode_name_field(data: bytes) -> str:
    if len(data) != 11:
        raise ValueError(
            f"Expected an 11-byte Generation II name field, got {len(data)}"
        )
    # Ignore the required final 0xFF: 0xFF within text may mean digit '9'.
    return decode_gen2_text(data[:10])


class Gen2_Save:
    """English Pokémon Gold/Silver save reader and writer."""

    game_name = "gold-silver"
    is_gold_silver = True
    party_offset = PARTY_OFFSET
    current_box_number_offset = CURRENT_BOX_NUMBER_OFFSET
    current_box_offset = CURRENT_BOX_OFFSET

    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.save_size = SAVE_SIZE
        # Retain the legacy attribute names for callers that use them.
        self.party_list_start_offset = self.party_offset
        self.party_ots_start_offset = 8 + (6 * 48)
        self.party_names_start_offset = self.party_ots_start_offset + (11 * 6)
        self.box_lists_start_offset = 0x4000
        self.save_bytes = bytearray()
        self.party_pokemon: list[Pokemon] = []
        self.box_pokemon: list[list[Pokemon]] = []

        if path is None:
            self.path = "./gen2-save.sav"
            return

        self.path = os.fspath(path)
        if not os.path.isfile(self.path):
            raise FileNotFoundError(f"Save file not found: {self.path}")

        with open(self.path, "rb") as file:
            raw = file.read(self.save_size)
        if len(raw) != self.save_size:
            raise ValueError(
                f"Expected a {self.save_size}-byte (32 KiB) save file, got {len(raw)} bytes"
            )

        self.save_bytes = bytearray(raw)
        self.party_pokemon = self.extract_gen2_party_pokemon()
        self.box_pokemon = self.extract_gen2_pokemon_boxes()

    def update_gold_silver_checksums(self) -> bool:
        """Update English Gold/Silver primary and secondary checksums."""
        if len(self.save_bytes) != SAVE_SIZE:
            raise ValueError(f"Save data must be exactly {SAVE_SIZE} bytes")

        # Primary: 0x2009..0x2D68 inclusive; checksum at 0x2D69.
        primary_checksum = sum(self.save_bytes[0x2009:0x2D69]) & 0xFFFF
        _write_checksum(self.save_bytes, 0x2D69, primary_checksum)

        # Gold/Silver secondary checksum spans its mapped backup regions.
        secondary_checksum = (
            sum(self.save_bytes[0x0C6B:0x17ED])
            + sum(self.save_bytes[0x3D96:0x3F40])
            + sum(self.save_bytes[0x7E39:0x7E6D])
        ) & 0xFFFF
        _write_checksum(self.save_bytes, 0x7E6D, secondary_checksum)
        return True

    def _sync_gold_silver_backup(self) -> None:
        """Copy each primary region to its corresponding secondary region."""
        for primary_start, primary_end, backup_start in _GS_BACKUP_REGIONS:
            region = bytes(self.save_bytes[primary_start:primary_end + 1])
            expected_length = primary_end - primary_start + 1
            if len(region) != expected_length:
                raise ValueError(
                    "Save data is truncated while synchronizing backup data"
                )
            self.save_bytes[backup_start:backup_start + expected_length] = region

    def _finalize_save(self) -> None:
        self._sync_gold_silver_backup()
        self.update_gold_silver_checksums()

    def print_all_pokemon(self) -> None:
        for pokemon in self.party_pokemon:
            print(f"{pokemon.name} (#{pokemon.species}) - lvl {pokemon.level}")
        for box_number, box in enumerate(self.box_pokemon, start=1):
            for pokemon in box:
                print(
                    f"Box {box_number}: {pokemon.name} "
                    f"(#{pokemon.species}) - lvl {pokemon.level}"
                )

    def write_save(self, gold_silver: bool | None = None):
        """Serialize this save to ``<input path>.new``.

        ``gold_silver`` is accepted for compatibility with the previous API.
        When supplied, it must agree with the concrete save class being used.
        """
        if gold_silver is not None and gold_silver != self.is_gold_silver:
            requested = "Gold/Silver" if gold_silver else "Crystal"
            raise ValueError(
                f"Cannot write this {self.game_name} save using the {requested} layout"
            )
        if len(self.save_bytes) != SAVE_SIZE:
            raise ValueError(f"Save data must be exactly {SAVE_SIZE} bytes")
        if len(self.party_pokemon) > 6:
            raise ValueError("A Generation II party cannot contain more than 6 Pokémon")
        if len(self.box_pokemon) != 14:
            raise ValueError(f"Expected 14 PC boxes, got {len(self.box_pokemon)}")

        party_bytes = self.export_gen2_party_list()
        if len(party_bytes) != PARTY_SIZE:
            raise ValueError(
                f"Party serialization produced {len(party_bytes)} bytes, "
                f"expected {PARTY_SIZE}"
            )
        self.save_bytes[self.party_offset:self.party_offset + PARTY_SIZE] = party_bytes

        all_box_bytes = self.export_gen2_boxes()
        expected_box_bytes = len(BOX_OFFSETS) * BOX_SIZE
        if len(all_box_bytes) != expected_box_bytes:
            raise ValueError(
                f"Box serialization produced {len(all_box_bytes)} bytes, "
                f"expected {expected_box_bytes}"
            )

        # Write every box to its actual address; do not compact the gap between
        # boxes 7 and 8 or shift the rest of the save file.
        for index, offset in enumerate(BOX_OFFSETS):
            start = index * BOX_SIZE
            box_bytes = all_box_bytes[start:start + BOX_SIZE]
            self.save_bytes[offset:offset + BOX_SIZE] = box_bytes

        # The Current Box is a separate live copy of the selected PC box.
        current_box = self.save_bytes[self.current_box_number_offset] & 0x0F
        if current_box >= len(self.box_pokemon):
            raise ValueError(f"Invalid current PC box index: {current_box}")
        selected_start = current_box * BOX_SIZE
        selected_box = all_box_bytes[selected_start:selected_start + BOX_SIZE]
        self.save_bytes[
            self.current_box_offset:self.current_box_offset + BOX_DATA_SIZE
        ] = selected_box[:BOX_DATA_SIZE]

        self._finalize_save()

        output_path = f"{self.path}.new"
        bytes_safe_write(path=output_path, contents=self.save_bytes)
        return output_path

    @staticmethod
    def _serialize_box(box: Sequence[Pokemon]) -> bytes:
        if len(box) > BOX_CAPACITY:
            raise ValueError(
                f"A Generation II PC box cannot contain more than {BOX_CAPACITY} Pokémon"
            )

        count = len(box)
        species = bytearray(pokemon.species for pokemon in box)
        species.append(0xFF)
        species.extend(b"\x00" * (BOX_CAPACITY - count))

        pokemon_data = bytearray()
        ot_names = bytearray()
        nicknames = bytearray()
        for pokemon in box:
            record = pokemon.export_gen2(party_pokemon=False)
            if len(record) != BOX_RECORD_SIZE:
                raise ValueError(
                    f"Box Pokémon record must be {BOX_RECORD_SIZE} bytes, got {len(record)}"
                )
            pokemon_data.extend(record)
            ot_names.extend(_fixed_name_field(pokemon.original_trainer_name))
            nicknames.extend(_fixed_name_field(pokemon.name))

        missing = BOX_CAPACITY - count
        pokemon_data.extend(b"\x00" * (missing * BOX_RECORD_SIZE))
        ot_names.extend(b"\x00" * (missing * 11))
        nicknames.extend(b"\x00" * (missing * 11))

        serialized = (
            bytes([count])
            + bytes(species)
            + bytes(pokemon_data)
            + bytes(ot_names)
            + bytes(nicknames)
            + b"\xFF\x00"
        )
        if len(serialized) != BOX_SIZE:
            raise ValueError(
                f"Serialized PC box has invalid size {len(serialized)} "
                f"(expected {BOX_SIZE})"
            )
        return serialized

    def export_gen2_party_list(self) -> bytes:
        if len(self.party_pokemon) > 6:
            raise ValueError("A Generation II party cannot contain more than 6 Pokémon")

        count = len(self.party_pokemon)
        species = bytearray(pokemon.species for pokemon in self.party_pokemon)
        species.append(0xFF)
        species.extend(b"\x00" * (6 - count))

        pokemon_data = bytearray()
        ot_names = bytearray()
        nicknames = bytearray()
        for pokemon in self.party_pokemon:
            record = pokemon.export_gen2(party_pokemon=True)
            if len(record) != 48:
                raise ValueError(
                    f"Party Pokémon record must be 48 bytes, got {len(record)}"
                )
            pokemon_data.extend(record)
            ot_names.extend(_fixed_name_field(pokemon.original_trainer_name))
            nicknames.extend(_fixed_name_field(pokemon.name))

        missing = 6 - count
        pokemon_data.extend(b"\x00" * (missing * 48))
        ot_names.extend(b"\x00" * (missing * 11))
        nicknames.extend(b"\x00" * (missing * 11))

        party = (
            bytes([count]) + bytes(species) + bytes(pokemon_data)
            + bytes(ot_names) + bytes(nicknames)
        )
        if len(party) != PARTY_SIZE:
            raise ValueError(
                f"Serialized party has invalid size {len(party)} "
                f"(expected {PARTY_SIZE})"
            )
        return party

    def export_gen2_boxes(self) -> bytes:
        """Return the 14 fixed-size box records in logical box-number order."""
        if len(self.box_pokemon) != 14:
            raise ValueError(f"Expected 14 PC boxes, got {len(self.box_pokemon)}")
        return b"".join(self._serialize_box(box) for box in self.box_pokemon)

    def read_gen2_save(self, path: str | os.PathLike[str]) -> bytes:
        with open(path, "rb") as file:
            data = file.read(SAVE_SIZE)
        if len(data) != SAVE_SIZE:
            raise ValueError(f"Expected a {SAVE_SIZE}-byte save file, got {len(data)} bytes")
        return data

    def extract_gen2_party_pokemon(self) -> list[Pokemon]:
        party = self.save_bytes[self.party_offset:self.party_offset + PARTY_SIZE]
        if len(party) != PARTY_SIZE:
            raise ValueError("Save data does not contain a complete party structure")
        count = party[0]
        if count > 6:
            raise ValueError(f"Invalid party count: {count}")

        result: list[Pokemon] = []
        for index in range(count):
            record_start = 8 + index * 48
            pokemon = Pokemon()
            pokemon.init_gen2(
                data=party[record_start:record_start + 48], party_pokemon=True
            )
            ot_start = self.party_ots_start_offset + index * 11
            name_start = self.party_names_start_offset + index * 11
            pokemon.original_trainer_name = _decode_name_field(
                party[ot_start:ot_start + 11]
            )
            pokemon.name = _decode_name_field(party[name_start:name_start + 11])
            result.append(pokemon)
        return result

    @staticmethod
    def _extract_box(data: bytes | bytearray, offset: int) -> list[Pokemon]:
        box = data[offset:offset + BOX_DATA_SIZE]
        if len(box) != BOX_DATA_SIZE:
            raise ValueError(f"Incomplete PC box data at offset 0x{offset:04X}")
        count = box[0]
        if count > BOX_CAPACITY:
            raise ValueError(
                f"Invalid Pokémon count {count} in PC box at 0x{offset:04X}"
            )

        ot_start = 22 + BOX_CAPACITY * BOX_RECORD_SIZE
        names_start = ot_start + BOX_CAPACITY * 11
        result: list[Pokemon] = []
        for index in range(count):
            record_start = 22 + index * BOX_RECORD_SIZE
            record = box[record_start:record_start + BOX_RECORD_SIZE]
            pokemon = Pokemon()
            pokemon.init_gen2(data=record, party_pokemon=False)
            if pokemon.species == 0:
                continue
            ot_field_start = ot_start + index * 11
            name_field_start = names_start + index * 11
            pokemon.original_trainer_name = _decode_name_field(
                box[ot_field_start:ot_field_start + 11]
            )
            pokemon.name = _decode_name_field(
                box[name_field_start:name_field_start + 11]
            )
            result.append(pokemon)
        return result

    def extract_gen2_pokemon_boxes(self) -> list[list[Pokemon]]:
        if len(self.save_bytes) != SAVE_SIZE:
            raise ValueError(f"Save data must be exactly {SAVE_SIZE} bytes")

        boxes = [self._extract_box(self.save_bytes, offset) for offset in BOX_OFFSETS]

        # The live Current Box can be newer than the numbered box copy.
        current_box = self.save_bytes[self.current_box_number_offset] & 0x0F
        if current_box >= len(BOX_OFFSETS):
            raise ValueError(f"Invalid current PC box index: {current_box}")
        boxes[current_box] = self._extract_box(
            self.save_bytes, self.current_box_offset
        )
        return boxes


class Crystal_Save(Gen2_Save):
    """Reader/writer for English Pokémon Crystal save files."""

    game_name = "crystal"
    is_gold_silver = False
    party_offset = CRYSTAL_PARTY_OFFSET
    current_box_number_offset = CRYSTAL_CURRENT_BOX_NUMBER_OFFSET
    current_box_offset = CRYSTAL_CURRENT_BOX_OFFSET

    def update_crystal_checksums(self) -> bool:
        """Synchronize Crystal's contiguous backup and calculate both checksums.

        Crystal's primary data region 0x2009..0x2B82 is copied byte-for-byte
        to 0x1209..0x1D82. The checksum words are little-endian at 0x2D0D and
        0x1F0D. Each copy also has its own save magic bytes.
        """
        if len(self.save_bytes) != SAVE_SIZE:
            raise ValueError(f"Save data must be exactly {SAVE_SIZE} bytes")

        primary = bytes(self.save_bytes[0x2009:0x2B83])
        if len(primary) != 0x2B83 - 0x2009:
            raise ValueError("Save data is truncated while synchronizing Crystal backup")
        self.save_bytes[0x1209:0x1D83] = primary

        primary_checksum = sum(self.save_bytes[0x2009:0x2B83]) & 0xFFFF
        secondary_checksum = sum(self.save_bytes[0x1209:0x1D83]) & 0xFFFF
        _write_checksum(self.save_bytes, 0x2D0D, primary_checksum)
        _write_checksum(self.save_bytes, 0x1F0D, secondary_checksum)

        # Save-magic values tell English Crystal that both copies are present.
        self.save_bytes[0x2008] = 0x63
        self.save_bytes[0x2D0F] = 0x7F
        self.save_bytes[0x1208] = 0x63
        self.save_bytes[0x1F0F] = 0x7F
        return True

    def _finalize_save(self) -> None:
        self.update_crystal_checksums()


# Friendly alternative spelling for callers that prefer explicit game names.
Gen2_Crystal_Save = Crystal_Save


def decode_gen2_text(data: bytes, *, stop_at_terminator: bool = True) -> str:
    """Decode the subset of English Generation II text used by this project."""
    chars: dict[int, str] = {}
    chars.update({0x80 + i: chr(ord("A") + i) for i in range(26)})
    chars.update({0xA0 + i: chr(ord("a") + i) for i in range(26)})
    chars.update({0xF6 + i: str(i) for i in range(10)})
    chars.update({
        0x7F: " ", 0xE3: "-", 0x9A: "(", 0x9B: ")", 0x9C: ":",
        0x9D: ";", 0x9E: "[", 0x9F: "]", 0xE0: "'", 0xE6: "?",
        0xE7: "!", 0xE8: ".", 0xE9: "&", 0xEA: "é", 0xF1: "×",
        0xF2: ".", 0xF3: "/", 0xF4: ",", 0xF5: "♀", 0xEF: "♂",
    })
    result: list[str] = []
    for byte in data:
        if byte == 0x50:
            if stop_at_terminator:
                break
            continue
        if byte == 0x4F:
            result.append("\n")
        else:
            result.append(chars.get(byte, f"[{byte:02X}]"))
    return "".join(result)


def encode_gen2_text(text: str, *, add_terminator: bool = True) -> bytes:
    """Encode the subset of English Generation II text used by this project."""
    chars = {
        " ": 0x7F, "-": 0xE3, "(": 0x9A, ")": 0x9B, ":": 0x9C,
        ";": 0x9D, "[": 0x9E, "]": 0x9F, "'": 0xE0, "?": 0xE6,
        "!": 0xE7, ".": 0xE8, "&": 0xE9, "é": 0xEA, "♂": 0xEF,
        "×": 0xF1, "/": 0xF3, ",": 0xF4, "♀": 0xF5, "\n": 0x4F,
    }
    chars.update({chr(ord("A") + i): 0x80 + i for i in range(26)})
    chars.update({chr(ord("a") + i): 0xA0 + i for i in range(26)})
    chars.update({str(i): 0xF6 + i for i in range(10)})

    encoded = bytearray()
    for char in text:
        if char not in chars:
            raise ValueError(
                f"Character not supported by the English Generation II encoder: {char!r}"
            )
        encoded.append(chars[char])
    if add_terminator:
        encoded.append(0x50)
    return bytes(encoded)
