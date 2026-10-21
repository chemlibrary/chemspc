import tempfile
import unittest
import sys
import types
from pathlib import Path

# The full application provides chempy. These small test-only definitions let
# this format test run from the source bundle when that optional package is not
# present; Gen III parsing itself only needs the Pokemon data container.
try:
    import chempy.primitives  # noqa: F401
except ModuleNotFoundError as exc:
    if exc.name != "chempy":
        raise
    chempy_module = types.ModuleType("chempy")
    chempy_module.__path__ = []
    primitives_module = types.ModuleType("chempy.primitives")
    primitives_module.get_int = lambda data: int.from_bytes(data, "big")
    primitives_module.get_bytes = lambda value, length: int(value).to_bytes(length, "big")
    sys.modules["chempy"] = chempy_module
    sys.modules["chempy.primitives"] = primitives_module

from gen3 import (
    BOX_CAPACITY,
    BOX_COUNT,
    PARTY_CAPACITY,
    BOX_RECORD_SIZE,
    BOX_RECORDS_OFFSET,
    PARTY_COUNT_OFFSET,
    PARTY_RECORDS_OFFSET,
    PARTY_RECORD_SIZE,
    SAVE_SIZE,
    SECTOR_DATA_SIZE,
    SECTOR_FOOTER_CHECKSUM_OFFSET,
    SECTOR_FOOTER_COUNTER_OFFSET,
    SECTOR_FOOTER_ID_OFFSET,
    SECTOR_FOOTER_SIGNATURE_OFFSET,
    SECTOR_SIZE,
    SECTOR_SIGNATURE,
    SECTION_CHECKSUM_SIZES,
    SECTION_CHECKSUM_SIZES_BY_PROFILE,
    PARTY_LAYOUTS,
    SECTIONS_PER_SLOT,
    SLOT_OFFSETS,
    SUBSTRUCTURE_ORDERS,
    Gen3_Save,
    decode_gen3_text,
    encode_gen3_text,
    _calculate_section_checksum,
)


def put16(buffer, offset, value):
    buffer[offset:offset + 2] = int(value).to_bytes(2, "little")


def put32(buffer, offset, value):
    buffer[offset:offset + 4] = int(value).to_bytes(4, "little")


def make_pokemon_record(party=True):
    """Make a simple valid Pikachu Gen III record for test coverage."""
    pid = 0x12345679
    otid = 0x00001234
    growth = bytearray(12)
    put16(growth, 0, 25)      # Pikachu, internal species ID 25
    put16(growth, 2, 0)       # held item
    put32(growth, 4, 1000)    # EXP
    growth[8] = 0             # PP bonuses
    growth[9] = 70            # friendship

    attacks = bytearray(12)
    put16(attacks, 0, 85)     # Thunderbolt
    put16(attacks, 2, 33)     # Tackle
    attacks[8] = 15
    attacks[9] = 35

    evs = bytearray(12)
    evs[1] = 4
    evs[4] = 8
    evs[5] = 8

    misc = bytearray(12)
    misc[1] = 10             # met location
    put16(misc, 2, 0x1234)   # origin data
    put32(misc, 4, 0x12345678)

    canonical = {"G": bytes(growth), "A": bytes(attacks), "E": bytes(evs), "M": bytes(misc)}
    order = SUBSTRUCTURE_ORDERS[pid % 24]
    shuffled = b"".join(canonical[name] for name in order)
    key = pid ^ otid
    encrypted = bytearray()
    for offset in range(0, 48, 4):
        value = int.from_bytes(shuffled[offset:offset + 4], "little") ^ key
        encrypted.extend(value.to_bytes(4, "little"))

    raw = bytearray(100 if party else 80)
    put32(raw, 0, pid)
    put32(raw, 4, otid)
    raw[8:18] = bytes([0xCA, 0xC3, 0xC5, 0xBB, 0xBD, 0xC2, 0xCF, 0xFF, 0xFF, 0xFF]) # PIKACHU
    raw[0x12] = 2              # English
    raw[0x13] = 2              # has species
    raw[0x14:0x1B] = bytes([0xBB, 0xCD, 0xC2, 0xFF, 0xFF, 0xFF, 0xFF]) # ASH
    put16(raw, 0x1C, sum(int.from_bytes((growth + attacks + evs + misc)[i:i + 2], "little") for i in range(0, 48, 2)) & 0xFFFF)
    raw[0x20:0x50] = encrypted
    if party:
        put32(raw, 0x50, 0)    # status
        raw[0x54] = 12         # level
        raw[0x55] = 0          # mail
        put16(raw, 0x56, 32)   # current HP
        put16(raw, 0x58, 40)   # max HP
        put16(raw, 0x5A, 25)
        put16(raw, 0x5C, 20)
        put16(raw, 0x5E, 30)
        put16(raw, 0x60, 15)
        put16(raw, 0x62, 18)
    return bytes(raw)


