"""Synthetic unit and SQLite integration tests for Gen VII 3DS main saves."""
from __future__ import annotations

import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

import gen6
import gen7
import db
from gen4 import crc16_ccitt
from gen7 import (
    BEEF_MAGIC,
    BLOCK_INFO_HEADER_LENGTH,
    BOX_BLOCK_LENGTH,
    BOX_CAPACITY,
    BOX_COUNT,
    BOX_RECORD_SIZE,
    PARTY_BLOCK_LENGTH,
    PARTY_CAPACITY,
    PARTY_RECORD_SIZE,
    PROFILES,
    Gen7_Save,
    _put_u16,
    _put_u32,
)


def _encode_text(text: str, field_size: int) -> bytes:
    encoded = text.encode("utf-16-le")
    if len(encoded) > field_size - 2:
        raise ValueError("text too long for PK7 field")
    return encoded + bytes(field_size - len(encoded))


def make_plain_record(species: int, *, party: bool, ec: int, name: str) -> bytes:
    """Build a synthetic valid PK7 plaintext record."""
    raw = bytearray(PARTY_RECORD_SIZE if party else BOX_RECORD_SIZE)
    _put_u32(raw, 0, ec)
    _put_u16(raw, 4, 0)
    _put_u16(raw, 8, species)
    _put_u16(raw, 0x0A, 1)
    _put_u16(raw, 0x0C, 12345)
    _put_u16(raw, 0x0E, 54321)
    _put_u32(raw, 0x10, 50000)
    raw[0x14] = 9
    _put_u32(raw, 0x18, 0x12345678)
    raw[0x1C] = 4
    raw[0x1D] = 0b00000010
    raw[0x1E:0x24] = bytes((1, 2, 3, 4, 5, 6))
    raw[0x2B] = 0
    raw[0x40:0x5A] = _encode_text(name, 0x1A)
    for index, move in enumerate((33, 45, 98, 0)):
        _put_u16(raw, 0x5A + index * 2, move)
    raw[0x62:0x66] = bytes((35, 20, 15, 0))
    iv_word = 31 | (30 << 5) | (29 << 10) | (28 << 15) | (27 << 20) | (26 << 25)
    _put_u32(raw, 0x74, iv_word)
    raw[0xB0:0xCA] = _encode_text("ASH", 0x1A)
    raw[0xCA] = 70
    raw[0xD1:0xD4] = bytes((24, 1, 15))
    raw[0xD4:0xD7] = bytes((25, 6, 20))
    _put_u16(raw, 0xD8, 1)
    _put_u16(raw, 0xDA, 2)
    raw[0xDC] = 4
    raw[0xDD] = 12
    raw[0xDF] = 30
    raw[0xE3] = 2
    if party:
        _put_u32(raw, 0xE8, 0)
        raw[0xEC] = 22
        _put_u16(raw, 0xF0, 54)
        _put_u16(raw, 0xF2, 61)
        _put_u16(raw, 0xF4, 32)
        _put_u16(raw, 0xF6, 28)
        _put_u16(raw, 0xF8, 35)
        _put_u16(raw, 0xFA, 30)
        _put_u16(raw, 0xFC, 27)
    checksum = sum(
        int.from_bytes(raw[offset:offset + 2], "little")
        for offset in range(8, BOX_RECORD_SIZE, 2)
    ) & 0xFFFF
    _put_u16(raw, 6, checksum)
    return bytes(raw)


def encrypt_gen7_record(plain_record: bytes) -> bytes:
    """Encrypt PK7 bytes using the same Gen VI/VII record crypto routine."""
    raw = bytearray(plain_record)
    ec = int.from_bytes(raw[0:4], "little")
    shuffle_index = (ec >> 13) & 31
    payload = bytearray(raw[8:BOX_RECORD_SIZE])
    gen6._shuffle_blocks(payload, gen6.BLOCK_POSITION_INVERT[shuffle_index])
    gen6._crypt_array(payload, ec)
    raw[8:BOX_RECORD_SIZE] = payload
    if len(raw) > BOX_RECORD_SIZE:
        stats = bytearray(raw[BOX_RECORD_SIZE:])
        gen6._crypt_array(stats, ec)
        raw[BOX_RECORD_SIZE:] = stats
    return bytes(raw)


