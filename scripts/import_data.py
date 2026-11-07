"""Reproducible, fail-closed Open Data BCN snapshot importer (stdlib only)."""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import time
import urllib.request
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
API = 'https://opendata-ajuntament.barcelona.cat/data/api/action/package_show?id='
DATASETS = [('accidents', 'accidents-gu-bcn'), ('street-trees', 'arbrat-viari'), ('park-trees', 'arbrat-parcs')]
YEARS = [2023, 2024, 2025]

def download(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                return response.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)

def normalize(row):
    row = {k.strip().lower(): v for k, v in row.items() if k}
    def number(*keys):
        for key in keys:
            value = row.get(key, '').strip()
            if value:
                return float(value.replace(',', '.'))
        raise ValueError('Missing coordinate')
    try:
        lat = number('latitud_wgs84', 'latitud')
        lng = number('longitud_wgs84', 'longitud')
        # Broad sanity envelope, not a municipal boundary. Source defines city scope.
        if not (math.isfinite(lat) and math.isfinite(lng) and 41.30 <= lat <= 41.49 and 2.04 <= lng <= 2.24):
            return None
        district = int(row.get('codi_districte', '0') or 0)
        if not 1 <= district <= 10:
            district = 0
        return [round(lng, 6), round(lat, 6), district]
    except (ValueError, TypeError):
        return None

def parse(raw):
    if raw.startswith(b'PK'):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith('.csv') and not n.startswith('__MACOSX')]
            if len(names) != 1:
                raise ValueError('Expected exactly one CSV in archive')
            raw = archive.read(names[0])
    text = raw.decode('utf-8-sig')
    dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    points, dropped, total = [], 0, 0
    for row in reader:
        total += 1
        point = normalize(row)
        if point is None:
            dropped += 1
        else:
            points.append(point)
    if not points or dropped / total > .1:
        raise ValueError(f'Invalid coordinate schema or excessive rejected rows: {dropped}/{total}')
    return points, dropped, total

def main():
    output = ROOT / 'public/data'
    output.mkdir(parents=True, exist_ok=True)
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    manifest = {'version': '1.0.0', 'retrievedAt': datetime.now(timezone.utc).isoformat(), 'years': YEARS, 'datasets': {}}
    for key, slug in DATASETS:
        package = json.loads(download(API + slug))['result']
        dataset = {'slug': slug, 'title': package.get('title'), 'publisher': 'Ajuntament de Barcelona', 'license': package.get('license_title'), 'licenseUrl': package.get('license_url') or 'https://creativecommons.org/licenses/by/4.0/', 'url': 'https://opendata-ajuntament.barcelona.cat/data/en/dataset/' + slug, 'years': {}}
        for year in YEARS:
            prefix = str(year) if key == 'accidents' else f'{year}_4T'
            resource = next(r for r in package['resources'] if r['name'].startswith(prefix) and '.csv' in r['name'].lower())
            cached = cache / resource['id']
            if not cached.exists():
                print(f'Downloading {resource["name"]}', flush=True)
                cached.write_bytes(download(resource['url']))
            raw = cached.read_bytes()
            points, dropped, total = parse(raw)
            filename = f'{key}-{year}.json'
            payload = json.dumps(points, separators=(',', ':'))
            (output / filename).write_text(payload)
            dataset['years'][str(year)] = {'file': '/data/' + filename, 'count': len(points), 'excluded': dropped, 'sourceRows': total, 'resourceId': resource['id'], 'resourceName': resource['name'], 'url': resource['url'], 'period': 'Full calendar year' if key == 'accidents' else 'Q4 inventory snapshot', 'sourceModified': resource.get('last_modified'), 'sourceSha256': hashlib.sha256(raw).hexdigest(), 'sha256': hashlib.sha256(payload.encode()).hexdigest()}
            print(f'{key} {year}: {len(points):,} points, {dropped} excluded', flush=True)
        manifest['datasets'][key] = dataset
    # Publish manifest only when every source has imported successfully.
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
