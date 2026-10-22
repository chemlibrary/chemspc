"""Regression tests for automatic save-generation/layout detection."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TESTS_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(TESTS_ROOT))

import main  # noqa: E402
from gen2 import Crystal_Save, Gen2_Save  # noqa: E402


class AutoDetectionTests(unittest.TestCase):
    @staticmethod
    def fixture_builders():
        # Import fixtures at test runtime, after pytest has completed collection.
        # Some legacy format tests install minimal chempy stubs during import.
        from test_gen1_save import build_synthetic_save as build_gen1
        from test_gen3_save import build_synthetic_save as build_gen3
        from test_gen4_save import build_synthetic_save as build_gen4
        from test_gen5_save import build_synthetic_save as build_gen5
        from test_gen6_save import build_synthetic_save as build_gen6
        from test_gen7_save import build_synthetic_save as build_gen7
        return build_gen1, build_gen3, build_gen4, build_gen5, build_gen6, build_gen7

    def detect(self, directory: str, filename: str, data: bytes):
        path = Path(directory) / filename
        path.write_bytes(data)
        return main.detect_save_game(str(path))

    @staticmethod
    def build_valid_gen2(save_class, directory: str, filename: str) -> bytes:
        source = Path(directory) / filename
        initial = bytearray(0x8000)
        initial[0x2009] = 0x80  # non-empty trainer/save data in the main block
        source.write_bytes(initial)
        save = save_class(str(source))
        save.party_pokemon = []
        save.box_pokemon = [[] for _ in range(14)]
        output_path = save.write_save()
        return Path(output_path).read_bytes()

    def test_detects_generation_one_and_oversized_generation_one(self):
        build_gen1 = self.fixture_builders()[0]
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                self.detect(directory, "red.sav", build_gen1()),
                (1, "red", "generation-1"),
            )
            oversized = build_gen1(large=True)
            self.assertEqual(
                self.detect(directory, "yellow-oversized.sav", oversized),
                (1, "red", "generation-1"),
            )
            self.assertEqual(
                self.detect(directory, "yellow-padded.sav", oversized + bytes(0x10000)),
                (1, "red", "generation-1"),
            )

    def test_distinguishes_generation_two_checksum_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            gold_silver = self.build_valid_gen2(Gen2_Save, directory, "gold-silver.sav")
            crystal = self.build_valid_gen2(Crystal_Save, directory, "crystal.sav")
            self.assertEqual(
                self.detect(directory, "gold-silver-valid.sav", gold_silver),
                (2, "gold-silver", "gold-silver"),
            )
            self.assertEqual(
                self.detect(directory, "crystal-valid.sav", crystal),
                (2, "crystal", "crystal"),
            )

    def test_detects_generations_three_through_seven(self):
        _, build_gen3, build_gen4, build_gen5, build_gen6, build_gen7 = self.fixture_builders()
        fixtures = (
            ("gen3.sav", build_gen3("emerald"), (3, "auto", "generation-3")),
            ("gen4.sav", build_gen4("diamond"), (4, "diamond", "generation-4")),
            ("gen5.sav", build_gen5("black"), (5, "black", "generation-5")),
            ("gen6.main", build_gen6("x"), (6, "x", "generation-6")),
            ("gen7.main", build_gen7("sun"), (7, "sun", "generation-7")),
        )
        with tempfile.TemporaryDirectory() as directory:
            for filename, data, expected in fixtures:
                with self.subTest(filename=filename):
                    self.assertEqual(self.detect(directory, filename, data), expected)

    def test_detects_alternate_layout_families(self):
        _, _, build_gen4, build_gen5, build_gen6, build_gen7 = self.fixture_builders()
        fixtures = (
            ("platinum.sav", build_gen4("platinum"), (4, "platinum", "generation-4")),
            ("heartgold.sav", build_gen4("heartgold"), (4, "heartgold", "generation-4")),
            ("black2.sav", build_gen5("black2"), (5, "black2", "generation-5")),
            ("oras.main", build_gen6("omegaruby"), (6, "omegaruby", "generation-6")),
            ("ultrasun.main", build_gen7("ultrasun"), (7, "ultrasun", "generation-7")),
        )
        with tempfile.TemporaryDirectory() as directory:
            for filename, data, expected in fixtures:
                with self.subTest(filename=filename):
                    self.assertEqual(self.detect(directory, filename, data), expected)

    def test_rejects_unknown_32k_file_instead_of_guessing_generation_two(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Could not identify this 32 KiB save"):
                self.detect(directory, "unknown.sav", bytes(0x8000))

    def test_generation_two_rejects_substring_game_names(self):
        # Previously, `game in ("crystal")` was a substring check, so "r"
        # incorrectly selected the Crystal reader.
        with self.assertRaisesRegex(ValueError, "Unsupported Generation II game"):
            main.import_gen2("unused.sav", game="r")

    def test_auto_cli_dispatches_to_the_detected_generation(self):
        scenarios = (
            (1, "red", "generation-1", "import_gen1"),
            (2, "crystal", "crystal", "import_gen2"),
            (3, "auto", "generation-3", "import_gen3"),
            (4, "platinum", "generation-4", "import_gen4"),
            (5, "black2", "generation-5", "import_gen5"),
            (6, "omegaruby", "generation-6", "import_gen6"),
            (7, "ultrasun", "generation-7", "import_gen7"),
        )
        for generation, game, provenance, importer_name in scenarios:
            with self.subTest(generation=generation):
                with patch("sys.argv", ["main.py", "sample.sav", "--game", "auto"]), \
                     patch.object(
                         main, "detect_save_game",
                         return_value=(generation, game, provenance),
                     ), \
                     patch.object(main, importer_name) as importer:
                    main.main()
                    importer.assert_called_once_with(
                        "sample.sav", game=game, source_game=provenance
                    )


if __name__ == "__main__":
    unittest.main()
