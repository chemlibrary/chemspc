"""Gen IV offset/level regressions; optional real-save checks always use copies.

CHEMSPC_PLATINUM_FIXTURE=/path/to/save.sav python -m unittest discover \
    -s tests -p test_gen4_regressions.py -v
"""
from hashlib import sha256
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gen4
from gen4_growth import EXPERIENCE_TABLES, SPECIES_GROWTH_RATES, level_from_experience


def encrypted_record(species=66, exp=236, *, party=False):
    """Independent ABCD-order record with PID 0 and known EXP (Machop Lv. 7)."""
    payload = bytearray(128)
    payload[0:2] = species.to_bytes(2, 'little')
    payload[8:12] = exp.to_bytes(4, 'little')
    checksum = sum(int.from_bytes(payload[i:i + 2], 'little') for i in range(0, 128, 2)) & 0xffff

    def encrypt(data, seed):
        output = bytearray()
        for i in range(0, len(data), 2):
            seed = (seed * 0x41C64E6D + 0x6073) & 0xffffffff
            output.extend((int.from_bytes(data[i:i + 2], 'little') ^ (seed >> 16)).to_bytes(2, 'little'))
        return output

    record = bytearray(6) + checksum.to_bytes(2, 'little') + encrypt(payload, checksum)
    if party:
        stats = bytearray(100)
        stats[4] = 7
        stats[6:10] = b'\x1e\x00\x1e\x00'
        record += encrypt(stats, 0)
    return bytes(record)


def synthetic_save(game):
    """Specify offsets independently of the parser so incorrect profiles fail."""
    party_start = 0xa0 if game == 'platinum' else 0x98
    profile = gen4.PROFILES[game]
    data = bytearray(gen4.SAVE_SIZE)
    for base in (0, gen4.PARTITION_SIZE):
        data[base + 0x90:base + party_start - 4] = b'\x35' * (party_start - 4 - 0x90)
        data[base + party_start - 4] = 1
        data[base + party_start:base + party_start + 236] = encrypted_record(party=True)
        storage = base + profile['storage_start']
        box_start = storage + (0 if profile['storage_kind'] == 'hgss' else 4)
        data[box_start:box_start + 136] = encrypted_record()
        for start, size in ((base, profile['general_size']), (storage, profile['storage_size'])):
            gen4._put_u32(data, start + size - 20, 7)
            gen4._put_u32(data, start + size - 16, 10)
            gen4._put_u32(data, start + size - 12, size)
            gen4._put_u32(data, start + size - 8, gen4.BLOCK_MAGICS[0])
            gen4._update_block_checksum(data, start, size, profile['footer_size'])
    return data


class GrowthTests(unittest.TestCase):
    def test_reference_thresholds_and_piecewise_boundaries(self):
        # Reference values from PKHeX Experience.cs, growth IDs 0 through 5.
        self.assertEqual([table[99] for table in EXPERIENCE_TABLES],
                         [1000000, 600000, 1640000, 1059860, 800000, 1250000])
        for growth, level, expected in [(1, 50, 125000), (1, 51, 131324),
                (1, 68, 257834), (1, 69, 267406), (1, 98, 583539),
                (1, 99, 591882), (2, 15, 1957), (2, 16, 2457),
                (2, 36, 46656), (2, 37, 50653), (3, 2, 9)]:
            self.assertEqual(EXPERIENCE_TABLES[growth][level - 1], expected)

    def test_every_species_and_level_boundary(self):
        self.assertEqual(len(SPECIES_GROWTH_RATES), 494)
        self.assertEqual(set(SPECIES_GROWTH_RATES), set('012345'))
        for species in range(1, 494):
            table = EXPERIENCE_TABLES[int(SPECIES_GROWTH_RATES[species])]
            self.assertEqual(level_from_experience(species, 0), 1)
            self.assertEqual(level_from_experience(species, 0xffffffff), 100)
            for level in range(2, 101):
                exp = table[level - 1]
                self.assertEqual(level_from_experience(species, exp), level)
                self.assertEqual(level_from_experience(species, exp - 1), level - 1)

    def test_known_species_and_experience(self):
        for species, exp, level in [(66, 236, 7), (41, 27, 3), (74, 179, 6),
                                    (113, 7408, 21), (313, 120001, 49)]:
            self.assertEqual(level_from_experience(species, exp), level)
        self.assertIsNone(level_from_experience(0, 100))
        self.assertIsNone(level_from_experience(494, 100))
        with self.assertRaises(ValueError):
            level_from_experience(25, -1)


