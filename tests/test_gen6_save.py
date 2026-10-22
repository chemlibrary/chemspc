"""Synthetic unit and SQLite integration tests for Gen VI main saves."""
from __future__ import annotations

import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

import gen6
from gen4 import crc16_ccitt
from gen6 import (
    BEEF_MAGIC,
    BLOCK_INFO_HEADER_LENGTH,
    BOX_BLOCK_LENGTH,
    BOX_CAPACITY,
    BOX_COUNT,
    BOX_RECORD_SIZE,
    BOX_RECORD_SIZE as STORED_SIZE,
    PARTY_BLOCK_LENGTH,
    PARTY_CAPACITY,
    PARTY_OFFSET,
    PARTY_RECORD_SIZE,
    PROFILES,
    Gen6_Save,
    _put_u16,
    _put_u32,
)


def _encode_text(text: str, field_size: int) -> bytes:
    encoded = text.encode("utf-16-le")
    if len(encoded) > field_size - 2:
        raise ValueError("text too long for Gen VI field")
    return encoded + bytes(field_size - len(encoded))


def make_plain_record(species: int, *, party: bool, ec: int, name: str) -> bytes:
    """Construct a small valid plaintext PK6 for encryption in synthetic tests."""
    raw = bytearray(PARTY_RECORD_SIZE if party else BOX_RECORD_SIZE)
    _put_u32(raw, 0, ec)
    _put_u16(raw, 4, 0)  # sanity
    _put_u16(raw, 8, species)
    _put_u16(raw, 0x0A, 1)  # held item
    _put_u16(raw, 0x0C, 12345)  # TID
    _put_u16(raw, 0x0E, 54321)  # SID
    _put_u32(raw, 0x10, 50000)  # EXP
    raw[0x14] = 9  # ability
    _put_u32(raw, 0x18, 0x12345678)  # PID
    raw[0x1C] = 4  # nature
    raw[0x1D] = 0b00000010  # female
    raw[0x1E:0x24] = bytes((1, 2, 3, 4, 5, 6))  # EVs
    raw[0x2B] = 0
    raw[0x40:0x5A] = _encode_text(name, 0x1A)
    for index, move in enumerate((33, 45, 98, 0)):
        _put_u16(raw, 0x5A + 2 * index, move)
    raw[0x62:0x66] = bytes((35, 20, 15, 0))
    iv_word = 31 | (30 << 5) | (29 << 10) | (28 << 15) | (27 << 20) | (26 << 25)
    _put_u32(raw, 0x74, iv_word)
    raw[0xB0:0xCA] = _encode_text("ASH", 0x1A)
    raw[0xCA] = 70  # OT friendship
    raw[0xD1:0xD4] = bytes((24, 1, 15))  # egg year/month/day
    raw[0xD4:0xD7] = bytes((25, 6, 20))  # met year/month/day
    _put_u16(raw, 0xD8, 1)  # egg location
    _put_u16(raw, 0xDA, 2)  # met location
    raw[0xDC] = 4  # Poké Ball
    raw[0xDD] = 12  # met level, OT gender bit unset
    raw[0xDF] = 24  # origin game code
    raw[0xE3] = 2  # language
    if party:
        _put_u32(raw, 0xE8, 0)  # status condition
        raw[0xEC] = 22  # level
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


def encrypt_gen6_record(plain_record: bytes) -> bytes:
    """Encrypt plaintext Gen VI data using PKHeX's documented inverse shuffle."""
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


