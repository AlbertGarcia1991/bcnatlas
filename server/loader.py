"""Bounded, on-demand readers for catalog-listed resources. No arbitrary URL endpoint."""
import csv
import hashlib
import io
import json
import math
import re
import tempfile
import time
import unicodedata
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import pandas as pd
import pyogrio
from pyogrio.raw import read as read_vector
from pyproj import CRS, Transformer
from shapely.geometry import shape, mapping, box
from shapely.ops import transform
from shapely import from_wkb, from_wkt
from defusedxml import ElementTree
from server import storage

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache/resources'
MAX_BYTES = 64 * 1024 * 1024
MAX_EXPANDED = 192 * 1024 * 1024
MAX_ROWS = 250_000
MAX_FEATURES = 150_000
CITY_ENVELOPE = box(2.04, 41.30, 2.24, 41.49)
SUPPORTED = {'CSV','JSON','GEOJSON','ZIP','GPKG','XLSX','XML','KML','KMZ'}

class ResourceError(Exception): pass

def safe_url(url):
    u = urlparse(url)
    if u.scheme != 'https' or u.hostname != 'opendata-ajuntament.barcelona.cat' or u.username or u.password or u.port not in (None, 443):
        raise ResourceError('This resource redirects outside the supported municipal host. Open the original source instead.')
    return url

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def fetch_resource(resource):
    if storage.source_mode() == 'r2':
        try:
            return storage.raw_resource(resource, MAX_BYTES)
        except storage.StorageError as e:
            raise ResourceError(str(e)) from e
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((resource['id'] + str(resource.get('modified'))).encode()).hexdigest()
    path = CACHE / key
    if path.exists(): return path.read_bytes(), datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    if resource.get('size') and int(resource['size']) > MAX_BYTES: raise ResourceError('Resource exceeds the 64 MiB preview limit. Download the original source.')
    request = urllib.request.Request(safe_url(resource['url']), headers={'User-Agent':'BarcelonaAtlas/1.1 (local open-data resource viewer)'})
    started = time.monotonic()
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.build_opener(SafeRedirect()).open(request, timeout=25) as response:
                safe_url(response.url)
                chunks, length = [], 0
                while True:
                    chunk = response.read(65536)
                    if not chunk: break
                    length += len(chunk)
                    if length > MAX_BYTES: raise ResourceError('Resource exceeds the 64 MiB preview limit. Download the original source.')
                    if time.monotonic() - started > 75: raise ResourceError('Source download timed out. Please retry or open the original resource.')
                    chunks.append(chunk)
            raw = b''.join(chunks)
            break
        except ResourceError: raise
        except Exception as e:
            last_error = e
            if attempt == 2 or time.monotonic() - started > 70:
                raise ResourceError('The municipal resource could not be downloaded after retries. Please retry later or open the original resource.') from e
            time.sleep(2 ** attempt)
    # Separate temp files permit concurrent requests for the same catalog resource.
    with tempfile.NamedTemporaryFile(dir=CACHE, prefix=key, delete=False) as tmp:
        tmp.write(raw); temporary = Path(tmp.name)
    temporary.replace(path)
    return raw, datetime.now(timezone.utc).isoformat()

def norm(s): return re.sub('[^a-z0-9]', '', unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode().lower())
def scalar(v):
    if v is None: return None
    if isinstance(v, (dict,list,tuple)): return json.dumps(v,ensure_ascii=False)[:500]
    try:
        if pd.isna(v): return None
    except (TypeError, ValueError): pass
    if hasattr(v,'item'): v = v.item()
    if isinstance(v, float) and not math.isfinite(v): return None
    if isinstance(v, (str,int,float,bool)): return v[:500] if isinstance(v,str) else v
    return str(v)[:500]

def numeric(v):
    if v is None or str(v).strip() in ('','..','-', 'NA'): return None
    s = str(v).strip().replace(' ', '')
    # Catalan decimals and thousands, or conventional dot decimals.
    if ',' in s and '.' in s: s = s.replace('.','').replace(',','.') if s.rfind(',') > s.rfind('.') else s.replace(',','')
    elif ',' in s: s = s.replace(',','.')
    try:
        n = float(s)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError): return None

