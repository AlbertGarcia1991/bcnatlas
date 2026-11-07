"""Resume a bounded audit of every map resource; no production data is deleted."""
import concurrent.futures
import gzip
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from server import storage

ROOT = storage.ROOT/'.cache/map-audit'

def audit(resource):
    dest=ROOT/'resources'/resource['id']; dest.mkdir(parents=True,exist_ok=True)
    result=dest/'result.json'
    if result.exists() and json.loads(result.read_text()).get('complete'): return resource['id'],'cached'
    if result.exists(): result.unlink()
    try:
        process=subprocess.Popen([str(storage.ROOT/'.venv/bin/python'),'-m','scripts.audit_map_resource'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
        first=True; started=time.time()
        while True:
            try:
                stdout,stderr=process.communicate(input=json.dumps(resource) if first else None,timeout=5)
                break
            except subprocess.TimeoutExpired:
                first=False
                try: stage=json.loads((dest/'stage.json').read_text())
                except Exception: stage={'started':started}
                if time.time()-max(started,stage['started'])>120:
                    process.kill();process.communicate()
                    raise TimeoutError('Production 120-second processing deadline exceeded during '+stage.get('stage','startup'))
        if process.returncode:
            message=json.loads(stdout.splitlines()[-1]).get('error','Parser exited unexpectedly') if stdout.strip() else 'Parser exited unexpectedly'
            raise RuntimeError(message)
        return resource['id'],'audited'
    except Exception as e:
        try: partial=json.loads(result.read_text())
        except Exception: partial={'resource':resource['id'],'dataset':resource['_dataset_id'],'cases':[]}
        try: stage=json.loads((dest/'stage.json').read_text())
        except Exception: stage={}
        partial['cases'].append({'member':stage.get('member'),'year':stage.get('year'),'status':'failed','error':str(e)[:500]+'; dependent untested choices are hidden'})
        partial.update(complete=True,aborted=True)
        result.write_text(json.dumps(partial))
        return resource['id'],'failed'

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    catalog=storage.catalog()
    (ROOT/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False))
    if not (ROOT/'reference.json.gz').exists():
        (ROOT/'reference.json.gz').write_bytes(storage.object_bytes(storage.public_bucket(),storage.SPATIAL_REFERENCE_KEY,24*1024*1024)[0])
    datasets=[d for d in catalog['datasets'] if d.get('mapMethods') and any(r['previewSupported'] for r in d['resources'])]
    # Newest editions first across datasets, then historical editions, for early useful evidence.
    resources=[]
    for index in range(max(len(d['resources']) for d in datasets)):
        for d in datasets:
            if index<len(d['resources']) and d['resources'][index]['previewSupported']:
                resources.append({**d['resources'][index],'_dataset_id':d['id']})
    started=time.monotonic()
    print(f'Auditing {len(datasets)} datasets / {len(resources)} resource files',flush=True)
    done=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(audit,r) for r in resources]
        for future in concurrent.futures.as_completed(futures):
            rid,status=future.result();done+=1
            (ROOT/'progress.tmp').write_text(json.dumps({'done':done,'total':len(resources),'elapsedSeconds':round(time.monotonic()-started),'updatedAt':datetime.now(timezone.utc).isoformat()}))
            (ROOT/'progress.tmp').replace(ROOT/'progress.json')
            if done%25==0: print(f'{done}/{len(resources)} resources; {round(time.monotonic()-started)}s',flush=True)
    print('Parser audit complete',flush=True)

if __name__=='__main__':main()
