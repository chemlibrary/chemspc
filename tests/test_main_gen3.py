"""Integration tests for Gen III save-to-SQLite extraction."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

# The existing Gen II implementation depends on the project's `chempy` helper.
# Install small test-only stand-ins when that package is absent.
if "chempy" not in sys.modules and importlib.util.find_spec("chempy") is None:
    chempy = types.ModuleType("chempy")
    chempy.__path__ = []
    primitives = types.ModuleType("chempy.primitives")
    files = types.ModuleType("chempy.files")
    primitives.get_int = lambda data: int.from_bytes(data, "big")
    primitives.get_bytes = lambda value, length: int(value).to_bytes(length, "big")

    def bytes_safe_write(path, contents):
        with open(path, "wb") as handle:
            handle.write(bytes(contents))
        return True

    files.bytes_safe_write = bytes_safe_write
    sys.modules["chempy"] = chempy
    sys.modules["chempy.primitives"] = primitives
    sys.modules["chempy.files"] = files

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(TESTS_ROOT))

from test_gen3_save import build_synthetic_save  # noqa: E402
import db  # noqa: E402
from main import import_gen3  # noqa: E402


class MainGen3IntegrationTests(unittest.TestCase):
    def test_extracts_party_and_box_to_sqlite_before_clearing_output_save(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "synthetic-emerald.sav"
            db_path = Path(directory) / "chemspc.db"
            input_path.write_bytes(build_synthetic_save(game="emerald"))
            old_db_name = db.DATABASE_NAME
            db.DATABASE_NAME = str(db_path)
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    output_path = import_gen3(str(input_path), game="emerald")

                with sqlite3.connect(db_path) as connection:
                    rows = connection.execute(
                        """SELECT generation, source_game, name, species,
                                  special_attack_ev, special_defense_ev
                           FROM pokemon ORDER BY uid"""
                    ).fetchall()
                self.assertEqual(len(rows), 2)
                self.assertTrue(all(row[0] == 3 for row in rows))
                self.assertTrue(all(row[1] == "emerald" for row in rows))
                self.assertTrue(all(row[2] == "PIKACHU" for row in rows))
                self.assertTrue(all(row[3] == 25 for row in rows))
                self.assertEqual((rows[0][4], rows[0][5]), (8, 8))

                from gen3 import Gen3_Save
                cleaned = Gen3_Save(output_path, game="emerald")
                self.assertEqual(cleaned.party_pokemon, [])
                self.assertTrue(all(not box for box in cleaned.box_pokemon))
                self.assertEqual(Path(output_path).stat().st_size, 0x20000)
                self.assertTrue(input_path.exists())
                self.assertEqual(input_path.stat().st_size, 0x20000)
            finally:
                db.DATABASE_NAME = old_db_name

    def test_all_five_gen3_games_run_through_sqlite_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "chemspc.db"
            old_db_name = db.DATABASE_NAME
            db.DATABASE_NAME = str(db_path)
            try:
                games = ("ruby", "sapphire", "emerald", "firered", "leafgreen")
                for game in games:
                    input_path = Path(directory) / f"synthetic-{game}.sav"
                    input_path.write_bytes(build_synthetic_save(game=game))
                    with contextlib.redirect_stdout(io.StringIO()):
                        output_path = import_gen3(str(input_path), game=game)
                    self.assertTrue(Path(output_path).exists(), game)

                with sqlite3.connect(db_path) as connection:
                    counts = dict(connection.execute(
                        "SELECT source_game, COUNT(*) FROM pokemon GROUP BY source_game"
                    ).fetchall())
                self.assertEqual(counts, {game: 2 for game in games})
            finally:
                db.DATABASE_NAME = old_db_name

    def test_database_migrates_existing_tables_with_gen3_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "old.db"
            old_db_name = db.DATABASE_NAME
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
                with sqlite3.connect(db_path) as connection:
                    for table in ("pokemon", "inactive_pokemon"):
                        columns = {
                            row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                        }
                        self.assertTrue({
                            "source_game", "special_attack_ev", "special_defense_ev"
                        }.issubset(columns))
            finally:
                db.DATABASE_NAME = old_db_name


if __name__ == "__main__":
    unittest.main()
