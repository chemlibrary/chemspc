from __future__ import annotations

import io
import re
import tempfile
import unittest
from pathlib import Path

import db
import main
from gen2 import Gen2_Save
from pokemon import Pokemon


class ChemSPCWorkflowTests(unittest.TestCase):
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

    def upload_save(self, path: Path):
        return self.client.post(
            "/open-save",
            data={"csrf_token": self.csrf(), "save_file": (io.BytesIO(path.read_bytes()), "test.sav")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )

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
        self.assertEqual(len(parsed.party_pokemon), 1)
        self.assertEqual(parsed.party_pokemon[0].name, "Pika")

    def test_incompatible_generation_cannot_be_exported(self):
        pokemon = self.valid_pokemon()
        pokemon.generation = 1
        db.add_pokemon(pokemon)
        row = db.list_pokemon(active=True)[0]
        path = self.make_save(Path(self.temp.name) / "blank.sav")
        self.upload_save(path)
        response = self.client.post("/finalize", data={"csrf_token": self.csrf(), "export_uid": str(row["uid"])}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Only Generation II Pokémon".encode(), response.data)
        self.assertEqual(len(db.list_pokemon(active=True)), 1)
        self.assertEqual(len(db.list_pokemon(active=False)), 0)


if __name__ == "__main__":
    unittest.main()
