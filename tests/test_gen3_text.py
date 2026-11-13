"""Gender glyph regressions; optional FireRed fixture is tested via a copy."""
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import unittest

from gen3 import Gen3_Save, decode_gen3_text, encode_gen3_text, _decode_gen3_record, _serialize_gen3_record


class Gen3GenderTextTests(unittest.TestCase):
    def test_decode_gender_symbols_and_terminator(self):
        # FireRed charmap: https://github.com/pret/pokefirered/blob/master/charmap.txt
        prefix = bytes.fromhex('c8 c3 be c9 cc bb c8')  # NIDORAN
        self.assertEqual(decode_gen3_text(prefix + b'\xb5\xff\xb6'), 'NIDORAN♂')
        self.assertEqual(decode_gen3_text(prefix + b'\xb6\xff\xb5'), 'NIDORAN♀')
        self.assertEqual(decode_gen3_text(b'\xb5\xb6\xff'), '♂♀')

    def test_encode_gender_symbols_with_padding_and_full_width(self):
        prefix = bytes.fromhex('c8 c3 be c9 cc bb c8')
        for symbol, value in [('♂', 0xb5), ('♀', 0xb6)]:
            self.assertEqual(encode_gen3_text('NIDORAN' + symbol, 10), prefix + bytes([value, 255, 255]))
            self.assertEqual(encode_gen3_text('NIDORAN' + symbol, 8), prefix + bytes([value]))
            self.assertEqual(decode_gen3_text(encode_gen3_text(symbol, 7)), symbol)

    @unittest.skipUnless(os.environ.get('CHEMSPC_FIRERED_FIXTURE'), 'Set CHEMSPC_FIRERED_FIXTURE for real-save checks')
    def test_attached_save_roundtrip_and_name_serialization(self):
        original_path = Path(os.environ['CHEMSPC_FIRERED_FIXTURE'])
        original = original_path.read_bytes()
        digest = sha256(original).digest()
        try:
            with tempfile.TemporaryDirectory() as folder:
                copy = Path(folder) / 'firered.srm'
                copy.write_bytes(original)
                save = Gen3_Save(copy, game='firered')
                pokemon = save.party_pokemon + [p for box in save.box_pokemon for p in box]
                nidorans = [p for p in pokemon if p.species in (29, 32)]
                self.assertEqual({p.name for p in nidorans}, {'NIDORAN♀', 'NIDORAN♂'})
                self.assertEqual(len(save.party_pokemon), 6)
                self.assertEqual(sum(map(len, save.box_pokemon)), 82)
                original_records = [p.gen3_box_record for p in pokemon]
                output = save.write_save()
                reloaded = Gen3_Save(output, game='firered')
                retained = reloaded.party_pokemon + [p for box in reloaded.box_pokemon for p in box]
                self.assertEqual([p.gen3_box_record for p in retained], original_records)
                self.assertEqual([p.name for p in retained], [p.name for p in pokemon])
                for mon in nidorans:
                    original_record = mon.gen3_box_record
                    self.assertEqual(_serialize_gen3_record(mon, party_record=False), original_record)
                    # Exercise the encoder too, rather than only retained bytes.
                    mon.name = 'TEST' + ('♀' if mon.species == 29 else '♂')
                    rewritten = _serialize_gen3_record(mon, party_record=False)
                    decoded = _decode_gen3_record(rewritten, party_record=False)
                    self.assertEqual(decoded.name, mon.name)
                    self.assertTrue(decoded.gen3_checksum_valid)
                self.assertEqual(copy.read_bytes(), original)
        finally:
            self.assertEqual(sha256(original_path.read_bytes()).digest(), digest, 'Original save changed')


if __name__ == '__main__':
    unittest.main()