def _set_block_entry(data: bytearray, profile: dict, block_id: int,
                     start: int, length: int) -> None:
    metadata = profile["size"] - 0x200
    entry = metadata + BLOCK_INFO_HEADER_LENGTH + block_id * 8
    _put_u32(data, entry, length)
    _put_u16(data, entry + 4, block_id)
    _put_u16(data, entry + 6, crc16_ccitt(data[start:start + length]))


def build_synthetic_save(game: str = "sun") -> bytes:
    profile = PROFILES[game]
    data = bytearray(profile["size"])
    metadata = profile["size"] - 0x200
    _put_u32(data, metadata + 0x10, BEEF_MAGIC)

    party = encrypt_gen7_record(
        make_plain_record(25, party=True, ec=0x12345678, name="Pika")
    )
    boxed = encrypt_gen7_record(
        make_plain_record(133, party=False, ec=0x13572468, name="Eevee")
    )
    party_start = profile["party_offset"]
    box_start = profile["box_offset"] + (3 * BOX_CAPACITY + 4) * BOX_RECORD_SIZE
    data[party_start:party_start + PARTY_RECORD_SIZE] = party
    data[party_start + PARTY_CAPACITY * PARTY_RECORD_SIZE] = 1
    data[box_start:box_start + BOX_RECORD_SIZE] = boxed

    _set_block_entry(
        data, profile, profile["party_block_id"],
        profile["party_offset"], PARTY_BLOCK_LENGTH,
    )
    _set_block_entry(
        data, profile, profile["box_block_id"],
        profile["box_offset"], BOX_BLOCK_LENGTH,
    )
    return bytes(data)


class Gen7SaveTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _load(self, game: str = "sun"):
        path = Path(self.temp_dir.name) / f"{game}.main"
        path.write_bytes(build_synthetic_save(game))
        return path, Gen7_Save(path, game=game)

    def test_recognizes_all_four_gen7_profiles(self):
        expected = {
            "sun": (0x6BE00, 0x1400, 0x4E00),
            "moon": (0x6BE00, 0x1400, 0x4E00),
            "ultrasun": (0x6CC00, 0x1600, 0x5200),
            "ultramoon": (0x6CC00, 0x1600, 0x5200),
        }
        for game, values in expected.items():
            _path, save = self._load(game)
            self.assertEqual((save.size, save.party_offset, save.box_offset), values)
            self.assertEqual(save.game_name, game)
            self.assertEqual(len(save.box_pokemon), BOX_COUNT)
            self.assertEqual(save.party_block_id, 4)
            self.assertEqual(save.box_block_id, 14)

    def test_parses_party_and_box_records_as_generation_seven(self):
        _path, save = self._load("sun")
        self.assertEqual(len(save.party_pokemon), 1)
        party = save.party_pokemon[0]
        self.assertEqual((party.generation, party.species, party.name), (7, 25, "Pika"))
        self.assertEqual(party.original_trainer_name, "ASH")
        self.assertEqual(party.level, 22)
        self.assertEqual((party.special_attack_ev, party.special_defense_ev), (5, 6))
        self.assertEqual((party.move1, party.move2, party.move3), (33, 45, 98))

        self.assertEqual(len(save.box_pokemon[3]), 1)
        eevee = save.box_pokemon[3][0]
        self.assertEqual((eevee.generation, eevee.species, eevee.name), (7, 133, "Eevee"))
        self.assertEqual((eevee.gen7_box_index, eevee.gen7_box_slot), (3, 4))

    def test_untouched_round_trip_preserves_the_entire_save(self):
        path, save = self._load("moon")
        original = path.read_bytes()
        output_path = save.write_save()
        self.assertEqual(Path(output_path).read_bytes(), original)
        self.assertEqual(path.read_bytes(), original)

    def test_clearing_party_and_boxes_updates_checksums(self):
        path, save = self._load("ultrasun")
        original = path.read_bytes()
        save.party_pokemon = []
        save.box_pokemon = [[] for _ in range(BOX_COUNT)]
        output_path = save.write_save()
        output = Path(output_path).read_bytes()
        self.assertEqual(len(output), len(original))
        self.assertEqual(path.read_bytes(), original)
        clean = Gen7_Save(output_path, game="ultrasun")
        self.assertEqual(clean.party_pokemon, [])
        self.assertTrue(all(not box for box in clean.box_pokemon))
        self.assertEqual(output[clean.party_count_offset], 0)

    def test_partial_box_removal_preserves_other_slots(self):
        path, _save = self._load("ultramoon")
        raw = bytearray(path.read_bytes())
        profile = PROFILES["ultramoon"]
        second = encrypt_gen7_record(
            make_plain_record(25, party=False, ec=0x87654321, name="Pika2")
        )
        location = profile["box_offset"] + (4 * BOX_CAPACITY + 9) * BOX_RECORD_SIZE
        raw[location:location + BOX_RECORD_SIZE] = second
        _set_block_entry(raw, profile, profile["box_block_id"], profile["box_offset"], BOX_BLOCK_LENGTH)
        path.write_bytes(raw)
        save = Gen7_Save(path, game="ultramoon")
        save.box_pokemon[3] = []
        out = Path(save.write_save()).read_bytes()
        removed = profile["box_offset"] + (3 * BOX_CAPACITY + 4) * BOX_RECORD_SIZE
        self.assertEqual(out[removed:removed + BOX_RECORD_SIZE], bytes(BOX_RECORD_SIZE))
        self.assertEqual(out[location:location + BOX_RECORD_SIZE], second)

    def test_rejects_bad_size_marker_and_block_checksum(self):
        path = Path(self.temp_dir.name) / "bad-size.main"
        path.write_bytes(bytes(0x100000))
        with self.assertRaisesRegex(ValueError, "Expected a decrypted Generation VII"):
            Gen7_Save(path, game="sun")

        data = bytearray(build_synthetic_save("sun"))
        data[-0x1F0] = 0
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "footer marker is missing"):
            Gen7_Save(path, game="sun")

        data = bytearray(build_synthetic_save("sun"))
        data[PROFILES["sun"]["party_offset"] + 10] ^= 0x01
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "party block metadata/checksum"):
            Gen7_Save(path, game="sun")

    def test_lets_go_titles_are_not_supported(self):
        path = Path(self.temp_dir.name) / "unused"
        with self.assertRaisesRegex(ValueError, "Choose sun, moon"):
            Gen7_Save(path, game="letsgo")