def build_synthetic_save(game="emerald", box_slot=0):
    raw = bytearray(SAVE_SIZE)
    party = make_pokemon_record(party=True)
    box_mon = make_pokemon_record(party=False)
    profile = {
        "ruby": "rs", "sapphire": "rs", "emerald": "emerald",
        "firered": "frlg", "leafgreen": "frlg",
    }[game]
    party_count_offset, party_records_offset, _party_count_size = PARTY_LAYOUTS[profile]
    storage = bytearray(9 * SECTOR_DATA_SIZE)
    storage[:4] = (0).to_bytes(4, "little")
    start_box_record = BOX_RECORDS_OFFSET + box_slot * BOX_RECORD_SIZE
    storage[start_box_record:start_box_record + BOX_RECORD_SIZE] = box_mon

    for slot_index, base in enumerate(SLOT_OFFSETS):
        counter = 12 if slot_index == 0 else 13
        rotation = slot_index * 3
        for physical_index in range(SECTIONS_PER_SLOT):
            section_id = (physical_index + rotation) % SECTIONS_PER_SLOT
            sector_offset = base + physical_index * SECTOR_SIZE
            sector_data = bytearray(SECTOR_DATA_SIZE)

            if section_id == 0:
                # Seed unused profile-tail bytes so the auto-detector can tell
                # apart otherwise checksum-equivalent synthetic layouts.
                sector_data[0xF28:0xF2C] = b"GEN3"
            elif section_id == 1:
                count_size = PARTY_LAYOUTS[profile][2]
                if count_size == 4:
                    put32(sector_data, party_count_offset, 1)
                else:
                    sector_data[party_count_offset] = 1
                    sector_data[party_count_offset + 1:party_records_offset] = b"\xA5\x5A\xC3"
                sector_data[party_records_offset:party_records_offset + PARTY_RECORD_SIZE] = party
            elif section_id == 4:
                sector_data[0xD00:0xD04] = b"LAYT"
            elif 5 <= section_id <= 13:
                storage_chunk_index = section_id - 5
                start = storage_chunk_index * SECTOR_DATA_SIZE
                sector_data[:] = storage[start:start + SECTOR_DATA_SIZE]

            raw[sector_offset:sector_offset + SECTOR_DATA_SIZE] = sector_data
            put16(raw, sector_offset + SECTOR_FOOTER_ID_OFFSET, section_id)
            checksum = _calculate_section_checksum(sector_data, section_id, profile)
            put16(raw, sector_offset + SECTOR_FOOTER_CHECKSUM_OFFSET, checksum)
            put32(raw, sector_offset + SECTOR_FOOTER_SIGNATURE_OFFSET, SECTOR_SIGNATURE)
            put32(raw, sector_offset + SECTOR_FOOTER_COUNTER_OFFSET, counter)
    return bytes(raw)


