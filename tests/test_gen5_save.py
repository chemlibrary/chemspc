"""Synthetic structural tests for English Generation V save handling.

The fixtures exercise documented layout/checksum boundaries, but are not a
substitute for validating output against a known-good retail save and emulator.
"""
from __future__ import annotations

import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

from gen4 import crc16_ccitt
from gen5 import (
    BOX_BLOCK_LENGTH,
    BOX_CAPACITY,
    BOX_COUNT,
    BOX_RECORD_SIZE,
    BOX_STRIDE,
    BOXES_START,
    BLOCK_POSITION,
    PARTY_BLOCK_LENGTH,
    PARTY_BLOCK_START,
    PARTY_CAPACITY,
    PARTY_COUNT_OFFSET,
    PARTY_RECORDS_OFFSET,
    PARTY_RECORD_SIZE,
    PROFILES,
    SAVE_SIZE,
    Gen5_Save,
    _put_u16,
    _put_u32,
    _u16,
    _u32,
    _box_block_start,
    _lcg_xor,
)


def _encode_text(text: str, units: int) -> bytes:
    values = []
    for char in text:
        if "0" <= char <= "9":
            values.append(0x0121 + ord(char) - ord("0"))
        elif "A" <= char <= "Z":
            values.append(0x012B + ord(char) - ord("A"))
        elif "a" <= char <= "z":
            values.append(0x0145 + ord(char) - ord("a"))
        else:
            raise ValueError(char)
    values = values[:max(0, units - 1)]
    values.append(0xFFFF)
    values.extend([0xFFFF] * max(0, units - len(values)))
    return b"".join(value.to_bytes(2, "little") for value in values[:units])


def make_encrypted_record(species: int, *, pid: int, name: str, party: bool = False) -> bytes:
    """Create a checksum-correct test PK5 record using the documented cipher."""
    payload = bytearray(128)
    _put_u16(payload, 0, species)
    _put_u16(payload, 2, 1)  # held item
    _put_u32(payload, 4, 0xABCD1234)  # TID/SID
    _put_u32(payload, 8, 123456)  # experience
    payload[0x0C] = 70  # friendship
    payload[0x0D] = 9   # ability ID
    payload[0x0F] = 2   # language
    payload[0x10:0x16] = bytes((1, 2, 3, 4, 5, 6))
    for idx, move in enumerate((33, 45, 98, 0)):
        _put_u16(payload, 0x20 + idx * 2, move)
    payload[0x28:0x2C] = bytes((35, 20, 15, 0))
    _put_u32(payload, 0x30, (31 | (30 << 5) | (29 << 10) | (28 << 15) |
                             (27 << 20) | (26 << 25)))
    payload[0x40:0x56] = _encode_text(name, 11)
    payload[0x57] = 20  # game-of-origin code
    payload[0x60:0x70] = _encode_text("ASH", 8)
    payload[0x70:0x73] = bytes((24, 1, 15))
    payload[0x73:0x76] = bytes((25, 6, 20))
    _put_u16(payload, 0x76, 1)
    _put_u16(payload, 0x78, 2)
    payload[0x7A] = 0
    payload[0x7B] = 4
    payload[0x7C] = 12  # met level, OT gender 0
    checksum = sum(_u16(payload, off) for off in range(0, len(payload), 2)) & 0xFFFF

    record = bytearray(PARTY_RECORD_SIZE if party else BOX_RECORD_SIZE)
    _put_u32(record, 0, pid)
    _put_u16(record, 6, checksum)
    shuffle_index = (pid >> 13) & 31
    row = BLOCK_POSITION[shuffle_index]
    shuffled = bytearray(128)
    for stored_index, logical_index in enumerate(row):
        shuffled[stored_index * 32:(stored_index + 1) * 32] = payload[
            logical_index * 32:(logical_index + 1) * 32
        ]
    record[8:BOX_RECORD_SIZE] = _lcg_xor(shuffled, checksum)

    if party:
        stats = bytearray(PARTY_RECORD_SIZE - BOX_RECORD_SIZE)
        _put_u32(stats, 0, 0)  # status condition
        stats[4] = 22  # current level
        _put_u16(stats, 6, 54)
        _put_u16(stats, 8, 61)
        _put_u16(stats, 10, 32)
        _put_u16(stats, 12, 28)
        _put_u16(stats, 14, 35)
        _put_u16(stats, 16, 30)
        _put_u16(stats, 18, 27)
        record[BOX_RECORD_SIZE:] = _lcg_xor(stats, pid)
    return bytes(record)


