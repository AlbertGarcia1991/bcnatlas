"""Verify near-limit or early untimed editions with the complete production reader."""
import concurrent.futures
import json
import os
import subprocess
import time
from scripts.audit_map_catalog import ROOT
from server import storage


def needs_probe(case):
    return (case['status'] == 'parsed'
            and ('seconds' not in case or case['seconds'] > 90)
            and case.get('serviceProbe', {}).get('status') != 'passed')


def probe_resource(item):
    path, resource = item
    result = json.loads(path.read_text())
    backup = path.with_name('before-service-probe.json')
    if not backup.exists(): backup.write_text(path.read_text())
    checked = failed = 0
    for case in result['cases']:
        if not needs_probe(case): continue
        request = {'resource': resource, 'member': case['member'], 'year': case['year'], 'filters': {}}
        for attempt in range(2):
            started = time.monotonic()
            try:
                process = subprocess.run(
                    [str(storage.ROOT / '.venv/bin/python'), '-m', 'server.worker'],
                    input=json.dumps(request), capture_output=True, text=True, timeout=120,
                    cwd=storage.ROOT,
                    env={**os.environ, 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'},
                )
                if process.returncode:
                    raise RuntimeError(f'Production reader exited with code {process.returncode} under its 100-second CPU / 2 GiB memory limits')
                payload = json.loads(process.stdout)
                if payload.get('error'): raise RuntimeError(payload['error'])
                if not payload.get('mappedCount'): raise RuntimeError('Production reader returned no mapped features')
                if payload.get('sourceSha256') != result['sha256']:
                    raise RuntimeError('Production reader checksum differs from the audited source')
                probe = {'status': 'passed', 'seconds': round(time.monotonic() - started, 3), 'mappedCount': payload['mappedCount']}
                payload = None
            except Exception as error:
                probe = {'status': 'failed', 'seconds': round(time.monotonic() - started, 3), 'error': str(error)[:500]}
            if 'temporarily' not in probe.get('error', ''): break
        case['serviceProbe'] = probe
        checked += 1
        if probe['status'] == 'failed':
            case.update(status='failed', error='Production reader probe failed: ' + probe['error'])
            failed += 1
        temporary = path.with_suffix('.service-tmp')
        temporary.write_text(json.dumps(result, ensure_ascii=False))
        temporary.replace(path)
    return resource['id'], checked, failed


def main():
    catalog = json.loads((ROOT / 'catalog.json').read_text())
    lookup = {r['id']: {**r, '_dataset_id': d['id']} for d in catalog['datasets'] for r in d['resources']}
    pending = []
    for path in (ROOT / 'resources').glob('*/result.json'):
        if path.parent.name in lookup and any(needs_probe(c) for c in json.loads(path.read_text())['cases']):
            pending.append((path, lookup[path.parent.name]))
    print(f'Production reader probes: {len(pending)} resource files', flush=True)
    workers=max(1,min(4,int(os.environ.get('BCN_AUDIT_SERVICE_WORKERS','2'))))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for index, (rid, checked, failed) in enumerate(pool.map(probe_resource, pending)):
            print(f'{index + 1}/{len(pending)}: {rid}; checked={checked}; failed={failed}', flush=True)


if __name__ == '__main__': main()
