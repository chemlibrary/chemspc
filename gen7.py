"""Reader/writer for decrypted Generation VII 3DS Pokémon save files.

Supported titles: Pokémon Sun, Moon, Ultra Sun, and Ultra Moon.
Pokémon: Let's Go, Pikachu! / Let's Go, Eevee! are intentionally excluded.

The input must be a decrypted PKHeX-compatible ``main`` save dump, not the
console-encrypted outer 3DS save container. SM saves are 0x6BE00 bytes and
USUM saves are 0x6CC00 bytes. Generation VII PK7 data uses the same 232-byte
stored and 260-byte party record sizes and record encryption as Generation VI.

This module supports extracting and clearing existing party/PC Pokémon. It
preserves retained Pokémon's original encrypted records and does not create
new records or encode arbitrary edits to Pokémon fields.

Format references:
  https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV7.cs
  https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV7SM.cs
  https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/SAV7USUM.cs
  https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/Access/SaveBlockAccessor7SM.cs
  https://github.com/kwsch/PKHeX/blob/master/PKHeX.Core/Saves/Access/SaveBlockAccessor7USUM.cs
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
from gen6 import _parse_pokemon as _parse_gen6_pokemon, decrypt_gen6_record
from pokemon import Pokemon

SM_SAVE_SIZE = 0x6BE00
USUM_SAVE_SIZE = 0x6CC00
PARTY_CAPACITY = 6
PARTY_RECORD_SIZE = 0x104       # 260 bytes (PK7 + party stats)
BOX_COUNT = 32
BOX_CAPACITY = 30
BOX_RECORD_SIZE = 0xE8          # 232 bytes (stored PK7)
PARTY_BLOCK_LENGTH = 0x61C
BOX_BLOCK_LENGTH = BOX_COUNT * BOX_CAPACITY * BOX_RECORD_SIZE  # 0x36600
BLOCK_INFO_HEADER_LENGTH = 0x14
FOOTER_SIZE = 0x200
BEEF_MAGIC = 0x42454546         # uint32 read little-endian: bytes b"FEEB"

PROFILES = {
    "sun": {
        "family": "sm", "size": SM_SAVE_SIZE, "party_offset": 0x1400,
        "box_offset": 0x4E00, "party_block_id": 4, "box_block_id": 14,
        "version_id": 30,
    },
    "moon": {
        "family": "sm", "size": SM_SAVE_SIZE, "party_offset": 0x1400,
        "box_offset": 0x4E00, "party_block_id": 4, "box_block_id": 14,
        "version_id": 31,
    },
    "ultrasun": {
        "family": "usum", "size": USUM_SAVE_SIZE, "party_offset": 0x1600,
        "box_offset": 0x5200, "party_block_id": 4, "box_block_id": 14,
        "version_id": 32,
    },
    "ultramoon": {
        "family": "usum", "size": USUM_SAVE_SIZE, "party_offset": 0x1600,
        "box_offset": 0x5200, "party_block_id": 4, "box_block_id": 14,
        "version_id": 33,
    },
}

GAME_ALIASES = {
    "sun": "sun", "pokemon sun": "sun", "pokémon sun": "sun",
    "moon": "moon", "pokemon moon": "moon", "pokémon moon": "moon",
    "ultrasun": "ultrasun", "ultra-sun": "ultrasun", "ultra sun": "ultrasun",
    "pokemon ultra sun": "ultrasun", "pokémon ultra sun": "ultrasun",
    "ultramoon": "ultramoon", "ultra-moon": "ultramoon", "ultra moon": "ultramoon",
    "pokemon ultra moon": "ultramoon", "pokémon ultra moon": "ultramoon",
}


def _u16(data: bytes | bytearray, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


def _u32(data: bytes | bytearray, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    data[offset:offset + 2] = (int(value) & 0xFFFF).to_bytes(2, "little")


def _put_u32(data: bytearray, offset: int, value: int) -> None:
    data[offset:offset + 4] = (int(value) & 0xFFFFFFFF).to_bytes(4, "little")


def decrypt_gen7_record(record: bytes) -> bytes:
    """Decrypt and checksum-validate a Generation VII PK7 record.

    PK7 has the same stored/party sizes and EC-seeded XOR/block-shuffle scheme
    as PK6. Reuse the common implementation, but report Gen VII in any errors.
    """
    if len(record) not in (BOX_RECORD_SIZE, PARTY_RECORD_SIZE):
        raise ValueError(
            f"Expected a 232- or 260-byte Generation VII record, got {len(record)}"
        )
    try:
        return decrypt_gen6_record(record)
    except ValueError as exc:
        raise ValueError(str(exc).replace("Generation VI", "Generation VII")) from exc


def _parse_pokemon(
    record: bytes,
    *,
    game_name: str,
    party: bool,
    party_slot: int | None = None,
    box_index: int | None = None,
    box_slot: int | None = None,
) -> Pokemon | None:
    """Parse common PK6/PK7 payload fields and tag the record as Generation VII."""
    # PK6 and PK7 share the core record layout. Reuse the field parser, then
    # assign Gen VII provenance/slot attributes for this writer.
    try:
        pokemon = _parse_gen6_pokemon(
            record,
            game_name=game_name,
            party=party,
            party_slot=party_slot,
            box_index=box_index,
            box_slot=box_slot,
        )
    except ValueError as exc:
        raise ValueError(str(exc).replace("Generation VI", "Generation VII")) from exc
    if pokemon is None:
        return None
    pokemon.generation = 7
    pokemon.game_name = game_name
    pokemon.gen7_record = bytes(record)
    pokemon.gen7_party_slot = party_slot
    pokemon.gen7_box_index = box_index
    pokemon.gen7_box_slot = box_slot
    # gen6_record and gen6 slot markers are retained only for compatibility
    # with the shared parser; Gen7_Save only trusts the gen7_* attributes.
    return pokemon


class Gen7_Save:
    """Read/write decrypted Pokémon Sun/Moon/USUM saves for extraction.

    ``game`` must be one of ``sun``, ``moon``, ``ultrasun`` or ``ultramoon``.
    Retained Pokémon records must stay in their original boxes/slots. Party
    records may be compacted in list order, which supports removing party slots.
    """
    generation = 7

    def __init__(self, path: str | os.PathLike[str] | None = None, *, game: str = "sun"):
        self.path = os.fspath(path) if path is not None else "./gen7-save.main"
        normalized = str(game).strip().lower().replace("_", "-")
        if normalized not in GAME_ALIASES:
            raise ValueError("Choose sun, moon, ultrasun, or ultramoon")
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
    def party_offset(self) -> int:
        return self.profile["party_offset"]

    @property
    def box_offset(self) -> int:
        return self.profile["box_offset"]

    @property
    def party_block_id(self) -> int:
        return self.profile["party_block_id"]

    @property
    def box_block_id(self) -> int:
        return self.profile["box_block_id"]

    @property
    def metadata_offset(self) -> int:
        return self.size - FOOTER_SIZE

    @property
    def party_count_offset(self) -> int:
        return self.party_offset + PARTY_CAPACITY * PARTY_RECORD_SIZE

    @staticmethod
    def _block_entry_offset(metadata_offset: int, block_id: int) -> int:
        # Save BEEF footer: two u64 timestamp fields, magic, then 8-byte entries.
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
                f"Expected a decrypted Generation VII {self.game_name} save of "
                f"0x{self.size:X} ({self.size:,}) bytes; got 0x{len(data):X} ({len(data):,})"
            )
        marker_offset = len(data) - 0x1F0
        if _u32(data, marker_offset) != BEEF_MAGIC:
            raise ValueError(
                "Generation VII save footer marker is missing. Use a decrypted "
                "PKHeX-compatible 3DS 'main' save, not the encrypted outer 3DS container."
            )
        if not self._block_valid(data, self.party_block_id,
                                 self.party_offset, PARTY_BLOCK_LENGTH):
            raise ValueError("Generation VII party block metadata/checksum is invalid")
        if not self._block_valid(data, self.box_block_id,
                                 self.box_offset, BOX_BLOCK_LENGTH):
            raise ValueError("Generation VII PC box block metadata/checksum is invalid")

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
            raise ValueError(
                f"Invalid Generation VII party count {count}; maximum is {PARTY_CAPACITY}"
            )
        extracted: list[Pokemon] = []
        self._original_party_records = []
        for slot in range(count):
            start = self.party_offset + slot * PARTY_RECORD_SIZE
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
                if pokemon is None:
                    # Preserve any nonzero bytes from an otherwise-empty slot.
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
                slot = getattr(pokemon, "gen7_box_slot", -1)
                print(f"Box {box_index}, slot {slot + 1}: {pokemon.name} (species {pokemon.species})")

    def _write_block_checksum(self, output: bytearray, block_id: int,
                              start: int, length: int) -> None:
        entry = self._block_entry_offset(self.metadata_offset, block_id)
        _put_u32(output, entry, length)
        _put_u16(output, entry + 4, block_id)
        _put_u16(output, entry + 6, crc16_ccitt(output[start:start + length]))

    def _make_output(self) -> bytes:
        if not self._validated or len(self.save_bytes) != self.size:
            raise ValueError("Read a valid Generation VII save before writing")
        if len(self.party_pokemon) > PARTY_CAPACITY:
            raise ValueError(f"Party exceeds {PARTY_CAPACITY} Pokémon")
        if len(self.box_pokemon) != BOX_COUNT:
            raise ValueError(f"Expected {BOX_COUNT} PC boxes, got {len(self.box_pokemon)}")

        output = bytearray(self.save_bytes)
        original_party_set = set(self._original_party_records)
        party_records: list[bytes] = []
        seen_party_records: set[bytes] = set()
        for pokemon in self.party_pokemon:
            record = getattr(pokemon, "gen7_record", None)
            if record is None or len(record) != PARTY_RECORD_SIZE or record not in original_party_set:
                raise ValueError(
                    f"No original Generation VII party record available for {pokemon.name!r}; "
                    "new or edited Pokémon records cannot be written by this handler"
                )
            if record in seen_party_records:
                raise ValueError("Duplicate Pokémon record in party list")
            seen_party_records.add(record)
            party_records.append(record)

        output[self.party_offset:self.party_offset + PARTY_CAPACITY * PARTY_RECORD_SIZE] = bytes(
            PARTY_CAPACITY * PARTY_RECORD_SIZE
        )
        for slot, record in enumerate(party_records):
            start = self.party_offset + slot * PARTY_RECORD_SIZE
            output[start:start + PARTY_RECORD_SIZE] = record
        output[self.party_count_offset] = len(party_records)
        self._write_block_checksum(
            output, self.party_block_id, self.party_offset, PARTY_BLOCK_LENGTH
        )

        retained: set[tuple[int, int]] = set()
        for box_index, box in enumerate(self.box_pokemon):
            if len(box) > BOX_CAPACITY:
                raise ValueError(f"PC box {box_index + 1} exceeds {BOX_CAPACITY} Pokémon")
            for pokemon in box:
                source_box = getattr(pokemon, "gen7_box_index", None)
                source_slot = getattr(pokemon, "gen7_box_slot", None)
                record = getattr(pokemon, "gen7_record", None)
                key = (source_box, source_slot)
                if (
                    source_box != box_index
                    or not isinstance(source_slot, int)
                    or not 0 <= source_slot < BOX_CAPACITY
                    or key not in self._original_box_records
                    or record != self._original_box_records.get(key)
                ):
                    raise ValueError(
                        f"No original Generation VII record available for {pokemon.name!r} "
                        f"in PC box {box_index + 1}; moving or editing Pokémon records is unsupported"
                    )
                if key in retained:
                    raise ValueError(
                        f"Duplicate Pokémon slot in PC box {box_index + 1}, slot {source_slot + 1}"
                    )
                retained.add(key)

        for key in self._original_box_records:
            if key in retained:
                continue
            box_index, slot = key
            start = self.box_offset + (box_index * BOX_CAPACITY + slot) * BOX_RECORD_SIZE
            output[start:start + BOX_RECORD_SIZE] = bytes(BOX_RECORD_SIZE)
        self._write_block_checksum(
            output, self.box_block_id, self.box_offset, BOX_BLOCK_LENGTH
        )

        marker_offset = len(output) - 0x1F0
        _put_u32(output, marker_offset, BEEF_MAGIC)
        self._validate(output)
        if len(output) != self.size:
            raise AssertionError("Generation VII output length changed unexpectedly")
        return bytes(output)

    def write_save(self) -> str:
        """Write ``<input>.new`` atomically without overwriting the input."""
        output = self._make_output()
        output_path = f"{self.path}.new"
        bytes_safe_write(path=output_path, contents=output)
        return output_path


Generation7Save = Gen7_Save