class PartyLayoutTests(unittest.TestCase):
    def test_read_write_and_removal_for_all_gen4_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            for game in gen4.PROFILES:
                with self.subTest(game=game):
                    path = Path(folder) / (game + '.sav')
                    original = bytes(synthetic_save(game))
                    path.write_bytes(original)
                    save = gen4.Gen4_Save(path, game=game)
                    self.assertEqual(len(save.party_pokemon), 1)
                    self.assertEqual(save.party_pokemon[0].level, 7)
                    self.assertEqual(save.box_pokemon[0][0].level, 7)
                    output = save.write_save()
                    reloaded = gen4.Gen4_Save(output, game=game)
                    self.assertEqual(reloaded.party_pokemon[0].gen4_party_record,
                                     save.party_pokemon[0].gen4_party_record)
                    save.party_pokemon.clear()
                    changed = Path(save.write_save()).read_bytes()
                    start = 0xa0 if game == 'platinum' else 0x98
                    for base in save.valid_general_offsets:
                        self.assertEqual(changed[base + start - 4], 0)
                        self.assertEqual(changed[base + 0x90:base + start - 4],
                                         original[base + 0x90:base + start - 4])
                        self.assertEqual(changed[base + start:base + start + 6 * 236], bytes(6 * 236))
                    self.assertEqual(gen4.Gen4_Save(save.write_save(), game=game).party_pokemon, [])
                    self.assertEqual(path.read_bytes(), original)