class Gen3SaveTests(unittest.TestCase):
    def _make_save_file(self, directory):
        path = Path(directory) / "synthetic-emerald.sav"
        path.write_bytes(build_synthetic_save(game="emerald"))
        return path

    def test_slot_selection_uses_save_counter_and_footer_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-ruby.sav"
            path.write_bytes(build_synthetic_save(game="ruby"))
            save = Gen3_Save(path, game="ruby")
            self.assertEqual(save.active_slot, 1)
            self.assertEqual(save.active_save_index, 13)
            self.assertEqual(set(save.section_offsets), set(range(14)))

    def test_extracts_party_and_pc_boxes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._make_save_file(directory)
            save = Gen3_Save(path, game="emerald")
            self.assertEqual(len(save.party_pokemon), 1)
            self.assertEqual(save.party_pokemon[0].generation, 3)
            self.assertEqual(save.party_pokemon[0].species, 25)
            self.assertEqual(save.party_pokemon[0].name, "PIKACHU")
            self.assertEqual(save.party_pokemon[0].original_trainer_name, "ASH")
            self.assertEqual(save.party_pokemon[0].exp, 1000)
            self.assertEqual(save.party_pokemon[0].move1, 85)
            self.assertEqual(save.party_pokemon[0].level, 12)
            self.assertEqual(len(save.box_pokemon), BOX_COUNT)
            self.assertEqual(len(save.box_pokemon[0]), 1)
            self.assertEqual(save.box_pokemon[0][0].species, 25)
            self.assertIsNone(save.box_pokemon[0][0].level)

    def test_write_round_trip_preserves_encrypted_record_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._make_save_file(directory)
            save = Gen3_Save(path, game="emerald")
            original_party = save.party_pokemon[0].gen3_party_record
            original_box = save.box_pokemon[0][0].gen3_box_record
            output = Path(save.write_save())
            reread = Gen3_Save(output, game="emerald")
            self.assertEqual(reread.party_pokemon[0].gen3_party_record, original_party)
            self.assertEqual(reread.box_pokemon[0][0].gen3_box_record, original_box)

    def test_modified_pokemon_fields_are_reencrypted_and_checksums_updated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._make_save_file(directory)
            save = Gen3_Save(path, game="emerald")
            save.party_pokemon[0].name = "RAICHU"
            save.party_pokemon[0].move1 = 33
            save.party_pokemon[0].current_hp = 29
            save.box_pokemon[0][0].name = "SPARK"
            output = Path(save.write_save())
            reread = Gen3_Save(output, game="emerald")
            party_mon = reread.party_pokemon[0]
            box_mon = reread.box_pokemon[0][0]
            self.assertEqual(party_mon.name, "RAICHU")
            self.assertEqual(party_mon.move1, 33)
            self.assertEqual(party_mon.current_hp, 29)
            self.assertTrue(party_mon.gen3_checksum_valid)
            self.assertEqual(box_mon.name, "SPARK")
            self.assertTrue(box_mon.gen3_checksum_valid)

    def test_clear_pokemon_and_rechecksum_active_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._make_save_file(directory)
            save = Gen3_Save(path, game="emerald")
            save.party_pokemon = []
            save.box_pokemon = [[] for _ in range(BOX_COUNT)]
            output = Path(save.write_save())
            self.assertEqual(output.stat().st_size, SAVE_SIZE)
            reread = Gen3_Save(output, game="emerald")
            self.assertEqual(reread.party_pokemon, [])
            self.assertTrue(all(not box for box in reread.box_pokemon))

    def test_party_and_box_record_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._make_save_file(directory)
            save = Gen3_Save(path, game="emerald")
            self.assertEqual(len(save.export_gen3_party_list()), 4 + PARTY_CAPACITY * PARTY_RECORD_SIZE)
            self.assertEqual(len(save.export_gen3_boxes()), 9 * SECTOR_DATA_SIZE)

    def test_all_game_profiles_use_their_correct_party_offsets_and_checksums(self):
        for game, expected_profile in (
            ("ruby", "rs"), ("sapphire", "rs"), ("emerald", "emerald"),
            ("firered", "frlg"), ("leafgreen", "frlg"),
        ):
            with self.subTest(game=game), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / f"synthetic-{game}.sav"
                path.write_bytes(build_synthetic_save(game=game))
                save = Gen3_Save(path, game=game)
                self.assertEqual(save.layout_profile, expected_profile)
                self.assertEqual(len(save.party_pokemon), 1)
                self.assertEqual(save.party_pokemon[0].name, "PIKACHU")
                self.assertEqual(save.party_count_offset, PARTY_LAYOUTS[expected_profile][0])
                self.assertEqual(save.party_count_size, PARTY_LAYOUTS[expected_profile][2])
                if expected_profile == "frlg":
                    self.assertEqual(bytes(save.section_data[1][0x35:0x38]), b"\xA5\x5A\xC3")
                auto_save = Gen3_Save(path, game="auto")
                self.assertEqual(auto_save.layout_profile, expected_profile)
                out = Path(save.write_save())
                reread = Gen3_Save(out, game=game)
                self.assertEqual(len(reread.party_pokemon), 1)
                self.assertEqual(reread.party_pokemon[0].name, "PIKACHU")
                if expected_profile == "frlg":
                    self.assertEqual(bytes(reread.section_data[1][0x35:0x38]), b"\xA5\x5A\xC3")

    def test_auto_detects_unambiguous_synthetic_emerald_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-emerald.sav"
            path.write_bytes(build_synthetic_save(game="emerald"))
            save = Gen3_Save(path, game="auto")
            self.assertEqual(save.layout_profile, "emerald")
            self.assertEqual(save.party_count_offset, 0x234)

    def test_box_round_trip_preserves_original_slot_gaps(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-emerald.sav"
            original_slot = 7
            path.write_bytes(build_synthetic_save(game="emerald", box_slot=original_slot))
            save = Gen3_Save(path, game="emerald")
            self.assertEqual(save.box_pokemon[0][0].gen3_box_slot, original_slot)
            out = Path(save.write_save())
            reread = Gen3_Save(out, game="emerald")
            self.assertEqual(reread.box_pokemon[0][0].gen3_box_slot, original_slot)

    def test_full_width_nickname_and_trainer_names_are_supported(self):
        nickname = "ABCDEFGHIJ"
        trainer = "ASHNAME"
        self.assertEqual(decode_gen3_text(encode_gen3_text(nickname, 10)), nickname)
        self.assertEqual(decode_gen3_text(encode_gen3_text(trainer, 7)), trainer)

    def test_rejects_wrong_file_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "short.sav"
            path.write_bytes(b"\0" * 1024)
            with self.assertRaises(ValueError):
                Gen3_Save(path)


if __name__ == "__main__":
    unittest.main()
