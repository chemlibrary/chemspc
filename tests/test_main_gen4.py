"""Integration tests for Generation IV extraction into SQLite."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

# Make the existing project helper optional for tests, as in test_gen4_save.
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
TESTS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(TESTS_ROOT))

from test_gen4_save import build_synthetic_save  # noqa: E402
import db  # noqa: E402
import main as app  # noqa: E402
from gen4 import Gen4_Save  # noqa: E402


class MainGen4IntegrationTests(unittest.TestCase):
    def test_all_five_gen4_games_import_and_clear_party_and_boxes(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "chemspc.db"
            previous_db_path = db.DATABASE_NAME
            db.DATABASE_NAME = str(db_path)
            try:
                for game in ("diamond", "pearl", "platinum", "heartgold", "soulsilver"):
                    input_path = Path(directory) / f"synthetic-{game}.sav"
                    input_path.write_bytes(build_synthetic_save(game))
                    with contextlib.redirect_stdout(io.StringIO()):
                        output_path = app.import_gen4(str(input_path), game=game)

                    self.assertTrue(Path(output_path).exists())
                    self.assertEqual(input_path.stat().st_size, 0x80000)
                    cleaned = Gen4_Save(output_path, game=game)
                    self.assertEqual(cleaned.party_pokemon, [])
                    self.assertTrue(all(not box for box in cleaned.box_pokemon))

                with sqlite3.connect(db_path) as connection:
                    rows = connection.execute(
                        """SELECT generation, source_game, name, species, personality,
                                  game_of_origin, met_location, egg_location
                           FROM pokemon ORDER BY source_game"""
                    ).fetchall()
                self.assertEqual(len(rows), 10)  # party + one PC Pokémon, five games
                self.assertEqual({row[0] for row in rows}, {4})
                self.assertEqual({row[1] for row in rows}, {
                    "diamond", "pearl", "platinum", "heartgold", "soulsilver"
                })
                self.assertTrue(all(row[2] == "PIKACHU" and row[3] == 25 for row in rows))
                self.assertTrue(all(row[4] == 0x12345678 for row in rows))
            finally:
                db.DATABASE_NAME = previous_db_path

    def test_database_failure_does_not_write_or_modify_input_save(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "synthetic-diamond.sav"
            original = build_synthetic_save("diamond")
            input_path.write_bytes(original)
            previous_db_path = db.DATABASE_NAME
            previous_insert = app.add_pokemon_batch
            db.DATABASE_NAME = str(Path(directory) / "chemspc.db")

            def fail_insert(_pokemon):
                raise sqlite3.OperationalError("simulated database failure")

            app.add_pokemon_batch = fail_insert
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(sqlite3.OperationalError):
                        app.import_gen4(str(input_path), game="diamond")
                self.assertEqual(input_path.read_bytes(), original)
                self.assertFalse(Path(str(input_path) + ".new").exists())
            finally:
                app.add_pokemon_batch = previous_insert
                db.DATABASE_NAME = previous_db_path

    def test_existing_database_migrates_generation_four_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "old.db"
            previous_db_path = db.DATABASE_NAME
            db.DATABASE_NAME = str(db_path)
            try:
                with sqlite3.connect(db_path) as connection:
                    connection.execute(
                        "CREATE TABLE pokemon (uid INTEGER PRIMARY KEY, generation INTEGER, name TEXT)"
                    )
                    connection.execute(
                        "CREATE TABLE inactive_pokemon (uid INTEGER, generation INTEGER, name TEXT)"
                    )
                db.init_tables()
                expected = {
                    "source_game", "special_attack_ev", "special_defense_ev",
                    "game_of_origin", "met_location", "egg_location", "met_level",
                    "pokeball", "encounter_type", "egg_date", "met_date",
                    "original_trainer_gender",
                }
                with sqlite3.connect(db_path) as connection:
                    for table in ("pokemon", "inactive_pokemon"):
                        found = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                        self.assertTrue(expected.issubset(found))
            finally:
                db.DATABASE_NAME = previous_db_path


if __name__ == "__main__":
    unittest.main()
