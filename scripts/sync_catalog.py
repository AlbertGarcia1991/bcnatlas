"""Snapshot the complete public CKAN catalog; no dataset resources are downloaded."""
import json
import re
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = {'CSV', 'JSON', 'GEOJSON', 'ZIP', 'GPKG', 'XLSX', 'XML', 'KML', 'KMZ'}
def build(packages):
    datasets = []
    for d in packages:
        resources = []
        for r in d['resources']:
            years = sorted(set(re.findall(r'(?<!\d)((?:19|20)\d{2})(?!\d)', r.get('name', ''))))
            resources.append({'id': r['id'], 'name': r.get('name') or r['id'], 'format': r.get('format', ''), 'url': r['url'], 'modified': r.get('last_modified'), 'size': r.get('size'), 'years': years, 'previewSupported': r.get('format', '').upper() in SUPPORTED})
        datasets.append({'id': d['name'], 'title': d.get('title_translated', {}).get('en') or d.get('title', d['name']), 'description': d.get('notes_translated', {}).get('en') or d.get('notes', ''), 'geographic': str(d.get('geolocation','')).startswith('Yes'), 'license': d.get('license_title') or 'See source license', 'licenseUrl': d.get('license_url') or '', 'publisher': 'Ajuntament de Barcelona', 'author': d.get('author') or '', 'category': (d.get('organization') or {}).get('title') or '', 'url': 'https://opendata-ajuntament.barcelona.cat/data/en/dataset/' + d['name'], 'tags': [t['name'] for t in d.get('tags', []) if not re.match(r'Any \d', t['name'])], 'modified': d.get('metadata_modified'), 'resources': resources})
    return {'retrievedAt': datetime.now(timezone.utc).isoformat(), 'count': len(datasets), 'resourceCount': sum(len(d['resources']) for d in datasets), 'geographicCount': sum(d['geographic'] for d in datasets), 'datasets': datasets}
def main():
    if '--cached' in sys.argv:
        packages = json.loads((ROOT / '.cache/catalog.json').read_text())
    else:
        packages = []
        start = 0
        while True:
            url = f'https://opendata-ajuntament.barcelona.cat/data/api/action/package_search?rows=100&start={start}&sort=name+asc'
            with urllib.request.urlopen(url, timeout=60) as r: page = json.load(r)['result']
            packages.extend(page['results'])
            start += len(page['results'])
            if start >= page['count']: break
            if not page['results']: raise RuntimeError('Incomplete catalog pagination')
        if len({p['name'] for p in packages}) != page['count']: raise RuntimeError('Catalog changed during pagination; retry')
        (ROOT / '.cache').mkdir(exist_ok=True)
        (ROOT / '.cache/catalog.json').write_text(json.dumps(packages))
    catalog = build(packages)
    dest = ROOT / 'public/data/catalog.json'
    dest.with_suffix('.tmp').write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')))
    dest.with_suffix('.tmp').replace(dest)
    print(f"Indexed {catalog['count']} datasets / {catalog['resourceCount']} resources / {catalog['geographicCount']} marked geographic")
if __name__ == '__main__': main()
