"""Exact joins against a versioned municipal reference, never remote/fuzzy geocoding."""
import gzip
import json
import re
import unicodedata
from functools import lru_cache
from shapely.geometry import shape
from server import storage

REFERENCE_KEY = storage.SPATIAL_REFERENCE_KEY
RELATIONS = {
    'aforaments-detall': ('traffic count site', 'idaforament'),
    'mesures-estacions-meteorologiques': ('weather station', 'codiestacio'),
}

def norm(value):
    return re.sub('[^a-z0-9]', '', unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower())

def code(value):
    value = str(value or '').strip()
    return str(int(float(value))) if re.fullmatch(r'\d+(?:\.0+)?', value) else ''

ALIASES = {
    'district': ('codidistricte', 'districtcode', 'addressesdistrictid', 'districtid', 'districted', 'districte', 'district', 'dte', 'districteres'),
    'districtName': ('nomdistricte', 'districtname', 'addressesdistrictname'),
    'neighbourhood': ('codibarri', 'neighborhoodcode', 'neighbourhoodcode', 'addressesneighborhoodid', 'barri', 'barris'),
    'neighbourhoodName': ('nombarri', 'descbarri', 'neighborhoodname', 'neighbourhoodname', 'addressesneighborhoodname'),
    'section': ('codisecciocensal', 'secciocensal', 'secccens', 'seccens'),
    'aeb': ('codiaeb', 'aeb', 'seccest'),
    'street': ('codicarrer', 'codivia', 'streetcode', 'addressesroadid', 'codicarrerd'),
    'streetName': ('nomcarrer', 'nomcarrerd', 'nomvia', 'nomoficial', 'street', 'streetname', 'carrer', 'addressesroadname'),
    'number': ('numpost', 'numero', 'numeropostal', 'numportal', 'addressesstartstreetnumber', 'numeroportal'),
    'letter': ('llepost', 'lletra', 'letter'),
    'address': ('adreca', 'direccio', 'direccion', 'address', 'adrecacompleta', 'localitzacio', 'ubicacio', 'llocacte'),
    'postcode': ('codipostal', 'codigopostal', 'postcode', 'postalcode', 'distpost'),
}

def columns(fields):
    normalized = {norm(f): f for f in fields}
    return {kind: next((normalized[a] for a in aliases if a in normalized), None) for kind, aliases in ALIASES.items()}

def spatial_methods(fields):
    names = {norm(f) for f in fields}
    cols = columns(fields)
    methods = []
    if any('geometr' in f or f in ('wkt', 'geom') for f in names): methods.append('geometry')
    if any('latitud' in f or f in ('lat', 'stationlat') for f in names) or any('etrs89' in f for f in names): methods.append('coordinates')
    for key in ('section', 'aeb', 'neighbourhood', 'district', 'street', 'address', 'postcode'):
        if cols.get(key) or cols.get(key + 'Name'): methods.append(key)
    return methods

@lru_cache(maxsize=1)
def reference():
    local = storage.ROOT / '.cache/spatial/reference.json.gz'
    if storage.source_mode() == 'local' and local.exists(): raw = local.read_bytes()
    else: raw = storage.object_bytes(storage.public_bucket(), REFERENCE_KEY, 24 * 1024 * 1024)[0]
    return json.loads(gzip.decompress(raw))

def resolve(row, cols, ref, dataset_id=''):
    def value(key): return row.get(cols.get(key)) if cols.get(key) else None
    def area(kind, raw):
        key = code(raw)
        if key and key in ref[kind]: return key
        labelled = re.fullmatch(r'\s*(\d+)\.\s*(.+)', str(raw or ''))
        if labelled:
            key = code(labelled[1])
            if key in ref[kind] and norm(ref[kind][key]['name']) == norm(labelled[2]): return key
        return ref.get('names', {}).get(kind, {}).get(norm(raw))
    district = area('district', value('district')) or area('district', value('districtName'))
    if dataset_id in RELATIONS:
        relation, field = RELATIONS[dataset_id]
        source_field = next((k for k in row if norm(k) == field), None)
        key = norm(row.get(source_field))
        match = ref.get('entities', {}).get(relation, {}).get(key) if key else None
        return (match, relation, key) if match else (None, '', '')
    # Prefer the most precise location supplied. Do not silently move an unknown
    # neighbourhood/section into the containing district.
    street_name = norm(value('streetName'))
    street = code(value('street')) or (ref['streetNames'].get(street_name) if street_name else None)
    number = code(value('number'))
    letter = norm(value('letter'))
    if not street and value('address'):
        address = str(value('address')).strip()
        match = re.fullmatch(r'(.+?)[,\s]+(\d+)\s*([A-Za-z]?)', address)
        if match:
            street = ref['streetNames'].get(norm(match[1])); number = code(match[2]); letter = norm(match[3])
        else: street = ref['streetNames'].get(norm(address))
    if street:
        if number:
            key = f'{street}:{number}:{letter}'
            point = ref['addresses'].get(key)
            if point: return ({'geometry': {'type': 'Point', 'coordinates': point[:2]}, 'district': point[2], 'name': str(value('address') or value('streetName') or street)}, 'postal address', key)
            return None, '', ''
        match = ref['street'].get(street)
        if match and 'districts' not in match:
            line = shape(match['geometry'])
            match['districts'] = [int(key) for key, area_ref in ref['district'].items() if line.intersects(shape(area_ref['geometry']))]
        return (match, 'street graph', street) if match else (None, '', '')
    postcode = code(value('postcode'))
    if postcode:
        if len(postcode) <= 2: postcode = str(8000 + int(postcode))
        match = ref.get('postcode', {}).get(postcode)
        return (match, 'postal address coverage', postcode) if match else (None, '', '')
    section = code(value('section'))
    if section:
        key = f'{district}:{section}'
        match = ref['section'].get(key) if district else None
        return (match, 'census section', key) if match else (None, '', '')
    aeb = code(value('aeb'))
    if aeb:
        match = ref['aeb'].get(aeb)
        return (match, 'statistical area', aeb) if match else (None, '', '')
    for kind, label in [('neighbourhood', 'neighbourhood'), ('district', 'district')]:
        raw = value(kind) or value(kind + 'Name')
        if raw is not None and str(raw).strip() not in ('', '0', '00', '-', '..'):
            key = area(kind, raw)
            match = ref[kind].get(key)
            return (match, label, key) if match else (None, '', '')
    return None, '', ''