class Gen7SQLiteIntegrationTests(unittest.TestCase):
    def test_all_gen7_games_import_to_sqlite_then_write_clean_copy(self):
        import main
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "chemspc.db"
            original_database_name = db.DATABASE_NAME
            db.DATABASE_NAME = str(database_path)
            try:
                games = ("sun", "moon", "ultrasun", "ultramoon")
                for game in games:
                    input_path = Path(directory) / f"{game}.main"
                    input_path.write_bytes(build_synthetic_save(game))
                    original = input_path.read_bytes()
                    with contextlib.redirect_stdout(io.StringIO()):
                        output_path = main.import_gen7(str(input_path), game=game)
                    self.assertTrue(Path(output_path).exists())
                    self.assertEqual(input_path.read_bytes(), original)
                    clean = Gen7_Save(output_path, game=game)
                    self.assertEqual(clean.party_pokemon, [])
                    self.assertTrue(all(not box for box in clean.box_pokemon))
                with sqlite3.connect(database_path) as connection:
                    rows = connection.execute(
                        "SELECT generation, source_game, species, name FROM pokemon ORDER BY uid"
                    ).fetchall()
                self.assertEqual(len(rows), 8)
                self.assertTrue(all(row[0] == 7 for row in rows))
                self.assertEqual({row[1] for row in rows}, {"sun", "moon", "ultrasun", "ultramoon"})
                self.assertEqual({row[2] for row in rows}, {25, 133})
            finally:
                db.DATABASE_NAME = original_database_name

    def test_sqlite_failure_does_not_write_clean_save(self):
        import main
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "failure.main"
            input_path.write_bytes(build_synthetic_save("sun"))
            original = input_path.read_bytes()
            original_database_name = db.DATABASE_NAME
            original_batch = main.add_pokemon_batch
            db.DATABASE_NAME = str(Path(directory) / "chemspc.db")
            main.add_pokemon_batch = lambda _items: (_ for _ in ()).throw(
                sqlite3.IntegrityError("synthetic import failure")
            )
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(sqlite3.IntegrityError):
                        main.import_gen7(str(input_path), game="sun")
                self.assertEqual(input_path.read_bytes(), original)
                self.assertFalse(Path(str(input_path) + ".new").exists())
            finally:
                db.DATABASE_NAME = original_database_name
                main.add_pokemon_batch = original_batch


if __name__ == "__main__":
    unittest.main()