def _rebuild_checksums(data: bytearray, game: str, base: int) -> None:
    profile = PROFILES[game]
    footer_start = base + profile["main_size"] - 0x100

    for box_index in range(BOX_COUNT):
        start = base + _box_block_start(box_index)
        checksum = crc16_ccitt(data[start:start + BOX_BLOCK_LENGTH])
        _put_u16(data, start + BOX_BLOCK_LENGTH + 2, checksum)
        _put_u16(data, footer_start + (box_index + 1) * 2, checksum)

    party_start = base + PARTY_BLOCK_START
    checksum = crc16_ccitt(data[party_start:party_start + PARTY_BLOCK_LENGTH])
    _put_u16(data, party_start + PARTY_BLOCK_LENGTH + 2, checksum)
    _put_u16(data, footer_start + 26 * 2, checksum)

    footer_crc = crc16_ccitt(data[footer_start:footer_start + profile["info_length"]])
    _put_u16(data, footer_start + profile["info_length"] + 0x0E, footer_crc)


def build_synthetic_save(game: str = "black") -> bytes:
    profile = PROFILES[game]
    data = bytearray(SAVE_SIZE)
    party = make_encrypted_record(25, pid=0x12345678, name="Pika", party=True)
    boxed = make_encrypted_record(133, pid=0x13572468, name="Eevee", party=False)
    for base in (0, profile["main_size"]):
        _put_u32(data, base + PARTY_COUNT_OFFSET, 1)
        party_start = base + PARTY_RECORDS_OFFSET
        data[party_start:party_start + PARTY_RECORD_SIZE] = party
        box_start = base + BOXES_START + BOX_STRIDE * 3
        data[box_start + BOX_RECORD_SIZE * 4:box_start + BOX_RECORD_SIZE * 5] = boxed
        _rebuild_checksums(data, game, base)
    return bytes(data)


class Gen5SaveTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _load(self, game="black"):
        path = Path(self.temp_dir.name) / f"{game}.sav"
        path.write_bytes(build_synthetic_save(game))
        return path, Gen5_Save(str(path), game=game)

    def test_supports_all_four_games_and_expected_profile_sizes(self):
        self.assertEqual(PROFILES["black"]["main_size"], 0x24000)
        self.assertEqual(PROFILES["white"]["main_size"], 0x24000)
        self.assertEqual(PROFILES["black2"]["main_size"], 0x26000)
        self.assertEqual(PROFILES["white2"]["main_size"], 0x26000)
        for game in ("black", "white", "black2", "white2"):
            path, save = self._load(game)
            self.assertEqual(Path(path).stat().st_size, SAVE_SIZE)
            self.assertEqual(save.game_name, game)
            self.assertEqual(len(save.box_pokemon), BOX_COUNT)

    def test_decrypts_party_and_box_records(self):
        _path, save = self._load("black")
        self.assertEqual(len(save.party_pokemon), 1)
        self.assertEqual(save.party_pokemon[0].species, 25)
        self.assertEqual(save.party_pokemon[0].name, "Pika")
        self.assertEqual(save.party_pokemon[0].level, 22)
        self.assertEqual(save.party_pokemon[0].special_attack_ev, 5)
        self.assertEqual(save.party_pokemon[0].special_defense_ev, 6)
        self.assertEqual(len(save.box_pokemon[3]), 1)
        boxed = save.box_pokemon[3][0]
        self.assertEqual(boxed.species, 133)
        self.assertEqual(boxed.name, "Eevee")
        self.assertEqual(boxed.gen5_box_slot, 4)

    def test_round_trip_preserves_original_encrypted_records(self):
        path, save = self._load("black2")
        original = path.read_bytes()
        output_path = save.write_save()
        output = Path(output_path).read_bytes()
        self.assertEqual(len(output), SAVE_SIZE)
        self.assertEqual(output, original)
        reloaded = Gen5_Save(output_path, game="black2")
        self.assertEqual(reloaded.party_pokemon[0].gen5_party_record,
                         save.party_pokemon[0].gen5_party_record)
        self.assertEqual(reloaded.box_pokemon[3][0].gen5_box_record,
                         save.box_pokemon[3][0].gen5_box_record)

    def test_clearing_party_and_boxes_updates_both_valid_copies(self):
        path, save = self._load("white")
        original = path.read_bytes()
        save.party_pokemon = []
        save.box_pokemon = [[] for _ in range(BOX_COUNT)]
        output_path = save.write_save()
        self.assertEqual(path.read_bytes(), original, "the input save must remain unchanged")
        cleaned = Gen5_Save(output_path, game="white")
        self.assertEqual(cleaned.party_pokemon, [])
        self.assertTrue(all(not box for box in cleaned.box_pokemon))
        self.assertEqual(_u32(Path(output_path).read_bytes(), PARTY_COUNT_OFFSET), 0)
        self.assertEqual(_u32(Path(output_path).read_bytes(), PROFILES["white"]["main_size"] + PARTY_COUNT_OFFSET), 0)

    def test_uses_backup_when_primary_footer_is_invalid(self):
        game = "white2"
        raw = bytearray(build_synthetic_save(game))
        footer_crc_offset = PROFILES[game]["main_size"] - 0x100 + PROFILES[game]["info_length"] + 0x0E
        _put_u16(raw, footer_crc_offset, _u16(raw, footer_crc_offset) ^ 1)
        path = Path(self.temp_dir.name) / "fallback.sav"
        path.write_bytes(raw)
        save = Gen5_Save(str(path), game=game)
        self.assertEqual(save.active_copy_base, PROFILES[game]["main_size"])
        self.assertEqual(len(save.party_pokemon), 1)

    def test_rejects_invalid_save_and_bad_pokemon_checksum(self):
        path = Path(self.temp_dir.name) / "invalid.sav"
        path.write_bytes(bytes(SAVE_SIZE))
        with self.assertRaises(ValueError):
            Gen5_Save(str(path), game="black")

        raw = bytearray(build_synthetic_save("black"))
        raw[PARTY_RECORDS_OFFSET + 8] ^= 1  # corrupt an encrypted payload byte
        _rebuild_checksums(raw, "black", 0)
        # Backup intentionally still contains its valid original records, so
        # the parser will use that valid copy; invalidate the backup similarly.
        backup = PROFILES["black"]["main_size"]
        raw[backup + PARTY_RECORDS_OFFSET + 8] ^= 1
        _rebuild_checksums(raw, "black", backup)
        path.write_bytes(raw)
        with self.assertRaises(ValueError):
            Gen5_Save(str(path), game="black")

    def test_rejects_wrong_file_size(self):
        path = Path(self.temp_dir.name) / "short.sav"
        path.write_bytes(bytes(100))
        with self.assertRaisesRegex(ValueError, "512 KiB"):
            Gen5_Save(str(path), game="black")


