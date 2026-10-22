from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from save_formats import GAME_SPECS, SAVE_SIZES, required_save_size, trim_save_file


class UploadNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_each_supported_title_has_a_required_size_and_trims_trailers(self):
        self.assertEqual(set(SAVE_SIZES), set(GAME_SPECS))
        self.assertEqual({spec.generation for spec in GAME_SPECS.values()}, set(range(1, 8)))
        trailer = b"EMULATOR-RUNTIME-FOOTER" * 7
        for game in GAME_SPECS:
            with self.subTest(game=game):
                required = required_save_size(game)
                path = self.root / f"{game}.sav"
                path.write_bytes(b"\xA5" * required + trailer)
                original, retained = trim_save_file(path, game)
                self.assertEqual(original, required + len(trailer))
                self.assertEqual(retained, required)
                self.assertEqual(path.stat().st_size, required)
                # Normalization trims only the suffix; bytes in the save itself stay intact.
                self.assertEqual(path.read_bytes(), b"\xA5" * required)

    def test_exact_size_file_is_unchanged(self):
        path = self.root / "exact.sav"
        expected = required_save_size("omegaruby")
        data = bytes((i % 251 for i in range(expected)))
        path.write_bytes(data)
        original, retained = trim_save_file(path, "omegaruby")
        self.assertEqual((original, retained), (expected, expected))
        self.assertEqual(path.read_bytes(), data)

    def test_short_file_is_rejected_without_modification(self):
        path = self.root / "short.sav"
        data = b"incomplete save"
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "too small"):
            trim_save_file(path, "gold-silver")
        self.assertEqual(path.read_bytes(), data)

    def test_title_specific_3ds_sizes(self):
        self.assertEqual(required_save_size("x"), 0x65600)
        self.assertEqual(required_save_size("omegaruby"), 0x76000)
        self.assertEqual(required_save_size("sun"), 0x6BE00)
        self.assertEqual(required_save_size("ultrasun"), 0x6CC00)


if __name__ == "__main__":
    unittest.main()