@unittest.skipUnless(os.environ.get('CHEMSPC_PLATINUM_FIXTURE'), 'Set CHEMSPC_PLATINUM_FIXTURE for real-save checks')
class PlatinumSaveTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('flask'), 'Flask required for HTTP workflow checks')
    def test_upload_display_import_download_and_export(self):
        import db
        from main import app

        original_path = Path(os.environ['CHEMSPC_PLATINUM_FIXTURE'])
        original = original_path.read_bytes()
        digest = sha256(original).digest()
        try:
            with tempfile.TemporaryDirectory() as folder:
                config = {'TESTING': True, 'UPLOAD_FOLDER': str(Path(folder) / 'staging'),
                          'EXPORT_FOLDER': str(Path(folder) / 'exports')}
                with patch.dict(app.config, config), patch.object(db, 'DATABASE_NAME', str(Path(folder) / 'collection.db')):
                    with app.test_client() as client:
                        self.assertEqual(client.get('/').status_code, 200)
                        with client.session_transaction() as session:
                            csrf = session['csrf_token']

                        def upload(data):
                            return client.post('/open-save', data={'csrf_token': csrf, 'game': 'platinum',
                                'save_file': (io.BytesIO(data), 'platinum.sav')}, follow_redirects=True)

                        page = upload(original)
                        self.assertEqual(page.status_code, 200)
                        self.assertEqual(page.data.count(b'name="import_slot"'), 123)
                        self.assertIn(b'Lv. 52', page.data)
                        self.assertIn(b'Lv. 7', page.data)
                        self.assertNotIn(b'Lv. None', page.data)
                        result = client.post('/finalize', data={'csrf_token': csrf,
                            'import_slot': ['party:0', 'box:0:0']}, follow_redirects=True)
                        self.assertIn(b'TRANSFER FINALIZED', result.data)
                        with client.session_transaction() as session:
                            token = session['last_export_token']
                        downloaded = client.get('/download/' + token)
                        self.assertEqual(downloaded.status_code, 200)
                        copy = Path(folder) / 'download.sav'
                        copy.write_bytes(downloaded.data)
                        downloaded.close()
                        parsed = gen4.Gen4_Save(copy, game='platinum')
                        self.assertEqual(len(parsed.party_pokemon), 5)
                        self.assertEqual(sum(map(len, parsed.box_pokemon)), 116)
                        rows = db.list_pokemon(active=True)
                        self.assertEqual([(p['name'], p['level']) for p in rows], [('GOLBAT', 52), ('MACHOP', 7)])
                        upload(downloaded.data)
                        exported = client.post('/finalize', data={'csrf_token': csrf,
                            'export_uid': [str(row['uid']) for row in rows]}, follow_redirects=True)
                        self.assertIn(b'TRANSFER FINALIZED', exported.data)
                        with client.session_transaction() as session:
                            token = session['last_export_token']
                        with client.get('/download/' + token) as response:
                            self.assertEqual(response.status_code, 200)
                            copy.write_bytes(response.data)
                        restored = gen4.Gen4_Save(copy, game='platinum')
                        self.assertEqual(len(restored.party_pokemon), 5)
                        self.assertEqual(sum(map(len, restored.box_pokemon)), 118)
                        reference = gen4.Gen4_Save(original_path, game='platinum')
                        def records(save):
                            return sorted(p.gen4_box_record for p in save.party_pokemon +
                                          [p for box in save.box_pokemon for p in box])
                        self.assertEqual(records(restored), records(reference))
                        self.assertEqual(db.list_pokemon(active=True), [])
                        self.assertEqual(len(db.list_pokemon(active=False)), 2)
        finally:
            self.assertEqual(sha256(original_path.read_bytes()).digest(), digest, 'Original save changed')

    def test_attached_save_roundtrip_and_selective_removal(self):
        original_path = Path(os.environ['CHEMSPC_PLATINUM_FIXTURE'])
        original = original_path.read_bytes()
        digest = sha256(original).digest()
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'platinum.sav'
                path.write_bytes(original)
                save = gen4.Gen4_Save(path, game='platinum')
                self.assertEqual([(p.name, p.level) for p in save.party_pokemon], [
                    ('GOLBAT', 52), ('LEAFEON', 66), ('PELIPPER', 62),
                    ('GIRATINA', 77), ('GRAVELER', 45), ('EMPOLEON', 68)])
                boxes = [p for box in save.box_pokemon for p in box]
                self.assertEqual(len(boxes), 117)
                self.assertTrue(all(1 <= p.level <= 100 for p in boxes))
                self.assertEqual([(p.name, p.level) for p in boxes[:5]],
                                 [('MACHOP', 7), ('ZUBAT', 3), ('KRICKETOT', 3), ('GOLBAT', 22), ('GEODUDE', 6)])
                output = save.write_save()
                reloaded = gen4.Gen4_Save(output, game='platinum')
                self.assertEqual([p.gen4_party_record for p in reloaded.party_pokemon],
                                 [p.gen4_party_record for p in save.party_pokemon])
                self.assertEqual([p.gen4_box_record for box in reloaded.box_pokemon for p in box],
                                 [p.gen4_box_record for p in boxes])
                # Remove one party member and one boxed member, preserving all others.
                save.party_pokemon.pop(0)
                save.box_pokemon[0].pop(0)
                output = save.write_save()
                changed = gen4.Gen4_Save(output, game='platinum')
                self.assertEqual([p.gen4_party_record for p in changed.party_pokemon],
                                 [p.gen4_party_record for p in save.party_pokemon])
                self.assertEqual([p.gen4_box_record for box in changed.box_pokemon for p in box],
                                 [p.gen4_box_record for box in save.box_pokemon for p in box])
                self.assertEqual(sum(map(len, changed.box_pokemon)), 116)
                data = Path(output).read_bytes()
                for base in save.valid_general_offsets:
                    self.assertEqual(data[base + 0x90:base + 0x9c], original[base + 0x90:base + 0x9c])
                    self.assertEqual(data[base + 0x9c], 5)
                    size = save.profile['general_size']
                    self.assertIsNotNone(gen4._footer_info(data[base:base + size], size, 0x14))
                self.assertEqual(path.read_bytes(), original)
        finally:
            self.assertEqual(sha256(original_path.read_bytes()).digest(), digest, 'Original save changed')


if __name__ == '__main__':
    unittest.main()