def decode(raw):
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')): return raw.decode('utf-16')
    try: return raw.decode('utf-8-sig')
    except UnicodeDecodeError: return raw.decode('cp1252')

def flatten(row, prefix=''):
    result = {}
    for k,v in row.items():
        name = f'{prefix}.{k}' if prefix else str(k)
        if isinstance(v,dict) and name not in ('geometry','geojson'): result.update(flatten(v,name))
        else: result[name] = v
    return result

def json_rows(obj):
    if isinstance(obj,list): return obj, None
    if not isinstance(obj,dict): raise ResourceError('JSON does not contain records.')
    if obj.get('type') == 'FeatureCollection': return obj.get('features',[]), obj.get('crs',{}).get('properties',{}).get('name','EPSG:4326')
    if obj.get('type') == 'Feature': return [obj], 'EPSG:4326'
    for key in ('records','data','results','result','features','items','elements','stations'):
        if key in obj:
            try: return json_rows(obj[key])
            except ResourceError: pass
    raise ResourceError('This JSON structure needs a dedicated adapter. Use the original resource.')

def vector_rows(raw, suffix, layer=None):
    with tempfile.TemporaryDirectory(prefix='bcn-resource-') as directory:
        p = Path(directory)/('resource'+suffix); p.write_bytes(raw)
        available = [str(x[0]) for x in pyogrio.list_layers(p)]
        if layer and layer not in available: raise ResourceError('Unknown geometry layer')
        chosen = layer or available[0]
        info = pyogrio.read_info(p, layer=chosen)
        if info['features'] > MAX_ROWS: raise ResourceError(f"This geometry resource has {info['features']:,} features, exceeding the interactive limit. Download the original.")
        meta, _, geometries, fields = read_vector(p, layer=chosen, max_features=MAX_ROWS+1)
        rows=[]
        for i in range(len(fields[0]) if len(fields) else len(geometries)):
            row={str(name):scalar(fields[j][i]) for j,name in enumerate(meta['fields'])}
            if geometries is not None and geometries[i] is not None: row['_geometry']=mapping(from_wkb(geometries[i]))
            rows.append(row)
        return rows, meta.get('crs'), available, chosen

def read_rows(raw, fmt, name, member=None):
    fmt=fmt.upper(); layers=[]; chosen=None; crs=None
    if fmt in ('ZIP','KMZ') or (raw.startswith(b'PK') and fmt != 'XLSX'):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_EXPANDED: raise ResourceError('Expanded archive exceeds the 192 MiB limit.')
            names=[n for n in z.namelist() if not n.startswith('__MACOSX') and n.lower().endswith(('.csv','.json','.geojson','.gpkg','.kml','.shp'))]
            if member and member not in names: raise ResourceError('Unknown archive member')
            if not names: raise ResourceError('This archive contains no supported CSV, JSON, GeoJSON, GPKG, KML or Shapefile data.')
            chosen=member or next((n for n in names if n.lower().endswith(('.csv','.geojson','.json'))),names[0])
            if chosen.endswith('.shp'):
                # GDAL reads the archive in its virtual filesystem; nothing is extracted.
                rows,crs,_,_=vector_rows(raw,'.zip',Path(chosen).stem)
            else: rows,crs,_,_=read_rows(z.read(chosen),Path(chosen).suffix[1:].upper(),chosen)
            return rows,crs,names,chosen
    if fmt=='CSV':
        text=decode(raw)
        try: dialect=csv.Sniffer().sniff(text[:16384],delimiters=',;\t|')
        except csv.Error: dialect=csv.excel
        reader=csv.DictReader(io.StringIO(text, newline=""),dialect=dialect)
        rows=[]
        for row in reader:
            rows.append({str(k):v for k,v in row.items() if k is not None})
            if len(rows)>MAX_ROWS: raise ResourceError('This table exceeds the 250,000 row preview limit. Download the original resource.')
    elif fmt in ('JSON','GEOJSON'):
        rows,crs=json_rows(json.loads(decode(raw)))
    elif fmt=='XLSX':
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if sum(i.file_size for i in archive.infolist()) > MAX_EXPANDED: raise ResourceError('Expanded workbook exceeds the preview limit.')
        workbook=pd.ExcelFile(io.BytesIO(raw),engine='openpyxl');layers=workbook.sheet_names;chosen=member or layers[0]
        if chosen not in layers: raise ResourceError('Unknown worksheet')
        frame=pd.read_excel(workbook,sheet_name=chosen,nrows=MAX_ROWS+1);rows=frame.to_dict('records')
    elif fmt in ('GPKG','KML'): return vector_rows(raw,'.'+fmt.lower(),member)
    elif fmt=='XML':
        root=ElementTree.fromstring(raw)
        candidates=[e for e in root.iter() if len(e) and all(len(c)==0 for c in e)]
        rows=[{c.tag.split('}')[-1]:c.text for c in e} for e in candidates]
    else: raise ResourceError('This format requires specialist software. Download the original resource from the catalog.')
    if len(rows)>MAX_ROWS: raise ResourceError('Resource exceeds the 250,000 row preview limit. Download the original.')
    return rows,crs,layers,chosen