def build_synthetic_save(game: str = "x") -> bytes:
    profile = PROFILES[game]
    data = bytearray(profile["size"])
    metadata = profile["size"] - 0x200
    _put_u32(data, metadata + 0x10, BEEF_MAGIC)

    party = encrypt_gen6_record(
        make_plain_record(25, party=True, ec=0x12345678, name="Pika")
    )
    boxed = encrypt_gen6_record(
        make_plain_record(133, party=False, ec=0x13572468, name="Eevee")
    )
    data[PARTY_OFFSET:PARTY_OFFSET + PARTY_RECORD_SIZE] = party
    data[PARTY_OFFSET + PARTY_CAPACITY * PARTY_RECORD_SIZE] = 1

    box_start = profile["box_offset"] + (3 * BOX_CAPACITY + 4) * BOX_RECORD_SIZE
    data[box_start:box_start + BOX_RECORD_SIZE] = boxed

    _set_block_entry(data, profile, 0x12, PARTY_OFFSET, PARTY_BLOCK_LENGTH)
    _set_block_entry(
        data, profile, profile["box_block_id"], profile["box_offset"], BOX_BLOCK_LENGTH
    )
    return bytes(data)


class Gen6SaveTests(unittest.TestCase):
    def test_all_32_shuffle_indices_have_matching_inverse(self):
        original = bytearray().join(bytes([block]) * 0x38 for block in range(4))
        for index in range(32):
            payload = bytearray(original)
            gen6._shuffle_blocks(payload, gen6.BLOCK_POSITION_INVERT[index])
            gen6._shuffle_blocks(payload, index)
            self.assertEqual(payload, original, f"shuffle index {index}")

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _load(self, game: str = "x"):
        path = Path(self.temp_dir.name) / f"{game}.main"
        path.write_bytes(build_synthetic_save(game))
        return path, Gen6_Save(path, game=game)

    def test_recognizes_all_four_gen6_game_profiles(self):
        expected = {
            "x": (0x65600, 0x22600, 0x35),
            "y": (0x65600, 0x22600, 0x35),
            "omegaruby": (0x76000, 0x33000, 0x38),
            "alphasapphire": (0x76000, 0x33000, 0x38),
        }
        for game, values in expected.items():
            _path, save = self._load(game)
            self.assertEqual((save.size, save.box_offset, save.box_block_id), values)
            self.assertEqual(save.game_name, game)
            self.assertEqual(len(save.box_pokemon), BOX_COUNT)

    def test_decrypts_party_and_box_pokemon_records(self):
        _path, save = self._load("x")
        self.assertEqual(len(save.party_pokemon), 1)
        pika = save.party_pokemon[0]
        self.assertEqual((pika.species, pika.name, pika.original_trainer_name), (25, "Pika", "ASH"))
        self.assertEqual(pika.level, 22)
        self.assertEqual((pika.special_attack_ev, pika.special_defense_ev), (5, 6))
        self.assertEqual((pika.move1, pika.move2, pika.move3), (33, 45, 98))
        self.assertEqual(pika.gender, 1)

        self.assertEqual(len(save.box_pokemon[3]), 1)
        eevee = save.box_pokemon[3][0]
        self.assertEqual((eevee.species, eevee.name), (133, "Eevee"))
        self.assertEqual((eevee.gen6_box_index, eevee.gen6_box_slot), (3, 4))
        self.assertIsNone(eevee.level, "boxed Pokémon have no stored current level field")

    def test_round_trip_without_changes_preserves_the_save(self):
        path, save = self._load("y")
        original = path.read_bytes()
        output_path = save.write_save()
        self.assertEqual(Path(output_path).read_bytes(), original)
        self.assertEqual(path.read_bytes(), original)

    def test_clearing_party_and_boxes_updates_checksums_and_keeps_file_size(self):
        path, save = self._load("omegaruby")
        original = path.read_bytes()
        save.party_pokemon = []
        save.box_pokemon = [[] for _ in range(BOX_COUNT)]
        output_path = save.write_save()
        output = Path(output_path).read_bytes()
        self.assertEqual(len(output), len(original))
        self.assertEqual(path.read_bytes(), original)
        cleaned = Gen6_Save(output_path, game="omegaruby")
        self.assertEqual(cleaned.party_pokemon, [])
        self.assertTrue(all(not box for box in cleaned.box_pokemon))
        self.assertEqual(output[cleaned.party_count_offset], 0)

    def test_partial_box_removal_preserves_other_box_slots(self):
        path, save = self._load("alphasapphire")
        # Add a second boxed Pokémon in another location.
        record = encrypt_gen6_record(
            make_plain_record(25, party=False, ec=0x87654321, name="Pika2")
        )
        location = save.box_offset + (4 * BOX_CAPACITY + 9) * BOX_RECORD_SIZE
        raw = bytearray(path.read_bytes())
        raw[location:location + BOX_RECORD_SIZE] = record
        profile = PROFILES["alphasapphire"]
        _set_block_entry(raw, profile, profile["box_block_id"], save.box_offset, BOX_BLOCK_LENGTH)
        path.write_bytes(raw)
        save = Gen6_Save(path, game="alphasapphire")
        save.box_pokemon[3] = []
        out = Path(save.write_save()).read_bytes()
        self.assertEqual(out[save.box_offset + (3 * BOX_CAPACITY + 4) * BOX_RECORD_SIZE:
                              save.box_offset + (3 * BOX_CAPACITY + 5) * BOX_RECORD_SIZE], bytes(BOX_RECORD_SIZE))
        self.assertEqual(out[location:location + BOX_RECORD_SIZE], record)

    def test_rejects_invalid_block_checksum_and_raw_container(self):
        data = bytearray(build_synthetic_save("x"))
        data[PARTY_OFFSET + 8] ^= 1
        path = Path(self.temp_dir.name) / "bad-checksum.main"
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "party block metadata/checksum"):
            Gen6_Save(path, game="x")

        raw_container = Path(self.temp_dir.name) / "encrypted-container.sav"
        raw_container.write_bytes(bytes(0x100000))
        with self.assertRaisesRegex(ValueError, "Expected a decrypted Generation VI"):
            Gen6_Save(raw_container, game="x")