class Gen5SQLiteIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def test_all_gen5_games_run_through_sqlite_and_write_clean_copy(self):
        import db
        from main import import_gen5

        db_path = Path(self.temp_dir.name) / "chemspc.db"
        old_db_name = db.DATABASE_NAME
        db.DATABASE_NAME = str(db_path)
        try:
            for game in ("black", "white", "black2", "white2"):
                input_path = Path(self.temp_dir.name) / f"{game}.sav"
                input_path.write_bytes(build_synthetic_save(game))
                original = input_path.read_bytes()
                with contextlib.redirect_stdout(io.StringIO()):
                    output_path = import_gen5(str(input_path), game)
                self.assertTrue(Path(output_path).exists())
                self.assertEqual(input_path.read_bytes(), original)
                clean = Gen5_Save(output_path, game=game)
                self.assertEqual(clean.party_pokemon, [])
                self.assertTrue(all(not box for box in clean.box_pokemon))

            with sqlite3.connect(db_path) as connection:
                rows = connection.execute(
                    "SELECT generation, source_game, species, name, special_attack_ev, special_defense_ev "
                    "FROM pokemon ORDER BY uid"
                ).fetchall()
            self.assertEqual(len(rows), 8)
            self.assertTrue(all(row[0] == 5 for row in rows))
            self.assertEqual({row[1] for row in rows}, {"black", "white", "black2", "white2"})
            self.assertEqual({row[2] for row in rows}, {25, 133})
        finally:
            db.DATABASE_NAME = old_db_name

    def test_database_failure_does_not_write_output_save(self):
        import main
        path = Path(self.temp_dir.name) / "failure.sav"
        path.write_bytes(build_synthetic_save("black"))
        old_init = main.init_tables
        old_add = main.add_pokemon_batch
        try:
            main.init_tables = lambda: True
            def fail(_pokemon):
                raise RuntimeError("simulated SQLite transaction failure")
            main.add_pokemon_batch = fail
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                main.import_gen5(str(path), "black")
            self.assertFalse(Path(str(path) + ".new").exists())
        finally:
            main.init_tables = old_init
            main.add_pokemon_batch = old_add


if __name__ == "__main__":
    unittest.main()