LAT={'lat','latitudy','stationlat','latitude','latitud','latitudwgs84','geolat','latitudewgs84','geoepgs4326lat','geoepsg4326lat'}
LON={'lon','longitudx','stationlng','lng','long','longitude','longitud','longitudwgs84','geolon','longitudewgs84','geoepgs4326lon','geoepsg4326lon'}
DISTRICT={'codidistricte','districtcode','addressesdistrictid','districtid','districted'}

def transform_geometry(geom, crs):
    if not geom: return None
    geometry=shape(geom)
    if geometry.is_empty: return None
    if crs:
        source=CRS.from_user_input(crs)
        if source != CRS.from_epsg(4326): geometry=transform(Transformer.from_crs(source,4326,always_xy=True).transform,geometry)
    # Unknown projected geometries are never silently assumed to be geographic.
    if not all(math.isfinite(x) for x in geometry.bounds) or not CITY_ENVELOPE.intersects(geometry): return None
    # Restrict non-point geometry to the same Barcelona sanity envelope.
    if geometry.geom_type not in ('Point','MultiPoint'):
        if not geometry.is_valid: geometry=geometry.buffer(0) if 'Polygon' in geometry.geom_type else geometry
        geometry=geometry.intersection(CITY_ENVELOPE).simplify(.00001,preserve_topology=True)
    elif geometry.geom_type=='MultiPoint': geometry=geometry.intersection(CITY_ENVELOPE)
    return mapping(geometry) if not geometry.is_empty else None

