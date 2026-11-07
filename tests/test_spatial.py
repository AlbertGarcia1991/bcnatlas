import unittest
from unittest.mock import patch
from server.loader import prepare
from server.spatial import columns, resolve

POLYGON = {'type': 'Polygon', 'coordinates': [[[2.15,41.38],[2.16,41.38],[2.16,41.39],[2.15,41.39],[2.15,41.38]]]}
AREA = {'geometry': POLYGON, 'district': 2, 'name': 'Eixample'}
REFERENCE = {'district': {'2': AREA}, 'neighbourhood': {'6': AREA}, 'section': {'2:1': AREA}, 'aeb': {},
             'names': {'district': {'eixample': '2'}, 'neighbourhood': {'sagradafamilia': '6'}},
             'street': {'123': {'geometry': {'type':'LineString','coordinates':[[2.15,41.38],[2.16,41.39]]}, 'district': 2, 'name': 'Carrer de Prova'}},
             'streetNames': {'carrerdeprova': '123'}, 'addresses': {'123:10:': [2.15,41.38,2]}, 'provenance': {'license': 'CC BY 4.0'}}

class SpatialTests(unittest.TestCase):
    def prepare(self, text, **kwargs):
        with patch('server.spatial.reference', return_value=REFERENCE):
            return prepare(text.encode(), {'format':'CSV','name':'test'}, **kwargs)

    def test_district_code_and_name_join_to_polygon(self):
        for field, value in [('Codi_Districte','02'),('Nom_Districte','Eixample')]:
            result = self.prepare(f'{field},Value\n{value},12\n')
            self.assertEqual(result['geometryTypes'], ['Polygon'])
            self.assertEqual(result['mappedCount'], 1)
            self.assertTrue(result['hasDistrict'])

    def test_missing_street_does_not_match_empty_alias(self):
        with patch.dict(REFERENCE['streetNames'], {'': '123'}):
            result = self.prepare('Codi_Barri,Value\n6,12\n')
        self.assertEqual(result['locationMethods'], ['neighbourhood'])

    def test_precise_section_does_not_fall_back_to_district(self):
        result = self.prepare('Codi_Districte,Seccio_Censal,Value\n2,1,12\n2,999,20\n')
        self.assertEqual(result['mappedCount'], 1)
        self.assertEqual(result['withoutGeometry'], 1)
        self.assertEqual(result['locationMethods'], ['census section'])

    def test_nonspatial_table_has_no_reference_reads(self):
        with patch('server.spatial.reference') as ref:
            result = prepare(b'Name,Start\nMayor,2020\n', {'format':'CSV','name':'mayors'})
        ref.assert_not_called()
        self.assertEqual(result['mappedCount'], 0)

    def test_exact_postal_address_and_unmatched_number(self):
        result = self.prepare('Adreca,Value\n"Carrer de Prova, 10",12\n"Carrer de Prova, 99",20\n')
        self.assertEqual(result['mappedCount'], 1)
        self.assertEqual(result['withoutGeometry'], 1)
        self.assertEqual(result['geometry']['features'][0]['geometry']['coordinates'], (2.15,41.38))

    def test_street_name_produces_line(self):
        result = self.prepare('Nom_Carrer,Value\nCarrer de Prova,12\n')
        self.assertEqual(result['geometryTypes'], ['LineString'])

    def test_year_category_filter_and_explicit_mean(self):
        text = 'Any,Codi_Districte,Sexe,Value\n2024,2,F,10\n2024,2,M,30\n2023,2,F,100\n'
        result = self.prepare(text, year='2024')
        self.assertEqual(result['matchedRows'], 2)
        self.assertEqual(result['mappedCount'], 1)
        props = result['geometry']['features'][0]['properties']
        self.assertEqual(props['Value'], 20)
        self.assertEqual(props['_records'], 2)
        self.assertEqual(result['preview'][0]['Value'], '10')
        self.assertNotIn('Sexe', props)
        filtered = self.prepare(text, year='2024', filters={'Sexe':'F'})
        self.assertEqual(filtered['geometry']['features'][0]['properties']['Value'], 10)
        self.assertEqual(filtered['selectedRows'], 1)

    def test_numeric_categories_are_not_averaged_or_colour_metrics(self):
        result = self.prepare('Codi_Districte,Sexe,Value\n2,1,10\n2,2,20\n')
        self.assertNotIn('Sexe', result['geometry']['features'][0]['properties'])
        self.assertNotIn('Sexe', [f['name'] for f in result['numericFields']])
        self.assertEqual(result['geometry']['features'][0]['properties']['Value'], 15)

    def test_native_geometry_takes_priority_over_join(self):
        with patch('server.spatial.reference') as ref:
            result = prepare(b'lat,lon,Codi_Districte\n41.39,2.17,2\n', {'format':'CSV','name':'points'})
        ref.assert_not_called()
        self.assertEqual(result['geometryTypes'], ['Point'])

    def test_municipal_wgs84_wkt_field(self):
        result = self.prepare('geometria_wgs84,Value\n"POINT (2.17 41.39)",12\n')
        self.assertEqual(result['mappedCount'], 1)

    def test_crs_belongs_to_the_selected_geometry_not_other_columns(self):
        result = self.prepare('lat,lon,geometria_etrs89\n41.39,2.17,"POINT (430000 4580000)"\n')
        self.assertEqual(result['mappedCount'], 1)
        self.assertEqual(result['geometry']['features'][0]['geometry']['coordinates'], (2.17,41.39))

    def test_invalid_filter_rejected_before_parser_spawn(self):
        from fastapi.testclient import TestClient
        from server.app import app
        for value in ['[]', '{"a":12}', 'not json', 'x'*4097]:
            response = TestClient(app).get('/api/resource/example/example', params={'filters':value})
            self.assertEqual(response.status_code, 400)
