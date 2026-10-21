"""Synthetic layout tests for the Generation IV save handler.

These fixtures validate parser mechanics and are not a substitute for testing a
known-good retail save in a Nintendo DS emulator.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

if "chempy" not in sys.modules and importlib.util.find_spec("chempy") is None:
    chempy = types.ModuleType("chempy")
    chempy.__path__ = []
    primitives = types.ModuleType("chempy.primitives")
    primitives.get_int = lambda data: int.from_bytes(data, "big")
    primitives.get_bytes = lambda value, length: int(value).to_bytes(length, "big")
    files = types.ModuleType("chempy.files")
    def bytes_safe_write(*, path, contents):
        Path(path).write_bytes(bytes(contents))
    files.bytes_safe_write = bytes_safe_write
    sys.modules["chempy"] = chempy
    sys.modules["chempy.primitives"] = primitives
    sys.modules["chempy.files"] = files

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from gen4 import (  # noqa: E402
    BOX_CAPACITY, BOX_COUNT, BOX_RECORD_SIZE, PARTY_COUNT_OFFSET,
    PARTY_RECORDS_OFFSET, PARTY_RECORD_SIZE, PARTITION_SIZE, PROFILES,
    SAVE_SIZE, SUBSTRUCTURE_ORDERS, Gen4_Save, _put_u16, _put_u32,
    crc16_ccitt, decode_gen4_text,
)

CHAR_ENCODE = {chr(ord("0") + i): 0x0121 + i for i in range(10)}
CHAR_ENCODE.update({chr(ord("A") + i): 0x012B + i for i in range(26)})
CHAR_ENCODE.update({chr(ord("a") + i): 0x0145 + i for i in range(26)})


def put_text(buffer: bytearray, offset: int, text: str, max_chars: int) -> None:
    text = text[:max_chars]
    for index, char in enumerate(text):
        _put_u16(buffer, offset + index * 2, CHAR_ENCODE[char])
    for index in range(len(text), max_chars):
        _put_u16(buffer, offset + index * 2, 0xFFFF)


def make_pk4(*, party: bool) -> bytes:
    """Create a checksummed/encrypted English Pikachu record for tests."""
    pid = 0x12345678
    logical = bytearray(128)
    _put_u16(logical, 0, 25)      # Species
    _put_u16(logical, 2, 1)       # Held item
    _put_u32(logical, 4, 0xBEEF1234)  # TID 0x1234, SID 0xBEEF
    _put_u32(logical, 8, 12500)   # Experience
    logical[0x0C] = 75            # Friendship
    logical[0x0D] = 9             # Ability number
    logical[0x0F] = 2             # English language ID
    logical[0x10:0x16] = bytes((1, 2, 3, 4, 5, 6))
    for i, move in enumerate((85, 33, 0, 0)):
        _put_u16(logical, 0x20 + i * 2, move)
    logical[0x28:0x2C] = bytes((15, 35, 0, 0))
    ivs = (31, 30, 29, 28, 27, 26)
    iv_word = sum(value << (index * 5) for index, value in enumerate(ivs))
    _put_u32(logical, 0x30, iv_word)
    logical[0x38] = 0x02   # female bit
    put_text(logical, 0x40, "PIKACHU", 12)
    put_text(logical, 0x60, "ASH", 8)
    logical[0x76:0x78] = (0x1234).to_bytes(2, "little")
    logical[0x7A] = 0x24
    checksum = sum(int.from_bytes(logical[i:i + 2], "little") for i in range(0, 128, 2)) & 0xFFFF

    permutation = SUBSTRUCTURE_ORDERS[((pid & 0x3E000) >> 13) % 24]
    shuffled = bytearray(128)
    for stored_index, block_name in enumerate(permutation):
        logical_index = ord(block_name) - ord("A")
        shuffled[stored_index * 32:(stored_index + 1) * 32] = logical[logical_index * 32:(logical_index + 1) * 32]
    encrypted = bytearray(128)
    seed = checksum
    for offset in range(0, 128, 2):
        seed = (0x41C64E6D * seed + 0x6073) & 0xFFFFFFFF
        word = int.from_bytes(shuffled[offset:offset + 2], "little") ^ (seed >> 16)
        encrypted[offset:offset + 2] = word.to_bytes(2, "little")

    raw = bytearray(PARTY_RECORD_SIZE if party else BOX_RECORD_SIZE)
    _put_u32(raw, 0, pid)
    _put_u16(raw, 6, checksum)
    raw[8:0x88] = encrypted
    if party:
        stats = bytearray(100)
        _put_u32(stats, 0, 0)      # Status
        stats[4] = 18              # Level
        _put_u16(stats, 6, 36)      # Current HP
        _put_u16(stats, 8, 42)      # Max HP
        _put_u16(stats, 10, 25)     # Attack
        _put_u16(stats, 12, 22)     # Defense
        _put_u16(stats, 14, 28)     # Speed
        _put_u16(stats, 16, 19)     # Sp. Attack
        _put_u16(stats, 18, 21)     # Sp. Defense
        seed = pid
        for offset in range(0, 100, 2):
            seed = (0x41C64E6D * seed + 0x6073) & 0xFFFFFFFF
            word = int.from_bytes(stats[offset:offset + 2], "little") ^ (seed >> 16)
            stats[offset:offset + 2] = word.to_bytes(2, "little")
        raw[0x88:] = stats
    return bytes(raw)


def write_footer(block: bytearray, *, link: int, counter: int, footer_size: int) -> None:
    _put_u32(block, len(block) - 0x14, link)
    _put_u32(block, len(block) - 0x10, counter)
    _put_u32(block, len(block) - 0x0C, len(block))
    _put_u32(block, len(block) - 0x08, 0x20060623)
    _put_u16(block, len(block) - 0x04, 0)
    _put_u16(block, len(block) - 2, crc16_ccitt(block[:-footer_size]))


def build_synthetic_save(game: str = "diamond", *, box_slot: int = 0) -> bytes:
    profile = PROFILES[game]
    raw = bytearray(SAVE_SIZE)
    party = make_pk4(party=True)
    boxed = make_pk4(party=False)
    for partition, link, counter in ((0, 0x11, 2), (PARTITION_SIZE, 0x22, 1)):
        general = bytearray(profile["general_size"])
        general[PARTY_COUNT_OFFSET] = 1
        general[PARTY_RECORDS_OFFSET:PARTY_RECORDS_OFFSET + PARTY_RECORD_SIZE] = party
        write_footer(general, link=link, counter=counter, footer_size=profile["footer_size"])
        raw[partition:partition + len(general)] = general

    # Link each general block to the storage block that belongs to that save.
    for partition, link, counter in (
        (0, 0x22, 1), (PARTITION_SIZE, 0x11, 2),
    ):
        storage = bytearray(profile["storage_size"])
        if profile["storage_kind"] == "hgss":
            storage_record_offset = box_slot * BOX_RECORD_SIZE
            _put_u32(storage, 0x12000, 0)  # current box
            _put_u32(storage, 0x12004, 1)  # total boxed Pokémon
        else:
            storage_record_offset = 4 + box_slot * BOX_RECORD_SIZE
            _put_u32(storage, 0, 0)        # current box
        storage[storage_record_offset:storage_record_offset + BOX_RECORD_SIZE] = boxed
        write_footer(storage, link=link, counter=counter, footer_size=profile["footer_size"])
        start = partition + profile["storage_start"]
        raw[start:start + len(storage)] = storage
    return bytes(raw)


class Gen4SaveTests(unittest.TestCase):
    def test_crc16_ccitt_known_check_value(self):
        self.assertEqual(crc16_ccitt(b"123456789"), 0x29B1)

    def test_gen4_character_encoding(self):
        encoded = bytearray()
        for value in (0x012B, 0x012C, 0x012D, 0xFFFF):
            encoded.extend(value.to_bytes(2, "little"))
        self.assertEqual(decode_gen4_text(encoded), "ABC")

    def test_reads_party_and_boxed_pokemon_for_all_game_layouts(self):
        for game in PROFILES:
            with self.subTest(game=game), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / f"{game}.sav"
                path.write_bytes(build_synthetic_save(game))
                save = Gen4_Save(path, game=game)
                self.assertEqual(len(save.party_pokemon), 1)
                party = save.party_pokemon[0]
                self.assertEqual(party.generation, 4)
                self.assertEqual(party.species, 25)
                self.assertEqual(party.name, "PIKACHU")
                self.assertEqual(party.original_trainer_name, "ASH")
                self.assertEqual(party.original_trainer, 0xBEEF1234)
                self.assertEqual(party.exp, 12500)
                self.assertEqual(party.move1, 85)
                self.assertEqual(party.level, 18)
                self.assertEqual(party.current_hp, 36)
                self.assertEqual(party.special_attack_ev, 5)
                self.assertEqual(party.special_defense_ev, 6)
                self.assertEqual(len(save.box_pokemon), BOX_COUNT)
                self.assertEqual(len(save.box_pokemon[0]), 1)
                self.assertEqual(save.box_pokemon[0][0].species, 25)
                self.assertIsNone(save.box_pokemon[0][0].level)

    def test_writer_keeps_save_size_and_checksums_valid(self):
        for game in PROFILES:
            with self.subTest(game=game), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "input.sav"
                original = build_synthetic_save(game)
                path.write_bytes(original)
                save = Gen4_Save(path, game=game)
                outpath = save.write_save()
                output = Path(outpath).read_bytes()
                self.assertEqual(len(output), SAVE_SIZE)
                self.assertEqual(path.read_bytes(), original)
                reread = Gen4_Save(outpath, game=game)
                self.assertEqual(len(reread.party_pokemon), 1)
                self.assertEqual(len(reread.box_pokemon[0]), 1)

    def test_empty_lists_remove_party_and_pc_pokemon_from_all_valid_copies(self):
        for game in PROFILES:
            with self.subTest(game=game), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "input.sav"
                path.write_bytes(build_synthetic_save(game))
                save = Gen4_Save(path, game=game)
                save.party_pokemon = []
                save.box_pokemon = [[] for _ in range(BOX_COUNT)]
                outpath = save.write_save()
                clean = Gen4_Save(outpath, game=game)
                self.assertEqual(clean.party_pokemon, [])
                self.assertTrue(all(not box for box in clean.box_pokemon))
                self.assertEqual(Path(outpath).stat().st_size, SAVE_SIZE)

    def test_box_slot_is_preserved_when_retaining_an_existing_pokemon(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "platinum.sav"
            path.write_bytes(build_synthetic_save("platinum", box_slot=7))
            save = Gen4_Save(path, game="platinum")
            outpath = save.write_save()
            reread = Gen4_Save(outpath, game="platinum")
            self.assertEqual(reread.box_pokemon[0][0].gen4_box_slot, 7)


if __name__ == "__main__":
    unittest.main()