def prepare(raw, resource, member=None, year=None):
    rows,crs,members,chosen=read_rows(raw,resource['format'],resource['name'],member)
    total=len(rows); flat=[]; geometries=[]
    for row in rows:
        if not isinstance(row,dict): continue
        if row.get('type')=='Feature': geometries.append(row.get('geometry'));flat.append(flatten(row.get('properties') or {}))
        else: geometries.append(row.get('_geometry'));flat.append(flatten({k:v for k,v in row.items() if k!='_geometry'}))
    fields=list(dict.fromkeys(k for row in flat[:500] for k in row))[:100]
    normalized={norm(k):k for k in fields}
    lat=next((normalized[k] for k in LAT if k in normalized),None)
    lon=next((normalized[k] for k in LON if k in normalized),None)
    district=next((normalized[k] for k in DISTRICT if k in normalized),None)
    yearfield=next((normalized[k] for k in ['any','year','nkany','anydata'] if k in normalized),None)
    years=sorted(set(str(row.get(yearfield)) for row in flat if yearfield and re.fullmatch(r'(19|20)\d{2}',str(row.get(yearfield)))))
    if year and year not in years: raise ResourceError('The requested year is not present in this resource.')
    # Projected coordinate columns must name their CRS explicitly.
    xkey=next((normalized[k] for k in ['xetrs89','coordenadaxetrs89','utmxetrs89','coordenadautmxed50'] if k in normalized),None)
    ykey=next((normalized[k] for k in ['yetrs89','coordenadayetrs89','utmyetrs89','coordenadautmyed50'] if k in normalized),None)
    projector=Transformer.from_crs(23031 if xkey and 'ed50' in norm(xkey) else 25831,4326,always_xy=True) if xkey and ykey else None
    geomkey=next((normalized[k] for k in ['geometry','geom','geometria','wkt'] if k in normalized),None)
    features=[];preview=[];selected=0;excluded=0;geometrytypes=set();numericstats={};unmapped=0
    for row,geom in zip(flat,geometries):
        if year and str(row.get(yearfield))!=year: continue
        selected+=1
        props={k:scalar(row.get(k)) for k in fields}
        if len(preview)<100: preview.append(props)
        if not geom and lat and lon:
            x,y=numeric(row.get(lon)),numeric(row.get(lat))
            if x is not None and y is not None: geom={'type':'Point','coordinates':[x,y]}
        elif not geom and projector:
            x,y=numeric(row.get(xkey)),numeric(row.get(ykey))
            if x is not None and y is not None: geom={'type':'Point','coordinates':list(projector.transform(x,y))}
        elif not geom and geomkey:
            try:
                v=row[geomkey]
                geom=v if isinstance(v,dict) else json.loads(v) if str(v).startswith('{') else mapping(from_wkt(v))
            except Exception: pass
        if geom:
            try: geom=transform_geometry(geom,crs)
            except Exception: geom=None
            if geom:
                geometrytypes.add(geom['type'])
                props['_district']=int(numeric(row.get(district)) or 0) if district else 0
                features.append({'type':'Feature','geometry':geom,'properties':props})
                for key,value in props.items():
                    n=numeric(value)
                    if key!='_district' and n is not None:
                        lo,hi,count=numericstats.get(key,(n,n,0));numericstats[key]=(min(lo,n),max(hi,n),count+1)
            else: excluded+=1
        else: unmapped+=1
    if len(features)>MAX_FEATURES: raise ResourceError('More than 150,000 map features. Select a year or download the source for desktop GIS.')
    if not selected: raise ResourceError('This resource has no records to preview.')
    numericfields=[{'name':k,'min':v[0],'max':v[1],'count':v[2]} for k,v in numericstats.items() if v[2] >= max(1,len(features)*.5) and norm(k) not in LAT|LON|DISTRICT and k!=yearfield and v[0]!=v[1]]
    fc={'type':'FeatureCollection','features':features}
    result={'totalRows':total,'selectedRows':selected,'mappedCount':len(features),'excluded':excluded,'withoutGeometry':unmapped,'fields':fields,'preview':preview,'geometry':fc,'geometryTypes':sorted(geometrytypes),'numericFields':numericfields,'years':years,'yearField':yearfield,'selectedYear':year,'members':members,'member':chosen,'hasDistrict':bool(district),'sourceSha256':hashlib.sha256(raw).hexdigest(),'notes':[]}
    if not features: result['notes'].append('No supported coordinate or geometry fields were found. This resource is available as a table; no locations have been invented.')
    if unmapped or excluded: result['notes'].append(f'{unmapped:,} records have no recognized geometry; {excluded:,} invalid or outside the Barcelona envelope are excluded from the map.')
    if not district: result['notes'].append('No recognized district code. This overlay is city-wide and is not affected by the curated district filter.')
    if chosen: result['notes'].append('Showing archive member, worksheet or geometry layer: '+chosen)
    result['notes'].append('Coordinates use the source CRS when declared. Lines and polygons are clipped to the Barcelona sanity envelope and simplified by ~1 metre. Counts refer to source features, not necessarily unique places.')
    # Prevent unexpectedly huge responses from very complex geometry.
    if len(json.dumps(result,separators=(',',':'))) > 48*1024*1024: raise ResourceError('Processed resource exceeds the interactive response limit. Use the original resource in desktop GIS.')
    return result
