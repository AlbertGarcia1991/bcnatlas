from pathlib import Path
import io
import json
import unittest
import zipfile
from unittest.mock import patch
from fastapi.testclient import TestClient
from server.loader import prepare, read_rows, ResourceError, safe_url, numeric, MAX_EXPANDED
from server.app import app
from scripts.sync_catalog import build

class ReaderTests(unittest.TestCase):
    def resource(self,fmt='CSV'): return {'format':fmt,'name':'test','id':'test'}
    def test_utf16_municipal_equipment_schema(self):
        raw='register_id,name,geo_epgs_4326_lat,geo_epgs_4326_lon,addresses_district_id\r\n1,Library,41.39,2.17,2\r\n'.encode('utf-16')
        result=prepare(raw,self.resource())
        self.assertEqual(result['mappedCount'],1)
        self.assertEqual(result['geometry']['features'][0]['properties']['_district'],2)
    def test_year_filter_preserves_duplicate_locations(self):
        raw=b'year,lat,lon,count\n2023,41.39,2.17,10\n2024,41.39,2.17,20\n2024,41.39,2.17,30\n'
        result=prepare(raw,self.resource(),year='2024')
        self.assertEqual(result['years'],['2023','2024']);self.assertEqual(result['totalRows'],3)
        self.assertEqual(result['mappedCount'],2);self.assertEqual(result['selectedRows'],2)
        with self.assertRaises(ResourceError): prepare(raw,self.resource(),year='1990')
    def test_nonspatial_table_remains_table(self):
        result=prepare(b'Any,Concepte,Total\n2024,City budget,10000\n',self.resource())
        self.assertEqual(result['mappedCount'],0);self.assertEqual(result['selectedRows'],1)
        self.assertEqual(result['withoutGeometry'],1)
    def test_projected_geojson_reprojected_and_geometry_preserved(self):
        raw=json.dumps({'type':'FeatureCollection','crs':{'properties':{'name':'EPSG:25831'}},'features':[{'type':'Feature','geometry':{'type':'LineString','coordinates':[[430000,4580000],[430100,4580100]]},'properties':{'value':20}}]}).encode()
        result=prepare(raw,self.resource('GeoJSON'))
        self.assertEqual(result['mappedCount'],1);self.assertEqual(result['geometryTypes'],['LineString'])
        self.assertTrue(2<result['geometry']['features'][0]['geometry']['coordinates'][0][0]<3)
    def test_outside_coordinates_not_mapped(self):
        result=prepare(b'lat,lon\n41.39,2.17\n0,0\nNaN,2.17\n',self.resource())
        self.assertEqual(result['mappedCount'],1);self.assertEqual(result['excluded'],1);self.assertEqual(result['withoutGeometry'],1)
    def test_archive_member_selection(self):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z:
            z.writestr('one.csv','lat,lon\n41.39,2.17\n')
            z.writestr('two.csv','lat,lon\n41.40,2.18\n41.41,2.19\n')
        result=prepare(buffer.getvalue(),self.resource('ZIP'),member='two.csv')
        self.assertEqual(result['mappedCount'],2);self.assertEqual(result['member'],'two.csv')
        with self.assertRaises(ResourceError):prepare(buffer.getvalue(),self.resource('ZIP'),member='../x')
    def test_archive_size_limit(self):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z:z.writestr('a.csv','lat,lon\n41.39,2.17\n')
        with patch('server.loader.MAX_EXPANDED',5):
            with self.assertRaises(ResourceError):prepare(buffer.getvalue(),self.resource('ZIP'))
    def test_numeric_locale(self):
        self.assertEqual(numeric('1.234,56'),1234.56);self.assertEqual(numeric('1,234.56'),1234.56)
        self.assertIsNone(numeric('NaN'))
    def test_nested_json_coordinate_fields(self):
        result=prepare(json.dumps({'data':[{'geo':{'epgs4326lat':41.39,'epgs4326lon':2.17},'name':'A'}]}).encode(),self.resource('JSON'))
        self.assertEqual(result['mappedCount'],1)
    def test_external_and_local_urls_rejected(self):
        for url in ['http://opendata-ajuntament.barcelona.cat/test','https://localhost/x','https://opendata-ajuntament.barcelona.cat.evil.org/x','https://user:pass@opendata-ajuntament.barcelona.cat/a','https://opendata-ajuntament.barcelona.cat:123/a']:
            with self.assertRaises(ResourceError):safe_url(url)
    def test_xml_entity_expansion_is_disabled(self):
        with self.assertRaises(Exception):read_rows(b'<!DOCTYPE x [<!ENTITY attack SYSTEM "file:///etc/passwd">]><rows><row><name>&attack;</name></row></rows>','XML','test')

class CatalogTests(unittest.TestCase):
    @unittest.skipUnless((Path(__file__).resolve().parents[1]/"public/data/catalog.json").exists(), "Optional local dataset snapshot; excluded from Git")
    def test_complete_snapshot_and_sources(self):
        from pathlib import Path
        catalog=json.loads((Path(__file__).resolve().parents[1]/'public/data/catalog.json').read_text())
        self.assertEqual(catalog['count'],len(catalog['datasets']))
        self.assertGreater(catalog['count'],400)
        self.assertNotIn('alcaldes-alcaldesses-bcn', {d['id'] for d in catalog['datasets']})
        self.assertEqual(catalog['resourceCount'],sum(len(d['resources']) for d in catalog['datasets']))
        self.assertEqual(len({d['id'] for d in catalog['datasets']}),catalog['count'])
        for d in catalog['datasets']:
            self.assertTrue(d['title']);self.assertTrue(d['url']);self.assertTrue(d['license'])
            for r in d['resources']:self.assertTrue(safe_url(r['url']))
    def test_api_rejects_unlisted_dataset_resource_pair(self):
        client=TestClient(app)
        with patch('server.storage.catalog',return_value={'datasets':[]}):
            self.assertEqual(client.get('/api/resource/unknown/unknown').status_code,404)
        self.assertEqual(client.get('/api/health').json()['status'],'ok')
    def test_undated_resources_do_not_inherit_publication_year(self):
        catalog=build([{'name':'example','title':'Example','resources':[{'id':'a','name':'current.csv','format':'CSV','url':'https://opendata-ajuntament.barcelona.cat/x','last_modified':'2026-11-07'},{'id':'b','name':'2022_2023_data.csv','format':'CSV','url':'https://opendata-ajuntament.barcelona.cat/y'}]}])
        self.assertEqual(catalog['datasets'][0]['resources'][0]['years'],[])
        self.assertEqual(catalog['datasets'][0]['resources'][1]['years'],['2022','2023'])
