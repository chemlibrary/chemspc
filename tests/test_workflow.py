from __future__ import annotations

import io
import re
import tempfile
import unittest
from pathlib import Path

import db
import main
from gen2 import Crystal_Save, Gen2_Save
from save_formats import GAME_SPECS, supported_games
from pokemon import Pokemon


class ChemsPCWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        db.DATABASE_NAME = str(root / "test.db")
        main.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret",
            UPLOAD_FOLDER=str(root / "staging"),
            EXPORT_FOLDER=str(root / "exports"),
        )
        Path(main.app.config["UPLOAD_FOLDER"]).mkdir(parents=True)
        Path(main.app.config["EXPORT_FOLDER"]).mkdir(parents=True)
        db.init_tables()
        self.client = main.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def valid_pokemon(name="Pika", species=25):
        return Pokemon(
            generation=2, name=name, species=species, held_item=0,
            move1=33, move2=45, move3=0, move4=0,
            original_trainer=1234, original_trainer_name="PLAYER", exp=1000,
            hp_ev=0, attack_ev=0, defense_ev=0, speed_ev=0, special_ev=0,
            iv=0, move1_pp=35, move2_pp=40, friendship=70, pokerus=0,
            caught=0, level=10, status_condition=0, current_hp=25, max_hp=25,
            attack=15, defense=14, speed=16, special_attack=20, special_defense=20,
        )

    def make_save(self, path: Path, party=None):
        path.write_bytes(bytes(32768))
        save = Gen2_Save(path)
        save.party_pokemon = list(party or [])
        save.write_save(path.with_name("prepared.sav"))
        return path.with_name("prepared.sav")

    def csrf(self):
        response = self.client.get("/")
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def upload_save(self, path: Path, trailer: bytes = b""):
        return self.client.post(
            "/open-save",
            data={"csrf_token": self.csrf(), "game": "gold-silver", "save_file": (io.BytesIO(path.read_bytes() + trailer), "test.sav")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )

    def test_registry_covers_the_repository_supported_generations(self):
        generations = {spec.generation for spec in GAME_SPECS.values()}
        self.assertEqual(generations, set(range(1, 8)))
        self.assertGreaterEqual(len(supported_games()), 25)

    def test_database_round_trip_preserves_native_record_payload(self):
        pokemon = Pokemon(generation=4, name="Porygon", species=137)
        pokemon.gen4_box_record = bytes([0xA5]) * 136
        pokemon.gen4_box_index = 4
        pokemon.gen4_box_slot = 12
        db.add_pokemon(pokemon)
        row = db.list_pokemon(active=True)[0]
        restored = db.row_to_pokemon(row)
        self.assertEqual(restored.gen4_box_record, pokemon.gen4_box_record)
        self.assertEqual(restored.gen4_box_index, 4)
        self.assertEqual(restored.gen4_box_slot, 12)

    def test_crystal_uses_its_own_layout_and_checksums(self):
        original = Path(self.temp.name) / "crystal-source.sav"
        original.write_bytes(bytes(32768))
        save = Crystal_Save(original)
        pokemon = self.valid_pokemon()
        save.party_pokemon = [pokemon]
        output = Path(self.temp.name) / "crystal-output.sav"
        save.write_save(output)
        parsed = Crystal_Save(output)
        self.assertEqual(len(parsed.party_pokemon), 1)
        self.assertEqual(parsed.party_pokemon[0].name, "Pika")
        self.assertEqual(parsed.save_bytes[0x2008], 0x63)
        self.assertEqual(parsed.save_bytes[0x1208], 0x63)

    def test_upload_trims_emulator_added_bytes_before_parsing(self):
        path = self.make_save(Path(self.temp.name) / "with-tail.sav")
        response = self.upload_save(path, trailer=b"EMU-RTC-FOOTER" * 20)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Removed", response.data)
        with self.client.session_transaction() as session:
            staged_path = Path(main.app.config["UPLOAD_FOLDER"]) / session["workflow_id"] / "source.sav"
        self.assertEqual(staged_path.stat().st_size, 32768)
        self.assertEqual(staged_path.read_bytes(), path.read_bytes())

    def test_short_upload_is_rejected_without_activating_workflow(self):
        response = self.client.post(
            "/open-save",
            data={
                "csrf_token": self.csrf(),
                "game": "gold-silver",
                "save_file": (io.BytesIO(bytes(32767)), "short.sav"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"too small", response.data)
        with self.client.session_transaction() as session:
            self.assertNotIn("workflow_id", session)

    def test_save_round_trip_rebuilds_party_and_boxes(self):
        path = self.make_save(Path(self.temp.name) / "initial.sav", [self.valid_pokemon()])
        parsed = Gen2_Save(path)
        self.assertEqual(len(parsed.party_pokemon), 1)
        self.assertEqual(parsed.party_pokemon[0].name, "Pika")
        self.assertEqual(len(parsed.box_pokemon), 14)
        self.assertEqual(len(parsed.export_gen2_party_list()), 428)
        self.assertEqual(len(parsed.export_gen2_boxes()), 15456)

    def test_import_selected_pokemon_removes_it_from_output_save(self):
        path = self.make_save(Path(self.temp.name) / "initial.sav", [self.valid_pokemon()])
        response = self.upload_save(path)
        self.assertEqual(response.status_code, 200)
        token = self.csrf()
        response = self.client.post("/finalize", data={"csrf_token": token, "import_slot": "party:0"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"TRANSFER FINALIZED", response.data)
        self.assertEqual(len(db.list_pokemon(active=True)), 1)
        imported = db.list_pokemon(active=True)[0]
        self.assertEqual(imported["name"], "Pika")
        # The final page link serves an output with the imported Pokémon removed.
        match = re.search(rb'href="/download/([0-9a-f]{32})"', response.data)
        self.assertIsNotNone(match)
        downloaded = self.client.get("/download/" + match.group(1).decode())
        self.assertEqual(downloaded.status_code, 200)
        output = Path(self.temp.name) / "downloaded.sav"
        output.write_bytes(downloaded.data)
        self.assertEqual(len(Gen2_Save(output).party_pokemon), 0)

    def test_export_moves_active_row_to_inactive(self):
        db.add_pokemon(self.valid_pokemon())
        uid = db.list_pokemon(active=True)[0]["uid"]
        path = self.make_save(Path(self.temp.name) / "blank.sav")
        response = self.upload_save(path)
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/finalize", data={"csrf_token": self.csrf(), "export_uid": str(uid)}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"TRANSFER FINALIZED", response.data)
        self.assertEqual([row["uid"] for row in db.list_pokemon(active=True)], [])
        inactive = db.list_pokemon(active=False)
        self.assertEqual(len(inactive), 1)
        self.assertEqual(inactive[0]["uid"], uid)
        match = re.search(rb'href="/download/([0-9a-f]{32})"', response.data)
        self.assertIsNotNone(match)
        downloaded = self.client.get("/download/" + match.group(1).decode())
        output = Path(self.temp.name) / "exported.sav"
        output.write_bytes(downloaded.data)
        parsed = Gen2_Save(output)
        self.assertEqual(len(parsed.party_pokemon), 0)
        self.assertEqual(sum(len(box) for box in parsed.box_pokemon), 1)
        self.assertEqual(parsed.box_pokemon[0][0].name, "Pika")

    def test_incompatible_generation_cannot_be_exported(self):
        pokemon = self.valid_pokemon()
        pokemon.generation = 1
        db.add_pokemon(pokemon)
        row = db.list_pokemon(active=True)[0]
        path = self.make_save(Path(self.temp.name) / "blank.sav")
        self.upload_save(path)
        response = self.client.post("/finalize", data={"csrf_token": self.csrf(), "export_uid": str(row["uid"])}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("cannot be exported to Generation 2".encode(), response.data)
        self.assertEqual(len(db.list_pokemon(active=True)), 1)
        self.assertEqual(len(db.list_pokemon(active=False)), 0)


if __name__ == "__main__":
    unittest.main()
