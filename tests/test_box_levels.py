"""Boxed-level coverage across all game versions and older stored records."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import db
import gen1
import gen3
import gen4
import gen5
import gen6
import gen7
from experience import level_from_experience, GEN3_GROWTH_RATES, NATIONAL_GROWTH_RATES, SPECIES_LIMITS
from gen4_growth import EXPERIENCE_TABLES, SPECIES_GROWTH_RATES
from pokemon import Pokemon
from save_formats import GAME_SPECS


def crypt(data, seed):
    result = bytearray()
    for i in range(0, len(data), 2):
        seed = (seed * 0x41c64e6d + 0x6073) & 0xffffffff
        result.extend((int.from_bytes(data[i:i + 2], 'little') ^ (seed >> 16)).to_bytes(2, 'little'))
    return result


def boxed_record(generation, species=66, exp=236):
    if generation == 1:
        data = bytearray(33)
        data[0] = next(key for key, value in gen1.INTERNAL_TO_DEX.items() if value == species)
        data[3] = 7
        data[14:17] = exp.to_bytes(3, 'big')
        return bytes(data)
    if generation == 2:
        data = bytearray(32)
        data[0] = species
        data[8:11] = exp.to_bytes(3, 'big')
        data[31] = 7
        return bytes(data)
    if generation == 3:
        data = bytearray(80)
        data[0x13] = 2
        data[0x20:0x22] = species.to_bytes(2, 'little')
        data[0x24:0x28] = exp.to_bytes(4, 'little')
        data[0x1c:0x1e] = (sum(int.from_bytes(data[i:i+2], 'little') for i in range(32, 80, 2)) & 0xffff).to_bytes(2, 'little')
        return bytes(data)  # PID and OT ID are zero; XOR key is zero.
    data = bytearray(136 if generation in (4, 5) else 232)
    data[8:10] = species.to_bytes(2, 'little')
    data[16:20] = exp.to_bytes(4, 'little')
    checksum = sum(int.from_bytes(data[i:i+2], 'little') for i in range(8, len(data), 2)) & 0xffff
    data[6:8] = checksum.to_bytes(2, 'little')
    data[8:] = crypt(data[8:], checksum if generation in (4, 5) else 0)
    return bytes(data)  # PID/EC 0 selects ABCD block ordering.


class BoxLevelTests(unittest.TestCase):
    def test_boxed_level_for_every_supported_game(self):
        for game, spec in GAME_SPECS.items():
            with self.subTest(game=game):
                record = boxed_record(spec.generation)
                if spec.generation == 1:
                    handler = object.__new__(gen1.Gen1_Save)  # Exercise the record parser independently of SRAM.
                    mon = handler._parse_pokemon(record, b'\x50'*11, b'\x50'*11, party=False)
                elif spec.generation == 2:
                    mon = Pokemon()
                    mon.init_gen2(record)
                elif spec.generation == 3:
                    mon = gen3._decode_gen3_record(record, party_record=False)
                else:
                    module = {4: gen4, 5: gen5, 6: gen6, 7: gen7}[spec.generation]
                    mon = module._parse_pokemon(record, party=False, game_name=game)
                self.assertEqual(mon.level, 7)
                if spec.generation >= 3:
                    retained = getattr(mon, f'gen{spec.generation}_box_record', None)
                    if retained is not None:
                        self.assertEqual(retained, record)

    def test_growth_boundaries_for_all_species_in_all_generations(self):
        self.assertEqual(NATIONAL_GROWTH_RATES[:494], SPECIES_GROWTH_RATES)
        for generation, limit in SPECIES_LIMITS.items():
            for species in range(1, limit + 1):
                if generation == 3 and 252 <= species <= 276:
                    self.assertIsNone(level_from_experience(generation, species, 1000))
                    continue
                rates = GEN3_GROWTH_RATES if generation == 3 else NATIONAL_GROWTH_RATES
                table = EXPERIENCE_TABLES[int(rates[species])]
                self.assertEqual(level_from_experience(generation, species, 0), 1)
                self.assertEqual(level_from_experience(generation, species, 0xffffffff), 100)
                for level in (2, 15, 16, 36, 37, 50, 51, 68, 69, 98, 99, 100):
                    self.assertEqual(level_from_experience(generation, species, table[level - 1]), level)
                    self.assertEqual(level_from_experience(generation, species, table[level - 1] - 1), level - 1)
            self.assertIsNone(level_from_experience(generation, limit + 1, 1000))

    def test_gen3_uses_native_hoenn_species_ids(self):
        # Native 306 = Shroomish (fluctuating), National 306 = Aggron (slow).
        self.assertEqual(level_from_experience(3, 306, 1957), 15)
        self.assertNotEqual(level_from_experience(4, 306, 1957), 15)
        mon = gen3._decode_gen3_record(boxed_record(3, 306, 1957), party_record=False)
        self.assertEqual(mon.level, 15)

    def test_gen7_species_beyond_gen6_limit(self):
        # Zeraora (807), Slow growth. Must be recalculated after the shared PK6 parser.
        raw = boxed_record(7, 807, 1250000)
        mon = gen7._parse_pokemon(raw, game_name='ultrasun', party=False)
        self.assertEqual(mon.level, 100)
        self.assertEqual(mon.gen7_record, raw)
        self.assertFalse(any(key.startswith('gen6_') for key in vars(mon)))
        restored = db.restore_record_payload(Pokemon(), db.encode_record_payload(mon))
        self.assertEqual(restored.gen7_record, raw)
        self.assertEqual(restored.generation, 7)

    def test_older_database_levels_are_derived_without_changing_rows(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(db, 'DATABASE_NAME', str(Path(folder) / 'test.db')):
            db.init_tables()
            for generation in range(1, 8):
                db.add_pokemon(Pokemon(generation=generation, species=66, exp=236, level=None))
            rows = db.list_pokemon()
            self.assertEqual([row['level'] for row in rows], [7] * 7)
            # Payloads from old imports also contain level=None; hydrate after restoring them.
            self.assertEqual([db.row_to_pokemon(row).level for row in rows], [7] * 7)
            with db.connect() as conn:
                self.assertEqual(conn.execute('select level from pokemon').fetchall()[0][0], None)
            mon = Pokemon(generation=3, species=66, exp=236, level=42)
            db.add_pokemon(mon)
            self.assertEqual(db.row_to_pokemon(db.list_pokemon()[-1]).level, 42)


if __name__ == '__main__':
    unittest.main()
