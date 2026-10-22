"""Synthetic structure, parsing, checksum, and round-trip tests for Gen I."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gen1 import (
    BANK_BOX_CHECKSUM_OFFSET,
    BOX_CAPACITY,
    BOX_DATA_START,
    BOX_NICKNAMES_OFFSET,
    BOX_OFFSETS,
    BOX_OT_NAMES_OFFSET,
    BOX_RECORD_SIZE,
    BOX_SIZE,
    CURRENT_BOX_NUMBER_OFFSET,
    CURRENT_BOX_OFFSET,
    MAIN_CHECKSUM_OFFSET,
    MAIN_DATA_START,
    PARTY_OFFSET,
    PARTY_SIZE,
    SAVE_SIZE,
    Gen1_Save,
    _checksum,
)


def encode_text(text: str) -> bytes:
    encoded = bytearray()
    for character in text:
        if "A" <= character <= "Z":
            encoded.append(0x80 + ord(character) - ord("A"))
        elif "a" <= character <= "z":
            encoded.append(0xA0 + ord(character) - ord("a"))
        elif "0" <= character <= "9":
            encoded.append(0xF6 + ord(character) - ord("0"))
        elif character == " ":
            encoded.append(0x7F)
        elif character in ("'", "-", ".", ",", "!", "?"):
            encoded.append({"'": 0xE0, "-": 0xE3, ".": 0xE8,
                            ",": 0xF4, "!": 0xE7, "?": 0xE6}[character])
        else:
            raise ValueError(f"Unsupported test character: {character!r}")
    if len(encoded) > 10:
        raise ValueError("Gen I names have at most 10 glyphs")
    return bytes(encoded + b"\x50" * (11 - len(encoded)))


def make_record(internal_species: int, *, party: bool, level: int = 12,
                trainer_id: int = 0x1234) -> bytes:
    record = bytearray(44 if party else BOX_RECORD_SIZE)
    record[0] = internal_species
    record[1:3] = (20).to_bytes(2, "big")
    record[3] = level
    record[4] = 0
    record[5:7] = bytes((0x17, 0x17))  # Electric/Electric for Pikachu fixture.
    record[7] = 190  # Gen I catch-rate byte.
    record[8:12] = bytes((33, 45, 98, 0))
    record[12:14] = trainer_id.to_bytes(2, "big")
    record[14:17] = (12500).to_bytes(3, "big")
    for index, value in enumerate((1000, 2000, 3000, 4000, 5000)):
        record[0x11 + index * 2:0x13 + index * 2] = value.to_bytes(2, "big")
    record[0x1B:0x1D] = bytes((0xAB, 0xCD))  # Attack/Defense and Speed/Special DVs.
    record[0x1D:0x21] = bytes((35, 30, 15, 0))
    if party:
        record[0x21] = level
        record[0x22:0x24] = (30).to_bytes(2, "big")
        record[0x24:0x26] = (25).to_bytes(2, "big")
        record[0x26:0x28] = (20).to_bytes(2, "big")
        record[0x28:0x2A] = (22).to_bytes(2, "big")
        record[0x2A:0x2C] = (24).to_bytes(2, "big")
    return bytes(record)


def make_party(pokemon: list[tuple[int, str, str]]) -> bytes:
    data = bytearray(PARTY_SIZE)
    data[0] = len(pokemon)
    data[1:8] = b"\xFF" * 7
    for index, (internal_species, nickname, ot_name) in enumerate(pokemon):
        data[1 + index] = internal_species
        record = make_record(internal_species, party=True)
        start = 8 + index * 44
        data[start:start + 44] = record
        ot_start = 0x110 + index * 11
        name_start = 0x152 + index * 11
        data[ot_start:ot_start + 11] = encode_text(ot_name)
        data[name_start:name_start + 11] = encode_text(nickname)
    return bytes(data)


def make_box(pokemon: list[tuple[int, str, str]]) -> bytes:
    data = bytearray(BOX_SIZE)
    data[0] = len(pokemon)
    data[1:22] = b"\xFF" * 21
    for index, (internal_species, nickname, ot_name) in enumerate(pokemon):
        data[1 + index] = internal_species
        start = BOX_DATA_START + index * BOX_RECORD_SIZE
        data[start:start + BOX_RECORD_SIZE] = make_record(internal_species, party=False)
        ot_start = BOX_OT_NAMES_OFFSET + index * 11
        name_start = BOX_NICKNAMES_OFFSET + index * 11
        data[ot_start:ot_start + 11] = encode_text(ot_name)
        data[name_start:name_start + 11] = encode_text(nickname)
    return bytes(data)


def finalize_checksums(data: bytearray) -> None:
    for base, checksum_offset in BANK_BOX_CHECKSUM_OFFSET.items():
        data[checksum_offset] = _checksum(data[base:checksum_offset])
        for i in range(6):
            start = base + i * BOX_SIZE
            data[checksum_offset + 1 + i] = _checksum(data[start:start + BOX_SIZE])
    data[MAIN_CHECKSUM_OFFSET] = _checksum(data[MAIN_DATA_START:MAIN_CHECKSUM_OFFSET])


def build_synthetic_save(*, active_box: int = 2, large: bool = False) -> bytes:
    data = bytearray(SAVE_SIZE)
    data[CURRENT_BOX_NUMBER_OFFSET] = active_box
    empty = bytearray(BOX_SIZE)
    empty[1:22] = b"\xFF" * 21
    for offset in BOX_OFFSETS:
        data[offset:offset + BOX_SIZE] = empty
    data[PARTY_OFFSET:PARTY_OFFSET + PARTY_SIZE] = make_party([(0x54, "PIKA", "ASH")])
    current = make_box([(0x66, "EEVEE", "ASH")])
    data[CURRENT_BOX_OFFSET:CURRENT_BOX_OFFSET + BOX_SIZE] = current
    # The numbered selected box intentionally remains empty/stale. Gen I reads
    # the authoritative live box copy from bank 1.
    finalize_checksums(data)
    if large:
        data.extend(b"\x00" * (0x20000 - SAVE_SIZE))
    return bytes(data)


class Gen1SaveTests(unittest.TestCase):
    def test_reads_all_three_english_game_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.sav"
            path.write_bytes(build_synthetic_save())
            for game in ("red", "blue", "yellow"):
                with self.subTest(game=game):
                    save = Gen1_Save(path, game=game)
                    self.assertEqual(save.game_name, game)
                    self.assertEqual(len(save.party_pokemon), 1)
                    self.assertEqual(len(save.box_pokemon), 12)
                    self.assertEqual(len(save.box_pokemon[2]), 1)

    def test_parses_national_species_names_and_gen1_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "red.sav"
            path.write_bytes(build_synthetic_save())
            save = Gen1_Save(path, game="red")
            pika = save.party_pokemon[0]
            self.assertEqual((pika.generation, pika.species, pika.name), (1, 25, "PIKA"))
            self.assertEqual(pika.gen1_internal_species, 0x54)
            self.assertEqual((pika.original_trainer_name, pika.original_trainer), ("ASH", 0x1234))
            self.assertEqual((pika.move1, pika.move2, pika.move3, pika.move4), (33, 45, 98, 0))
            self.assertEqual((pika.hp_ev, pika.attack_ev, pika.defense_ev,
                              pika.speed_ev, pika.special_ev), (1000, 2000, 3000, 4000, 5000))
            self.assertEqual(pika.held_item, 190)  # Catch rate in Gen I.
            self.assertEqual(pika.special_attack, 24)
            self.assertIsNone(pika.special_defense)
            eevee = save.box_pokemon[2][0]
            self.assertEqual((eevee.species, eevee.gen1_internal_species, eevee.name), (133, 0x66, "EEVEE"))

    def test_uses_live_current_box_instead_of_stale_numbered_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.sav"
            path.write_bytes(build_synthetic_save(active_box=2))
            save = Gen1_Save(path, game="red")
            self.assertEqual([mon.name for mon in save.box_pokemon[2]], ["EEVEE"])
            self.assertEqual(save.box_pokemon[2][0].species, 133)

    def test_untouched_write_is_byte_for_byte_and_input_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "yellow.sav"
            original = build_synthetic_save()
            path.write_bytes(original)
            save = Gen1_Save(path, game="yellow")
            output_path = save.write_save()
            self.assertEqual(Path(output_path).read_bytes(), original)
            self.assertEqual(path.read_bytes(), original)

    def test_clearing_all_pokemon_updates_current_box_and_checksums(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "blue.sav"
            original = build_synthetic_save()
            path.write_bytes(original)
            save = Gen1_Save(path, game="blue")
            save.party_pokemon = []
            save.box_pokemon = [[] for _ in range(12)]
            output_path = save.write_save()
            output = bytearray(Path(output_path).read_bytes())
            self.assertEqual(len(output), SAVE_SIZE)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(output[PARTY_OFFSET], 0)
            self.assertEqual(output[CURRENT_BOX_OFFSET], 0)
            self.assertEqual(output[CURRENT_BOX_OFFSET + 1], 0xFF)
            self.assertEqual(output[BOX_OFFSETS[2]], 0)
            self.assertEqual(output[BOX_OFFSETS[2] + 1], 0xFF)
            self.assertEqual(output[MAIN_CHECKSUM_OFFSET], _checksum(output[MAIN_DATA_START:MAIN_CHECKSUM_OFFSET]))
            for base, check_offset in BANK_BOX_CHECKSUM_OFFSET.items():
                self.assertEqual(output[check_offset], _checksum(output[base:check_offset]))
                for index in range(6):
                    start = base + index * BOX_SIZE
                    self.assertEqual(output[check_offset + 1 + index], _checksum(output[start:start + BOX_SIZE]))
            clean = Gen1_Save(output_path, game="blue")
            self.assertEqual(clean.party_pokemon, [])
            self.assertTrue(all(not box for box in clean.box_pokemon))

    def test_accepts_oversized_yellow_dump_using_first_32k(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "yellow-large.sav"
            raw = build_synthetic_save(large=True)
            path.write_bytes(raw)
            save = Gen1_Save(path, game="yellow")
            self.assertEqual(len(save.save_bytes), SAVE_SIZE)
            self.assertEqual(len(save.party_pokemon), 1)
            self.assertEqual(Path(save.write_save()).stat().st_size, SAVE_SIZE)

    def test_rejects_corrupt_main_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.sav"
            data = bytearray(build_synthetic_save())
            data[PARTY_OFFSET + 8 + 3] ^= 0x01
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "main checksum"):
                Gen1_Save(path, game="red")

    def test_rejects_unsupported_localized_game_label(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.sav"
            path.write_bytes(build_synthetic_save())
            with self.assertRaisesRegex(ValueError, "English Red, Blue, and Yellow"):
                Gen1_Save(path, game="red-jp")


if __name__ == "__main__":
    unittest.main()
