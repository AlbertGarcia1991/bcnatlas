import hashlib
import json
import unittest
from pathlib import Path
from scripts.import_data import normalize, parse

class ImportTests(unittest.TestCase):
    def test_coordinate_schemas(self):
        self.assertEqual(normalize({'Latitud_WGS84': '41.39123', 'Longitud_WGS84': '2.17123', 'Codi_districte': '2'}), [2.17123, 41.39123, 2])
        self.assertEqual(normalize({'latitud': '41,39123', 'longitud': '2,17123', 'codi_districte': '02'}), [2.17123, 41.39123, 2])
    def test_rejects_bad_coordinates(self):
        for value in ['NaN', '', '-1', '90', 'garbage']:
            self.assertIsNone(normalize({'latitud': value, 'longitud': '2.17'}))
    def test_unknown_district_remains_in_city(self):
        self.assertEqual(normalize({'latitud': '41.39', 'longitud': '2.17', 'codi_districte': '-1'})[2], 0)
    def test_detects_schema_breakage(self):
        with self.assertRaises(ValueError):
            parse(b'latitude,longitude\n41.39,2.17\n')
    @unittest.skipUnless((Path(__file__).resolve().parents[1]/"public/data/manifest.json").exists(), "Optional local dataset snapshot; excluded from Git")
    def test_bundled_snapshot_integrity(self):
        root = Path(__file__).resolve().parents[1] / 'public'
        manifest = json.loads((root / 'data/manifest.json').read_text())
        self.assertEqual(len(manifest['datasets']), 3)
        for dataset in manifest['datasets'].values():
            self.assertIn('Attribution', dataset['license'])
            for year in manifest['years']:
                meta = dataset['years'][str(year)]
                raw = (root / meta['file'].lstrip('/')).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), meta['sha256'])
                points = json.loads(raw)
                self.assertEqual(len(points), meta['count'])
                self.assertEqual(meta['count'] + meta['excluded'], meta['sourceRows'])
                self.assertTrue(all(len(p) == 3 and 2.04 <= p[0] <= 2.24 and 41.30 <= p[1] <= 41.49 and 0 <= p[2] <= 10 for p in points))
