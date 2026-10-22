"""English Pokémon Gold/Silver save-file reader and writer (32 KiB saves)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pokemon import Pokemon

SAVE_SIZE = 32768
PARTY_START = 10378
PARTY_SIZE = 428
BOX_START = 0x4000
BOX_COUNT = 14
BOX_SIZE = 1104
BOX_DATA_SIZE = BOX_SIZE - 2
BOX_SEGMENT_SIZE = BOX_COUNT * BOX_SIZE
BOX_OFFSETS = tuple(
    [0x4000 + i * BOX_SIZE for i in range(7)]
    + [0x6000 + i * BOX_SIZE for i in range(7)]
)
CURRENT_BOX_NUMBER_OFFSET = 0x2724
CURRENT_BOX_OFFSET = 0x2D6C
CRYSTAL_PARTY_START = 0x2865
CRYSTAL_CURRENT_BOX_NUMBER_OFFSET = 0x2700
CRYSTAL_CURRENT_BOX_OFFSET = 0x2D10
PARTY_LIMIT = 6
BOX_LIMIT = 20
_GS_BACKUP_REGIONS = (
    (0x2009, 0x222E, 0x15C7),
    (0x222F, 0x23D8, 0x3D96),
    (0x23D9, 0x2855, 0x0C6B),
    (0x2856, 0x2889, 0x7E39),
    (0x288A, 0x2D68, 0x10E8),
)


class Gen2_Save:
    """Read and modify English Pokémon Gold/Silver saves.

    Save writes use the retail box banks and checksum/backup locations. The
    source is never overwritten; output goes to an explicit path or ``.new``.
    """
    game_name = "gold-silver"
    is_gold_silver = True
    party_offset = PARTY_START
    current_box_number_offset = CURRENT_BOX_NUMBER_OFFSET
    current_box_offset = CURRENT_BOX_OFFSET

    def __init__(self, path: str | os.PathLike | None = None):
        self.save_size = SAVE_SIZE
        self.party_list_start_offset = self.party_offset
        self.party_ots_start_offset = 8 + (6 * 48)
        self.party_names_start_offset = self.party_ots_start_offset + (11 * 6)
        self.box_lists_start_offset = BOX_START
        self.box_offsets = BOX_OFFSETS
        self.party_pokemon: list[Pokemon] = []
        self.box_pokemon: list[list[Pokemon]] = [[] for _ in range(BOX_COUNT)]
        self.save_bytes = bytearray(SAVE_SIZE)
        self.path = str(path) if path is not None else "./gen2-save.sav"
        if path is not None:
            source = Path(path)
            if not source.is_file():
                raise FileNotFoundError(f"Save file not found: {source}")
            raw = source.read_bytes()
            if len(raw) != SAVE_SIZE:
                raise ValueError(
                    f"Unsupported save size: expected exactly {SAVE_SIZE:,} bytes for an English Gold/Silver save, "
                    f"received {len(raw):,} bytes. Make a raw 32 KiB .sav backup first."
                )
            self.save_bytes = bytearray(raw)
            self.party_pokemon = self.extract_gen2_party_pokemon()
            self.box_pokemon = self.extract_gen2_pokemon_boxes()

    def read_gen2_save(self, path: str | os.PathLike) -> bytes:
        """Read an exact-size English Gold/Silver save image from disk."""
        raw = Path(path).read_bytes()
        if len(raw) != SAVE_SIZE:
            raise ValueError(f"Expected a {SAVE_SIZE:,}-byte Gold/Silver save, received {len(raw):,} bytes")
        return raw

    def print_all_pokemon(self) -> None:
        for pokemon in self.party_pokemon:
            print(f"{pokemon.name} (#{pokemon.species}) - lvl {pokemon.level}")
        for box_no, box in enumerate(self.box_pokemon, start=1):
            for slot_no, pokemon in enumerate(box, start=1):
                print(f"Box {box_no}, slot {slot_no}: {pokemon.name} (#{pokemon.species}) - lvl {pokemon.level}")

    def extract_gen2_party_pokemon(self) -> list[Pokemon]:
        start = self.party_list_start_offset
        region = self.save_bytes[start:start + PARTY_SIZE]
        if len(region) != PARTY_SIZE:
            raise ValueError("Save is too short to contain the Generation II party data")
        count = region[0]
        if count > PARTY_LIMIT:
            raise ValueError(f"Invalid party count ({count}); expected 0-{PARTY_LIMIT}")
        results = []
        data_start = 8
        ots_start = 8 + 6 * 48
        names_start = ots_start + 6 * 11
        for index in range(count):
            data = region[data_start + index * 48:data_start + (index + 1) * 48]
            pokemon = Pokemon()
            pokemon.init_gen2(data, party_pokemon=True)
            pokemon.original_trainer_name = decode_gen2_text(region[ots_start + index * 11:ots_start + (index + 1) * 11])
            pokemon.name = decode_gen2_text(region[names_start + index * 11:names_start + (index + 1) * 11])
            results.append(pokemon)
        return results

    @staticmethod
    def _parse_box_bytes(box: bytes | bytearray, box_number: int) -> list[Pokemon]:
        if len(box) < BOX_DATA_SIZE:
            raise ValueError(f"PC box {box_number} data is incomplete")
        count = box[0]
        if count > BOX_LIMIT:
            raise ValueError(f"Invalid Pokémon count ({count}) in box {box_number}")
        ots_start = 22 + BOX_LIMIT * 32
        names_start = ots_start + BOX_LIMIT * 11
        contents: list[Pokemon] = []
        for slot_index in range(count):
            data = box[22 + slot_index * 32:22 + (slot_index + 1) * 32]
            pokemon = Pokemon()
            pokemon.init_gen2(data, party_pokemon=False)
            if pokemon.species == 0:
                continue
            pokemon.original_trainer_name = decode_gen2_text(
                box[ots_start + slot_index * 11:ots_start + (slot_index + 1) * 11]
            )
            pokemon.name = decode_gen2_text(
                box[names_start + slot_index * 11:names_start + (slot_index + 1) * 11]
            )
            contents.append(pokemon)
        return contents

    def extract_gen2_pokemon_boxes(self) -> list[list[Pokemon]]:
        boxes: list[list[Pokemon]] = []
        for box_index, offset in enumerate(self.box_offsets):
            raw = self.save_bytes[offset:offset + BOX_SIZE]
            if len(raw) != BOX_SIZE:
                raise ValueError(f"Save is too short to contain PC box {box_index + 1}")
            boxes.append(self._parse_box_bytes(raw, box_index + 1))
        current_box = self.save_bytes[self.current_box_number_offset] & 0x0F
        if current_box >= BOX_COUNT:
            raise ValueError(f"Invalid current PC box index: {current_box}")
        live = self.save_bytes[self.current_box_offset:self.current_box_offset + BOX_DATA_SIZE]
        if len(live) == BOX_DATA_SIZE:
            boxes[current_box] = self._parse_box_bytes(live, current_box + 1)
        return boxes

    def export_gen2_party_list(self) -> bytearray:
        if len(self.party_pokemon) > PARTY_LIMIT:
            raise ValueError("A Generation II party cannot contain more than 6 Pokémon")
        section = bytearray([len(self.party_pokemon)])
        species = bytearray(p.species for p in self.party_pokemon)
        species.append(0xFF)
        species.extend(bytearray(7 - len(species)))
        section.extend(species)
        for pokemon in self.party_pokemon:
            section.extend(pokemon.export_gen2(party_pokemon=True))
        section.extend(bytearray((PARTY_LIMIT - len(self.party_pokemon)) * 48))
        # Gold/Silver store OT names before nicknames in the party structure.
        for pokemon in self.party_pokemon:
            section.extend(encode_gen2_name(pokemon.original_trainer_name, width=11, max_chars=7))
        section.extend(bytearray((PARTY_LIMIT - len(self.party_pokemon)) * 11))
        for pokemon in self.party_pokemon:
            section.extend(encode_gen2_name(pokemon.name, width=11, max_chars=10))
        section.extend(bytearray((PARTY_LIMIT - len(self.party_pokemon)) * 11))
        if len(section) != PARTY_SIZE:
            raise AssertionError(f"Party section must be {PARTY_SIZE} bytes, got {len(section)}")
        return section

    def export_gen2_boxes(self) -> bytearray:
        if len(self.box_pokemon) != BOX_COUNT:
            raise ValueError(f"Expected {BOX_COUNT} storage boxes")
        result = bytearray()
        for box_index, contents in enumerate(self.box_pokemon, start=1):
            if len(contents) > BOX_LIMIT:
                raise ValueError(f"Box {box_index} contains more than {BOX_LIMIT} Pokémon")
            box = bytearray([len(contents)])
            species = bytearray(p.species for p in contents)
            species.append(0xFF)
            species.extend(bytearray(21 - len(species)))
            box.extend(species)
            for pokemon in contents:
                box.extend(pokemon.export_gen2(party_pokemon=False))
            box.extend(bytearray((BOX_LIMIT - len(contents)) * 32))
            # Box name blocks are OT names first, then Pokémon nicknames.
            for pokemon in contents:
                box.extend(encode_gen2_name(pokemon.original_trainer_name, width=11, max_chars=7))
            box.extend(bytearray((BOX_LIMIT - len(contents)) * 11))
            for pokemon in contents:
                box.extend(encode_gen2_name(pokemon.name, width=11, max_chars=10))
            box.extend(bytearray((BOX_LIMIT - len(contents)) * 11))
            box.extend((0xFF, 0x00))
            if len(box) != BOX_SIZE:
                raise AssertionError(f"Box section must be {BOX_SIZE} bytes, got {len(box)}")
            result.extend(box)
        if len(result) != BOX_SEGMENT_SIZE:
            raise AssertionError(f"Box storage must be {BOX_SEGMENT_SIZE} bytes, got {len(result)}")
        return result

    def update_gold_silver_checksums(self) -> bool:
        for primary_start, primary_end, backup_start in _GS_BACKUP_REGIONS:
            self.save_bytes[backup_start:backup_start + primary_end - primary_start + 1] = self.save_bytes[primary_start:primary_end + 1]
        primary = sum(self.save_bytes[0x2009:0x2D69]) & 0xFFFF
        secondary = (
            sum(self.save_bytes[0x0C6B:0x17ED])
            + sum(self.save_bytes[0x3D96:0x3F40])
            + sum(self.save_bytes[0x7E39:0x7E6D])
        ) & 0xFFFF
        self.save_bytes[0x2D69:0x2D6B] = primary.to_bytes(2, "little")
        self.save_bytes[0x7E6D:0x7E6F] = secondary.to_bytes(2, "little")
        return True

    def _finalize_checksums(self) -> None:
        self.update_gold_silver_checksums()

    def write_save(self, path: str | os.PathLike | None = None, gold_silver: bool | None = None) -> str:
        """Write a new save image and return its path; never overwrite the source."""
        if gold_silver is not None and bool(gold_silver) != bool(self.is_gold_silver):
            raise ValueError(f"Cannot write this {self.game_name} save using the requested Generation II layout")
        party = self.export_gen2_party_list()
        boxes = self.export_gen2_boxes()
        self.save_bytes[self.party_list_start_offset:self.party_list_start_offset + PARTY_SIZE] = party
        for index, offset in enumerate(self.box_offsets):
            start = index * BOX_SIZE
            self.save_bytes[offset:offset + BOX_SIZE] = boxes[start:start + BOX_SIZE]
        current_box = self.save_bytes[self.current_box_number_offset] & 0x0F
        if current_box >= BOX_COUNT:
            raise ValueError(f"Invalid current PC box index: {current_box}")
        current_start = current_box * BOX_SIZE
        current_bytes = boxes[current_start:current_start + BOX_DATA_SIZE]
        self.save_bytes[self.current_box_offset:self.current_box_offset + BOX_DATA_SIZE] = current_bytes
        self._finalize_checksums()
        destination = Path(path) if path is not None else Path(f"{self.path}.new")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(self.save_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, destination)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
        return str(destination)


def encode_gen2_name(text: str, width: int, max_chars: int) -> bytes:
    """Encode one fixed-width name field without allowing adjacent fields to shift."""
    value = str(text or "")
    if len(value) > max_chars:
        raise ValueError(f"Name {value!r} is longer than the {max_chars}-character Gen II limit")
    encoded = encode_gen2_text(value, add_terminator=True)
    if len(encoded) > width:
        raise ValueError(f"Encoded name {value!r} is too long for a {width}-byte field")
    return encoded + bytes([0x50]) * (width - len(encoded))


def decode_gen2_text(data: bytes | bytearray, *, stop_at_terminator: bool = True) -> str:
    """Decode English Generation II text bytes."""
    chars: dict[int, str] = {}
    chars.update({0x80 + i: chr(ord("A") + i) for i in range(26)})
    chars.update({0xA0 + i: chr(ord("a") + i) for i in range(26)})
    chars.update({0xF6 + i: str(i) for i in range(10)})
    chars.update({
        0x7F: " ", 0xE3: "-", 0x9A: "(", 0x9B: ")", 0x9C: ":", 0x9D: ";",
        0x9E: "[", 0x9F: "]", 0xE0: "'", 0xE6: "?", 0xE7: "!", 0xE8: ".",
        0xE9: "&", 0xEA: "é", 0xF1: "×", 0xF2: ".", 0xF3: "/", 0xF4: ",",
        0xF5: "♀", 0xEF: "♂",
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
    """Encode the English character set used by Generation II games."""
    chars = {
        " ": 0x7F, "-": 0xE3, "(": 0x9A, ")": 0x9B, ":": 0x9C, ";": 0x9D,
        "[": 0x9E, "]": 0x9F, "'": 0xE0, "?": 0xE6, "!": 0xE7, ".": 0xE8,
        "&": 0xE9, "é": 0xEA, "♂": 0xEF, "×": 0xF1, "/": 0xF3, ",": 0xF4,
        "♀": 0xF5, "\n": 0x4F,
    }
    chars.update({chr(ord("A") + i): 0x80 + i for i in range(26)})
    chars.update({chr(ord("a") + i): 0xA0 + i for i in range(26)})
    chars.update({str(i): 0xF6 + i for i in range(10)})
    encoded = bytearray()
    for char in text:
        if char not in chars:
            raise ValueError(f"Character not supported in English Gen II text: {char!r}")
        encoded.append(chars[char])
    if add_terminator:
        encoded.append(0x50)
    return bytes(encoded)


class Crystal_Save(Gen2_Save):
    """Reader/writer for English Pokémon Crystal saves (distinct Gen II layout)."""
    game_name = "crystal"
    is_gold_silver = False
    party_offset = CRYSTAL_PARTY_START
    current_box_number_offset = CRYSTAL_CURRENT_BOX_NUMBER_OFFSET
    current_box_offset = CRYSTAL_CURRENT_BOX_OFFSET

    def update_crystal_checksums(self) -> bool:
        primary = bytes(self.save_bytes[0x2009:0x2B83])
        if len(primary) != 0x2B83 - 0x2009:
            raise ValueError("Save data is truncated while synchronizing Crystal backup data")
        self.save_bytes[0x1209:0x1D83] = primary
        self.save_bytes[0x2D0D:0x2D0F] = (sum(self.save_bytes[0x2009:0x2B83]) & 0xFFFF).to_bytes(2, "little")
        self.save_bytes[0x1F0D:0x1F0F] = (sum(self.save_bytes[0x1209:0x1D83]) & 0xFFFF).to_bytes(2, "little")
        self.save_bytes[0x2008] = 0x63
        self.save_bytes[0x2D0F] = 0x7F
        self.save_bytes[0x1208] = 0x63
        self.save_bytes[0x1F0F] = 0x7F
        return True

    def _finalize_checksums(self) -> None:
        self.update_crystal_checksums()
