"""Inspect actual table schemas; cache evidence without changing the catalog or storage."""
import concurrent.futures
import csv
import io
import json
import urllib.request
from pathlib import Path
from server import storage
from server.loader import decode

DEST = storage.ROOT / '.cache/spatial/schemas.json'
MISSING = set()

def inspect(dataset):
    resources = [r for r in dataset['resources'] if r['format'].upper() == 'CSV']
    # Prefer a recent table. Every distinct schema is audited during final curation.
    if not resources:
        return dataset['id'], {'fields': [], 'status': 'no-csv'}
    resources.sort(key=lambda r: f'raw/{dataset["id"]}/{r["id"]}/source' in MISSING)
    resource = resources[0]
    key = storage.resource_key({**resource, '_dataset_id': dataset['id']})
    try:
        response = storage.client().get_object(Bucket=storage.raw_bucket(), Key=key, Range='bytes=0-65535')
        try: raw = response['Body'].read()
        finally: response['Body'].close()
        text = decode(raw[:len(raw) - len(raw) % 2])
        try: dialect = csv.Sniffer().sniff(text[:16384], delimiters=',;\t|')
        except csv.Error: dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        samples = []
        for _, row in zip(range(2), reader): samples.append(row)
        return dataset['id'], {'resource': resource['id'], 'fields': reader.fieldnames, 'samples': samples, 'status': 'inspected'}
    except Exception:
        try:
            url = 'https://opendata-ajuntament.barcelona.cat/data/api/action/datastore_search?resource_id=' + resource['id'] + '&limit=1'
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'BarcelonaAtlas/1.3'}), timeout=8) as response:
                result = json.load(response)['result']
            return dataset['id'], {'resource': resource['id'], 'fields': [f['id'] for f in result['fields']], 'samples': result['records'], 'status': 'inspected'}
        except Exception:
            return dataset['id'], {'resource': resource['id'], 'fields': [], 'status': 'unavailable'}

def main():
    global MISSING
    DEST.parent.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((storage.ROOT / 'public/data/catalog.json').read_text())
    evidence = json.loads(DEST.read_text()) if DEST.exists() else {}
    report = storage.ROOT / '.cache/r2-mirror/verification.json'
    if report.exists(): MISSING = {x['key'] for x in json.loads(report.read_text())['missing']}
    pending = [d for d in catalog['datasets'] if evidence.get(d['id'], {}).get('status') not in ('inspected','no-csv')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for index, (key, value) in enumerate(pool.map(inspect, pending)):
            evidence[key] = value
            DEST.write_text(json.dumps(evidence, ensure_ascii=False))
            if index % 25 == 0: print(f'Inspected {len(evidence)} datasets', flush=True)
    print('Saved schema evidence:', len(evidence), flush=True)

if __name__ == '__main__': main()
