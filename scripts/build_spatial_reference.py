"""Build reproducible joins from downloaded official municipal reference resources."""
import gzip
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from shapely import from_wkt
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from pyproj import Transformer
from server import storage
from server.loader import read_rows, transform_geometry, numeric
from server.spatial import code, norm, REFERENCE_KEY

def build():
    folder = storage.ROOT / '.cache/spatial'
    folder.mkdir(parents=True, exist_ok=True)
    sources = []
    def rows(name, member=None):
        if not (folder / name).exists():
            catalog = storage.catalog()
            aliases = {'aforaments-descriptiu.csv': 'aforaments-descriptiu', 'metadades-estacions-meteorologiques.csv': 'metadades-estacions-meteorologiques'}
            matches = [(d,r) for d in catalog['datasets'] for r in d['resources'] if r['name'] == name or (d['id'] == aliases.get(name) and r['format'].upper() == 'CSV')]
            if not matches: raise RuntimeError('Reference input not in the catalog: ' + name)
            d,r = matches[0]
            raw = storage.raw_resource({**r, '_dataset_id': d['id']}, 64*1024*1024)[0]
            (folder / name).write_bytes(raw)
        raw = (folder / name).read_bytes()
        sources.append({'file': name, 'sha256': hashlib.sha256(raw).hexdigest()})
        return read_rows(raw, 'ZIP' if name.endswith('.zip') else 'CSV', name, member)[0]
    ref = {k: {} for k in ('district', 'neighbourhood', 'section', 'aeb', 'street', 'streetNames', 'addresses', 'postcode')}
    ref['names'] = {'district': {}, 'neighbourhood': {}}
    for row in rows('BarcelonaCiutat_Districtes.csv'):
        key = code(row['Codi_Districte'])
        geom = transform_geometry(mapping(from_wkt(row['geometria_wgs84'])), 'EPSG:4326')
        ref['district'][key] = {'geometry': geom, 'district': int(key), 'name': row['nom_districte']}
        ref['names']['district'][norm(row['nom_districte'])] = key
    neighbourhoods = defaultdict(list)
    for row in rows('BarcelonaCiutat_SeccionsCensals.csv'):
        district, section, barrio = code(row['codi_districte']), code(row['codi_seccio_censal']), code(row['codi_barri'])
        geom = transform_geometry(mapping(from_wkt(row['geometria_wgs84'])), 'EPSG:4326')
        ref['section'][f'{district}:{section}'] = {'geometry': geom, 'district': int(district), 'name': f'{row["nom_barri"]} · {district}/{section}'}
        neighbourhoods[barrio].append(shape(geom))
        ref['neighbourhood'][barrio] = {'district': int(district), 'name': row['nom_barri']}
        ref['names']['neighbourhood'][norm(row['nom_barri'])] = barrio
    for key, geometries in neighbourhoods.items(): ref['neighbourhood'][key]['geometry'] = mapping(unary_union(geometries))
    for row in rows('BarcelonaCiutat_AreesEstadistiquesBasiques.csv'):
        ref['aeb'][code(row['aeb'])] = {'geometry': transform_geometry(mapping(from_wkt(row['geometria_wgs84'])), 'EPSG:4326'), 'district': int(row['codi_districte']), 'name': 'AEB ' + row['aeb']}
    ambiguous = set()
    def alias(name, key):
        name = norm(name)
        if not name: return
        if name in ref['streetNames'] and ref['streetNames'][name] != key: ambiguous.add(name)
        else: ref['streetNames'][name] = key
    for row in rows('carrerer.csv'):
        key = code(row['codi_via'])
        for field in ('nom_oficial', 'nom_curt'): alias(row[field], key)
    projector = Transformer.from_crs(25831, 4326, always_xy=True)
    nodes = {r['C_Nus']: list(projector.transform(float(r['Coord_X']), float(r['Coord_Y']))) for r in rows('graf_viari_csv.zip', 'BCN_GrafVial_Nodes_ETRS89_CSV.csv')}
    lines = defaultdict(list); districts = defaultdict(set)
    for row in rows('graf_viari_csv.zip', 'BCN_GrafVial_Trams_ETRS89_CSV.csv'):
        if row['C_Nus_I'] not in nodes or row['C_Nus_F'] not in nodes: continue
        for side in ('D', 'E'):
            key = code(row['CVia_' + side])
            if not key or key == '0': continue
            line = [nodes[row['C_Nus_I']], nodes[row['C_Nus_F']]]
            if line not in lines[key]: lines[key].append(line)
            d = code(row['Distric_' + side])
            if d and 1 <= int(d) <= 10: districts[key].add(int(d))
            alias(row['NVia_' + side], key)
            ref['street'][key] = {'name': row['NVia_' + side]}
    for key, coordinates in lines.items():
        ref['street'][key].update(geometry=transform_geometry({'type': 'MultiLineString', 'coordinates': coordinates}, 'EPSG:4326'), district=next(iter(districts[key])) if len(districts[key]) == 1 else 0)
    ambiguous_addresses = set()
    postal_points = defaultdict(set)
    for row in rows('adreces_postals_elementals.csv'):
        key = ':'.join([code(row['codi_carrer']), code(row['numpost']), norm(row['llepost'])])
        value = [float(row['longitud_wgs84']), float(row['latitud_wgs84']), int(row['districte'])]
        if not (2.04 <= value[0] <= 2.24 and 41.30 <= value[1] <= 41.49): continue
        postal = code(row['dist_post'])
        if postal and 1 <= int(postal) <= 99: postal_points[str(8000 + int(postal))].add(tuple(value[:2]))
        if key in ref['addresses'] and ref['addresses'][key] != value: ambiguous_addresses.add(key)
        else: ref['addresses'][key] = value
    for key in ambiguous_addresses: ref['addresses'].pop(key, None)
    for key in ambiguous: ref['streetNames'].pop(key, None)
    for key, points in postal_points.items():
        ref['postcode'][key] = {'geometry': {'type': 'MultiPoint', 'coordinates': sorted(points)}, 'district': 0, 'name': 'Postal code ' + key.zfill(5)}
    ref['entities'] = {}
    for filename, kind, keyfield, namefield in [('aforaments-descriptiu.csv','traffic count site','Id_aforament','Desc_aforament'), ('metadades-estacions-meteorologiques.csv','weather station','CODI_ESTACIO','NOM_ESTACIO')]:
        entities = {}; ambiguous_entities = set()
        for row in rows(filename):
            normalized = {norm(k):v for k,v in row.items()}
            x,y = numeric(normalized.get('longitud')), numeric(normalized.get('latitud'))
            if x is None or y is None: continue
            geom = transform_geometry({'type':'Point','coordinates':[x,y]}, 'EPSG:4326')
            if not geom: continue
            key = norm(row[keyfield]); value = {'geometry':geom,'district':int(numeric(normalized.get('codidistricte')) or 0),'name':row[namefield]}
            if key in entities and entities[key]['geometry'] != geom: ambiguous_entities.add(key)
            else: entities[key] = value
        for key in ambiguous_entities: entities.pop(key, None)
        ref['entities'][kind] = entities
    ref['provenance'] = {'publisher': 'Ajuntament de Barcelona', 'license': 'CC BY 4.0', 'builtAt': datetime.now(timezone.utc).isoformat(), 'sources': sources, 'boundaryNote': 'Current municipal boundaries; historical observations are not reconstructed onto historical boundaries.', 'streetNote': 'Street lines connect official road-graph nodes; postal points use exact, unambiguous address matches.'}
    assert len(ref['district']) == 10 and len(ref['neighbourhood']) == 73 and len(ref['section']) == 1068
    raw = gzip.compress(json.dumps(ref, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0)
    (folder / 'reference.json.gz').write_bytes(raw)
    print({k: len(ref[k]) for k in ('district', 'neighbourhood', 'section', 'aeb', 'street', 'addresses')})
    print('Reference bytes:', len(raw))
    return raw

if __name__ == '__main__':
    import sys
    raw = build()
    if '--publish' in sys.argv:
        from scripts.r2_assets import put_verified
        try:
            existing = storage.object_bytes(storage.public_bucket(), REFERENCE_KEY, 24*1024*1024)[0]
        except storage.MissingObject: existing = None
        if existing is not None and existing != raw:
            raise SystemExit('Reference keys are immutable. Set a new SPATIAL_REFERENCE_KEY before publishing a rebuilt reference.')
        put_verified(storage.public_bucket(), REFERENCE_KEY, raw, 'application/gzip')
