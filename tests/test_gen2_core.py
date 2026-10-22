"""Core parser, writer, and SQLite tests that do not need Flask."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import db
from gen2 import BOX_OFFSETS, Crystal_Save, Gen2_Save
from pokemon import Pokemon


class Gen2CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        db.DATABASE_NAME = str(root / "test.db")
        db.init_tables()
        self.root = root

    def tearDown(self):
        self.temp.cleanup()

    def test_party_round_trip_and_fixed_section_sizes(self):
        pokemon = Pokemon(
            generation=2, name="Pika", species=25, held_item=0, move1=33, move2=45,
            original_trainer=1234, original_trainer_name="PLAYER", exp=1000,
            move1_pp=35, move2_pp=40, friendship=70, level=10, current_hp=25,
            max_hp=25, attack=15, defense=14, speed=16, special_attack=20,
            special_defense=20,
        )
        source = self.root / "blank.sav"
        source.write_bytes(bytes(32768))
        save = Gen2_Save(source)
        save.party_pokemon = [pokemon]
        target = self.root / "output.sav"
        save.write_save(target)
        parsed = Gen2_Save(target)
        self.assertEqual(len(parsed.party_pokemon), 1)
        self.assertEqual(parsed.party_pokemon[0].name, "Pika")
        self.assertEqual(parsed.party_pokemon[0].original_trainer_name, "PLAYER")
        self.assertEqual(len(parsed.export_gen2_party_list()), 428)
        self.assertEqual(len(parsed.export_gen2_boxes()), 15456)
        self.assertEqual(len(parsed.box_pokemon), 14)
        self.assertEqual(source.read_bytes(), bytes(32768), "writer must never alter source save")

    def test_pc_box_bank_boundary_uses_real_offsets(self):
        pokemon = Pokemon(
            generation=2, name="Eevee", species=133, held_item=0,
            original_trainer=21, original_trainer_name="PLAYER", exp=100,
            level=5,
        )
        source = self.root / "banked.sav"
        source.write_bytes(bytes(32768))
        save = Gen2_Save(source)
        save.box_pokemon[7] = [pokemon]
        target = self.root / "banked-output.sav"
        save.write_save(target)
        parsed = Gen2_Save(target)
        self.assertEqual(parsed.box_pokemon[7][0].name, "Eevee")
        self.assertEqual(target.read_bytes()[BOX_OFFSETS[7]], 1)

    def test_crystal_round_trip_uses_distinct_party_and_checksum_offsets(self):
        pokemon = Pokemon(
            generation=2, name="Pika", species=25, held_item=0,
            original_trainer=1234, original_trainer_name="PLAYER", exp=1000,
            level=10, current_hp=25, max_hp=25, attack=15, defense=14,
            speed=16, special_attack=20, special_defense=20,
        )
        source = self.root / "crystal.sav"
        source.write_bytes(bytes(32768))
        save = Crystal_Save(source)
        save.party_pokemon = [pokemon]
        target = self.root / "crystal-output.sav"
        save.write_save(target)
        parsed = Crystal_Save(target)
        self.assertEqual(parsed.party_pokemon[0].name, "Pika")
        self.assertEqual(parsed.save_bytes[0x2008], 0x63)
        self.assertEqual(parsed.save_bytes[0x1208], 0x63)

    def test_active_to_inactive_move_preserves_uid(self):
        pokemon = Pokemon(generation=2, name="Pika", species=25, level=10)
        db.add_pokemon(pokemon)
        row = db.list_pokemon(active=True)[0]
        uid = row["uid"]
        conn = db.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            db.move_active_to_inactive(conn, uid)
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(db.list_pokemon(active=True), [])
        inactive = db.list_pokemon(active=False)
        self.assertEqual(len(inactive), 1)
        self.assertEqual(inactive[0]["uid"], uid)
        self.assertEqual(inactive[0]["name"], "Pika")


if __name__ == "__main__":
    unittest.main()
