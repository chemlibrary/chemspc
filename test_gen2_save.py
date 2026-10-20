"""Structural tests for English Gold/Silver serialization.

If the repository's chempy helper package is not installed, these tests install
small test-only equivalents for its integer conversion and safe-write helpers.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path


if importlib.util.find_spec("chempy") is None:
    chempy = types.ModuleType("chempy")
    chempy.__path__ = []  # mark as a package
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
sys.path.insert(0, str(PROJECT_ROOT))

from gen2 import (  # noqa: E402
    BOX_DATA_SIZE,
    BOX_OFFSETS,
    BOX_SIZE,
    CURRENT_BOX_OFFSET,
    CURRENT_BOX_NUMBER_OFFSET,
    PARTY_OFFSET,
    PARTY_SIZE,
    Gen2_Save,
)
from pokemon import Pokemon  # noqa: E402


def make_pokemon(name="CYNDAQUIL", ot="ASH", species=155):
    return Pokemon(
        generation=2,
        name=name,
        species=species,
        held_item=0,
        move1=33,
        move2=45,
        move3=0,
        move4=0,
        original_trainer=0x1234,
        original_trainer_name=ot,
        exp=12345,
        hp_ev=1,
        attack_ev=2,
        defense_ev=3,
        speed_ev=4,
        special_ev=5,
        iv=0x1234,
        move1_pp=35,
        move2_pp=30,
        move3_pp=0,
        move4_pp=0,
        friendship=70,
        pokerus=0,
        caught=0,
        level=12,
        status_condition=0,
        current_hp=29,
        max_hp=32,
        attack=20,
        defense=18,
        speed=22,
        special_attack=23,
        special_defense=21,
    )


class Gen2SaveTests(unittest.TestCase):
    def make_blank_save(self, directory):
        path = os.path.join(directory, "blank.sav")
        data = bytearray(0x8000)
        data[CURRENT_BOX_NUMBER_OFFSET] = 0
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def test_serialized_structure_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            save = Gen2_Save(self.make_blank_save(directory))
            save.party_pokemon = [make_pokemon()]
            save.box_pokemon[0] = [make_pokemon()]
            self.assertEqual(len(save.export_gen2_party_list()), PARTY_SIZE)
            self.assertEqual(len(save.export_gen2_boxes()), 14 * BOX_SIZE)

    def test_name_fields_and_section_order_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_blank_save(directory)
            save = Gen2_Save(path)
            save.party_pokemon = [make_pokemon(name="1234567890", ot="ASH")]
            save.box_pokemon = [[] for _ in range(14)]
            save.write_save()

            reread = Gen2_Save(path + ".new")
            self.assertEqual(len(reread.party_pokemon), 1)
            self.assertEqual(reread.party_pokemon[0].name, "1234567890")
            self.assertEqual(reread.party_pokemon[0].original_trainer_name, "ASH")

    def test_all_box_offsets_written_without_compacting_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_blank_save(directory)
            with open(path, "rb") as handle:
                data = bytearray(handle.read())
            data[0x5E30:0x6000] = b"\xA5" * (0x6000 - 0x5E30)
            with open(path, "wb") as handle:
                handle.write(data)

            save = Gen2_Save(path)
            save.party_pokemon = []
            save.box_pokemon = [[] for _ in range(14)]
            save.box_pokemon[7] = [make_pokemon(name="BOXEIGHT", species=25)]
            save.box_pokemon[13] = [make_pokemon(name="BOX14", species=26)]
            expected = save.export_gen2_boxes()
            save.write_save()
            with open(path + ".new", "rb") as handle:
                output = bytearray(handle.read())

            for index, offset in enumerate(BOX_OFFSETS):
                self.assertEqual(
                    output[offset:offset + BOX_SIZE],
                    expected[index * BOX_SIZE:(index + 1) * BOX_SIZE],
                )
            self.assertEqual(output[0x5E30:0x6000], b"\xA5" * (0x6000 - 0x5E30))
            self.assertEqual(output[0x6000], 1)
            self.assertEqual(output[0x79E0], 1)

    def test_current_box_overrides_stale_numbered_copy_on_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_blank_save(directory)
            save = Gen2_Save(path)
            live_box = save._serialize_box([make_pokemon(name="LIVEBOX", species=133)])
            save.save_bytes[CURRENT_BOX_NUMBER_OFFSET] = 2
            save.save_bytes[CURRENT_BOX_OFFSET:CURRENT_BOX_OFFSET + BOX_DATA_SIZE] = live_box[:BOX_DATA_SIZE]
            with open(path, "wb") as handle:
                handle.write(save.save_bytes)

            reread = Gen2_Save(path)
            self.assertEqual(len(reread.box_pokemon[2]), 1)
            self.assertEqual(reread.box_pokemon[2][0].name, "LIVEBOX")
            self.assertEqual(reread.box_pokemon[2][0].species, 133)

    def test_backup_regions_and_checksums_are_synchronized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_blank_save(directory)
            save = Gen2_Save(path)
            save.party_pokemon = [make_pokemon()]
            save.box_pokemon = [[] for _ in range(14)]
            save.write_save()
            with open(path + ".new", "rb") as handle:
                output = bytearray(handle.read())

            mappings = (
                (0x2009, 0x222E, 0x15C7),
                (0x222F, 0x23D8, 0x3D96),
                (0x23D9, 0x2855, 0x0C6B),
                (0x2856, 0x2889, 0x7E39),
                (0x288A, 0x2D68, 0x10E8),
            )
            for source_start, source_end, target_start in mappings:
                length = source_end - source_start + 1
                self.assertEqual(
                    output[target_start:target_start + length],
                    output[source_start:source_end + 1],
                )

            primary = sum(output[0x2009:0x2D69]) & 0xFFFF
            secondary = (
                sum(output[0x0C6B:0x17ED])
                + sum(output[0x3D96:0x3F40])
                + sum(output[0x7E39:0x7E6D])
            ) & 0xFFFF
            self.assertEqual(int.from_bytes(output[0x2D69:0x2D6B], "little"), primary)
            self.assertEqual(int.from_bytes(output[0x7E6D:0x7E6F], "little"), secondary)
            self.assertEqual(len(output), 0x8000)

    def test_current_box_copy_matches_selected_numbered_box(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.make_blank_save(directory)
            save = Gen2_Save(path)
            save.save_bytes[CURRENT_BOX_NUMBER_OFFSET] = 3
            save.box_pokemon = [[] for _ in range(14)]
            save.box_pokemon[3] = [make_pokemon(name="MATCH", species=4)]
            save.write_save()
            with open(path + ".new", "rb") as handle:
                output = bytearray(handle.read())
            selected_offset = BOX_OFFSETS[3]
            self.assertEqual(
                output[CURRENT_BOX_OFFSET:CURRENT_BOX_OFFSET + BOX_DATA_SIZE],
                output[selected_offset:selected_offset + BOX_DATA_SIZE],
            )


if __name__ == "__main__":
    unittest.main()
