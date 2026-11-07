import json
import unittest
from unittest.mock import patch
from scripts.curate_catalog import curate
from scripts.prune_nonspatial import plan
from server import storage

class CurationTests(unittest.TestCase):
    def dataset(self, identity, geographic=False):
        return {'id':identity, 'title':identity, 'description':'', 'tags':[], 'geographic':geographic, 'resources':[{'id':identity+'-resource'}]}

    def test_excludes_reviewed_nonspatial_but_retains_unknown_sources(self):
        source = {'datasets':[self.dataset('alcaldes-alcaldesses-bcn'),self.dataset('unknown'),self.dataset('renda-disponible-llars-bcn')]}
        result = curate(source)
        self.assertEqual([d['id'] for d in result['datasets']], ['unknown','renda-disponible-llars-bcn'])
        self.assertEqual(result['datasets'][0]['mapStatus'], 'needs-inspection')
        self.assertIn('section', result['datasets'][1]['mapMethods'])

    def test_deletion_plan_scopes_raw_prefix_and_processed_resource_ids(self):
        source = {'datasets':[self.dataset('remove'),self.dataset('keep')]}
        calls=[]
        def listing(bucket, prefix):
            calls.append((bucket,prefix))
            if prefix=='processed/':
                return [{'Key':'processed/v2/remove-resource/a.json'},{'Key':'processed/v3/keep-resource/b.json'}]
            return [{'Key':prefix+'remove-resource/source'}]
        with patch('scripts.prune_nonspatial.objects', side_effect=listing):
            result = plan(source, {'remove':{}})
        self.assertEqual(result['processedKeys'], ['processed/v2/remove-resource/a.json'])
        self.assertEqual(result['rawKeys'], [f'{storage.raw_prefix()}/raw/remove/remove-resource/source'])
        self.assertEqual(result['datasets'], ['remove'])
        self.assertFalse(any('/keep/' in prefix for _,prefix in calls))

    def test_no_geographic_dataset_is_in_reviewed_exclusions(self):
        path = storage.ROOT / 'public/data/catalog.json'
        if not path.exists(): self.skipTest('Optional local data snapshot')
        catalog=json.loads(path.read_text())
        excluded=json.loads((storage.ROOT/'config/catalog-exclusions.json').read_text())
        self.assertFalse(any(d['geographic'] and d['id'] in excluded for d in catalog['datasets']))
