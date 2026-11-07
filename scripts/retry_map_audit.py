"""Retry temporary upload/network failures after the mirror has progressed."""
import concurrent.futures
import json
from scripts.audit_map_catalog import ROOT, audit

def main():
    catalog=json.loads((ROOT/'catalog.json').read_text())
    resources={r['id']:{**r,'_dataset_id':d['id']} for d in catalog['datasets'] for r in d['resources']}
    pending=[]
    for path in (ROOT/'resources').glob('*/result.json'):
        result=json.loads(path.read_text())
        if result.get('complete') and any(c['status']=='failed' and any(word in c.get('error','').lower() for word in ('not yet available','temporarily unreachable','temporarily unavailable')) for c in result['cases']):
            path.replace(path.with_name('before-upload-retry.json'))
            pending.append(resources[result['resource']])
    print(f'Retrying {len(pending)} temporary failures',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for rid,status in pool.map(audit,pending):print(rid,status,flush=True)

if __name__=='__main__':main()
