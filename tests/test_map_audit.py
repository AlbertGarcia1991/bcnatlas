import contextlib
import io
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import publish_map_audit

class MapAuditPublicationTests(unittest.TestCase):
    def test_filter_combinations_respect_request_limits(self):
        from scripts.audit_map_filters import combinations
        mode,total,selections=combinations([{'field':'a','values':['x','y']},{'field':'b','values':['z']}])
        self.assertEqual((mode,total,len(selections)),('exhaustive',6,6))
        mode,total,selections=combinations([{'field':str(i),'values':['x','y']} for i in range(20)]+[{'field':'too_long','values':['x'*501]}])
        self.assertEqual(mode,'representative')
        self.assertGreater(total,len(selections))
        self.assertTrue(all(len(s)<=12 and 'too_long' not in s for s in selections))

    def test_keeps_working_editions_and_documents_failing_attributes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); audit=root/'audit'
            for p in (root/'config',root/'docs',root/'src',audit/'resources'/'good',audit/'resources'/'bad'):p.mkdir(parents=True)
            (root/'src/mapOverlay.ts').write_text('renderer')
            catalog={'datasets':[{'id':'dataset','title':'Example','url':'https://example.test/dataset','mapMethods':['coordinates'],'resources':[{'id':'good','name':'2024.csv','url':'https://example.test/good','format':'CSV','previewSupported':True},{'id':'bad','name':'2023.csv','url':'https://example.test/bad','format':'CSV','previewSupported':True}]}]}
            (audit/'catalog.json').write_text(json.dumps(catalog))
            payload=str(audit/'resources/good/edition.json.gz')
            case={'status':'parsed','seconds':1,'member':None,'year':'2024','payload':payload,'metrics':[{'name':'income'},{'name':'bad_metric'}],'filters':[{'field':'category','values':['A','B']}]}
            (audit/'resources/good/result.json').write_text(json.dumps({'complete':True,'sha256':'abc','cases':[case]}))
            filtered_payload=str(audit/'resources/good/filtered.json.gz')
            (audit/'resources/good/filters.json').write_text(json.dumps({'complete':True,'cases':[{'member':None,'year':'2024','status':'passed','mode':'representative','totalCombinations':'1000','checks':[{'filters':{},'status':'baseline'},{'filters':{'category':'A'},'status':'empty'},{'filters':{'category':'B'},'status':'parsed','payload':filtered_payload}]}]}))
            (audit/'resources/good/filtered.render.json').write_text(json.dumps({'rendererHash':hashlib.sha256(b'renderer').hexdigest(),'status':'passed','checks':[{'metric':'','render':'geometry','status':'passed'},{'metric':'conditional','render':'geometry','status':'passed'},{'metric':'bad_metric','render':'geometry','status':'passed'}]}))
            (audit/'resources/good/edition.render.json').write_text(json.dumps({'rendererHash':hashlib.sha256(b'renderer').hexdigest(),'status':'failed','checks':[{'metric':'','render':'geometry','status':'passed'},{'metric':'income','render':'geometry','status':'passed'},{'metric':'bad_metric','render':'geometry','status':'failed','error':'Invalid colour range'}]}))
            (audit/'resources/bad/result.json').write_text(json.dumps({'complete':True,'cases':[{'status':'failed','member':None,'year':None,'error':'No recognized map locations'}]}))
            with patch.object(publish_map_audit,'ROOT',audit),patch.object(publish_map_audit.storage,'ROOT',root),contextlib.redirect_stdout(io.StringIO()):publish_map_audit.main()
            manifest=json.loads((root/'config/map-render-audit.json').read_text())
            self.assertEqual(list(manifest['resources']),['good'])
            self.assertEqual(manifest['resources']['good']['cases'][0]['metrics'],['income','conditional'])
            self.assertEqual(manifest['resources']['good']['cases'][0]['filterAudit']['mode'],'representative')
            self.assertIn('INCOMPLETE: representative',(root/'docs/filter-audit-coverage.md').read_text())
            report=(root/'docs/map-rendering-review.md').read_text()
            self.assertIn('Retained with verified editions',report)
            self.assertIn('https://example.test/bad',report)
            self.assertIn('Invalid colour range',report)
            del case['seconds']
            (audit/'resources/good/result.json').write_text(json.dumps({'complete':True,'sha256':'abc','cases':[case]}))
            with patch.object(publish_map_audit,'ROOT',audit),patch.object(publish_map_audit.storage,'ROOT',root),self.assertRaisesRegex(SystemExit,'Audit incomplete'):
                publish_map_audit.main()

    def test_empty_category_combination_returns_empty_data(self):
        from server.loader import prepare
        data=prepare(b'lat,lon,category\n41.39,2.17,A\n',{'format':'CSV','name':'points.csv'},filters={'category':'B'})
        self.assertEqual(data['selectedRows'],0)
        self.assertEqual(data['geometry']['features'],[])
        self.assertIn('No records match',data['notes'][0])

    def test_incomplete_audit_cannot_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'catalog.json').write_text(json.dumps({'datasets':[{'id':'d','mapMethods':['geometry'],'resources':[{'id':'missing','previewSupported':True}]}]}))
            with patch.object(publish_map_audit,'ROOT',root),self.assertRaisesRegex(SystemExit,'Audit incomplete'):publish_map_audit.main()

if __name__=='__main__':unittest.main()
