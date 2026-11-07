"""Remove only explicitly reviewed datasets from the mirror; default is a dry run.

Stop the mirror supervisor/transfer first. The apply operation takes its lock,
updates catalogs and transfer plans before deletion, verifies R2 deletions, and
records the exact deleted keys. Unknown/failed schema probes are never deleted.
"""
import argparse
import csv
import fcntl
import hashlib
import io
import json
from datetime import datetime, timezone
from server import storage
from scripts.curate_catalog import curate
from scripts.r2_assets import put_verified
from scripts.r2_verify import atomic_write, verify

def objects(bucket, prefix):
    for page in storage.client().get_paginator('list_objects_v2').paginate(Bucket=bucket, Prefix=prefix):
        yield from page.get('Contents', [])

def plan(catalog, exclusions):
    datasets = [d for d in catalog['datasets'] if d['id'] in exclusions]
    resource_ids = {r['id'] for d in datasets for r in d['resources']}
    raw = [obj['Key'] for d in datasets for obj in objects(storage.raw_bucket(), f'{storage.raw_prefix()}/raw/{d["id"]}/')]
    processed = [o['Key'] for o in objects(storage.public_bucket(), 'processed/') if len(o['Key'].split('/')) == 4 and o['Key'].split('/')[2] in resource_ids]
    return {'datasets': [d['id'] for d in datasets], 'resources': sorted(resource_ids), 'rawKeys': raw, 'processedKeys': processed}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    folder = storage.ROOT / '.cache/r2-mirror'
    exclusions = json.loads((storage.ROOT / 'config/catalog-exclusions.json').read_text())
    # Retained metadata makes interrupted cleanup resumable; no source data is
    # copied into backups. Every deletion is confined to this reviewed list.
    backup = folder / 'catalog-before-spatial-curation.json'
    catalog = json.loads((backup if backup.exists() else folder / 'catalog.json').read_text())
    report = plan(catalog, exclusions)
    report['plannedAt'] = datetime.now(timezone.utc).isoformat()
    atomic_write(folder / 'nonspatial-removal-plan.json', json.dumps(report, indent=2).encode())
    print({k: len(report[k]) for k in ('datasets', 'resources', 'rawKeys', 'processedKeys')}, flush=True)
    if not args.apply: return
    with (folder / 'mirror.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit('Stop the mirror supervisor and transfer before pruning.')
        if not backup.exists(): atomic_write(backup, json.dumps(catalog).encode())
        curated = curate(catalog)
        raw_catalog = json.dumps(curated, ensure_ascii=False, separators=(',', ':')).encode()
        for path in (folder / 'catalog.json', storage.ROOT / 'public/data/catalog.json'):
            atomic_write(path, raw_catalog)
        for path in [folder / 'resources.csv', folder / 'missing-resources.csv', *folder.glob('pass-*.csv')]:
            with path.open(newline='') as source: rows = list(csv.reader(source))
            rows = [r for r in rows if len(r) == 2 and r[1].split('/')[1] not in exclusions]
            output = io.StringIO(newline=''); csv.writer(output).writerows(rows)
            atomic_write(path, output.getvalue().encode())
        put_verified(storage.public_bucket(), f'{storage.app_prefix()}/data/catalog.json', raw_catalog)
        put_verified(storage.raw_bucket(), f'{storage.raw_prefix()}/catalog.json', raw_catalog)
        for bucket, keys in [(storage.raw_bucket(), report['rawKeys']), (storage.public_bucket(), report['processedKeys'])]:
            for start in range(0, len(keys), 1000):
                response = storage.client().delete_objects(Bucket=bucket, Delete={'Objects': [{'Key': k} for k in keys[start:start+1000]], 'Quiet': True})
                if response.get('Errors'): raise RuntimeError('Some storage deletions failed; inspect the removal plan and retry.')
        remaining = plan(catalog, exclusions)
        if remaining['rawKeys'] or remaining['processedKeys']: raise RuntimeError('Excluded objects remain; cleanup must be retried.')
        for d in catalog['datasets']:
            if d['id'] not in exclusions: continue
            for r in d['resources']:
                key = hashlib.sha256((r['id'] + str(r.get('modified'))).encode()).hexdigest()
                (storage.ROOT / '.cache/resources' / key).unlink(missing_ok=True)
        report['completedAt'] = datetime.now(timezone.utc).isoformat()
        atomic_write(folder / 'nonspatial-removal-result.json', json.dumps(report, indent=2).encode())
        verify()
        print('Verified removal of reviewed non-spatial datasets.', flush=True)

if __name__ == '__main__': main()
