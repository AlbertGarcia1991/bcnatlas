"""Compare the frozen transfer plan with R2 and write a resumable missing-only plan."""
import csv
import json
import io
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from server import storage


def atomic_write(path, raw):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(raw)
        name = temporary.name
    Path(name).replace(path)


def inventory():
    found={}
    prefix=storage.raw_prefix()+'/'
    for page in storage.client().get_paginator('list_objects_v2').paginate(Bucket=storage.raw_bucket(),Prefix=prefix+'raw/'):
        for obj in page.get('Contents',[]):found[obj['Key'][len(prefix):]]=obj
    return found


def verify(publish=True):
    folder=storage.ROOT/'.cache/r2-mirror'
    with (folder/'resources.csv').open(newline='') as f: plan=list(csv.reader(f))
    found=inventory();missing=[row for row in plan if row[1] not in found or found[row[1]]['Size']==0]
    output=io.StringIO(newline='');csv.writer(output).writerows(missing)
    atomic_write(folder/'missing-resources.csv',output.getvalue().encode())
    expected={row[1] for row in plan}
    catalog=json.loads((folder/'catalog.json').read_text())
    sizes={f'raw/{d["id"]}/{r["id"]}/source':int(r.get('size') or 0) for d in catalog['datasets'] for r in d['resources']}
    differences=[{'key':key,'catalogBytes':sizes.get(key,0),'uploadedBytes':obj['Size']} for key,obj in found.items() if key in expected and sizes.get(key,0)>0 and sizes[key]!=obj['Size']]
    report={'snapshot':storage.raw_prefix(),'checkedAt':datetime.now(timezone.utc).isoformat(),
            'plannedResources':len(plan),'uploadedResources':len(plan)-len(missing),'missingResources':len(missing),
            'uploadedBytes':sum(o['Size'] for key,o in found.items() if key in expected),'serviceReferences':len(json.loads((folder/'service-references.json').read_text())),
            'status':'complete' if not missing else 'in-progress','verification':'Object presence and nonzero size; catalog byte-size differences require source/content review.',
            'sizeDifferences':differences,'missing':[{'url':url,'key':key} for url,key in missing]}
    raw=json.dumps(report,indent=2).encode();atomic_write(folder/'verification.json',raw)
    if publish:
        storage.client().put_object(Bucket=storage.public_bucket(),Key=f'{storage.app_prefix()}/data/mirror-status.json',Body=raw,ContentType='application/json',CacheControl='public, max-age=60')
    print(json.dumps({k:v for k,v in report.items() if k not in ('missing','sizeDifferences')},indent=2),flush=True)
    print('Catalog size differences:',len(differences),flush=True)
    return report

if __name__=='__main__':verify()