class Gen6SQLiteIntegrationTests(unittest.TestCase):
    def test_all_gen6_games_import_to_sqlite_then_write_clean_copy(self):
        import db
        from main import import_gen6

        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "chemspc.db"
            old_db_name = db.DATABASE_NAME
            db.DATABASE_NAME = str(db_path)
            try:
                games = ("x", "y", "omegaruby", "alphasapphire")
                for game in games:
                    input_path = Path(directory) / f"{game}.main"
                    input_path.write_bytes(build_synthetic_save(game))
                    original = input_path.read_bytes()
                    with contextlib.redirect_stdout(io.StringIO()):
                        output_path = import_gen6(str(input_path), game=game)
                    self.assertTrue(Path(output_path).exists())
                    self.assertEqual(input_path.read_bytes(), original)
                    clean = Gen6_Save(output_path, game=game)
                    self.assertEqual(clean.party_pokemon, [])
                    self.assertTrue(all(not box for box in clean.box_pokemon))

                with sqlite3.connect(db_path) as conn:
                    rows = conn.execute(
                        "SELECT generation, source_game, species, name, special_attack_ev, special_defense_ev "
                        "FROM pokemon ORDER BY uid"
                    ).fetchall()
                self.assertEqual(len(rows), 8)
                self.assertTrue(all(row[0] == 6 for row in rows))
                self.assertEqual({row[1] for row in rows}, set(games))
                self.assertEqual({row[2] for row in rows}, {25, 133})
            finally:
                db.DATABASE_NAME = old_db_name

    def test_sqlite_failure_does_not_write_clean_save(self):
        import db
        import main

        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "failure.main"
            input_path.write_bytes(build_synthetic_save("x"))
            original = input_path.read_bytes()
            old_db_name = db.DATABASE_NAME
            old_batch = main.add_pokemon_batch
            db.DATABASE_NAME = str(Path(directory) / "chemspc.db")
            main.add_pokemon_batch = lambda _items: (_ for _ in ()).throw(sqlite3.IntegrityError("test fail"))
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(sqlite3.IntegrityError):
                        main.import_gen6(str(input_path), game="x")
                self.assertEqual(input_path.read_bytes(), original)
                self.assertFalse(Path(str(input_path) + ".new").exists())
            finally:
                db.DATABASE_NAME = old_db_name
                main.add_pokemon_batch = old_batch


if __name__ == "__main__":
    unittest.main()
