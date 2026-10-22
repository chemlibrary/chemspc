"""SQLite extraction integration tests for English Generation I games."""
from __future__ import annotations

import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db
import main
from gen1 import Gen1_Save
from tests.test_gen1_save import build_synthetic_save


class MainGen1IntegrationTests(unittest.TestCase):
    def test_all_three_games_import_into_sqlite_and_write_clean_save(self):
        with tempfile.TemporaryDirectory() as directory:
            old_db = db.DATABASE_NAME
            db.DATABASE_NAME = str(Path(directory) / "chemspc.db")
            try:
                for game in ("red", "blue", "yellow"):
                    source = Path(directory) / f"{game}.sav"
                    original = build_synthetic_save()
                    source.write_bytes(original)
                    with contextlib.redirect_stdout(io.StringIO()):
                        output_path = main.import_gen1(str(source), game=game)
                    self.assertTrue(Path(output_path).exists())
                    self.assertEqual(source.read_bytes(), original)
                    clean = Gen1_Save(output_path, game=game)
                    self.assertEqual(clean.party_pokemon, [])
                    self.assertTrue(all(not box for box in clean.box_pokemon))

                with sqlite3.connect(db.DATABASE_NAME) as connection:
                    rows = connection.execute(
                        "SELECT generation, source_game, gen1_internal_species, species, name "
                        "FROM pokemon ORDER BY uid"
                    ).fetchall()
                self.assertEqual(len(rows), 6)
                by_game = {}
                for generation, game, internal_species, species, name in rows:
                    self.assertEqual(generation, 1)
                    by_game.setdefault(game, set()).add((internal_species, species, name))
                self.assertEqual(set(by_game), {"red", "blue", "yellow"})
                expected = {(0x54, 25, "PIKA"), (0x66, 133, "EEVEE")}
                self.assertTrue(all(values == expected for values in by_game.values()))
            finally:
                db.DATABASE_NAME = old_db

    def test_database_failure_does_not_write_output_save(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "red.sav"
            source.write_bytes(build_synthetic_save())
            with patch.object(main, "init_tables"), patch.object(
                main, "add_pokemon_batch", side_effect=RuntimeError("simulated database failure")
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(RuntimeError, "simulated database failure"):
                        main.import_gen1(str(source), game="red")
            self.assertFalse(Path(str(source) + ".new").exists())


if __name__ == "__main__":
    unittest.main()
