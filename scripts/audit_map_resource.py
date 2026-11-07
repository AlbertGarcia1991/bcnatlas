"""Isolated production-parser audit of one resource and every member/record year."""
import gzip
import gc
import hashlib
import json
import math
import os
import signal
import resource as limits
import sys
import time
from pathlib import Path
from server import loader, spatial, storage


def timeout(*_): raise TimeoutError('Production 120-second processing deadline exceeded')
signal.signal(signal.SIGALRM, timeout)

def main():
    limits.setrlimit(limits.RLIMIT_AS,(2*1024**3,2*1024**3))
    resource = json.load(sys.stdin)
    root = storage.ROOT / '.cache/map-audit'
    dest = root / 'resources' / resource['id']; dest.mkdir(parents=True, exist_ok=True)
    def stage(name, member=None, year=None, credit=0):
        (dest/'stage.json').write_text(json.dumps({'started':time.time()-credit,'stage':name,'member':member,'year':year}))
    result = {'resource':resource['id'], 'dataset':resource['_dataset_id'], 'cases':[]}
    # Same immutable reference as production, downloaded once for this audit.
    spatial.reference = lambda: reference
    reference = json.loads(gzip.decompress((root/'reference.json.gz').read_bytes()))
    signal.alarm(120)
    stage('download')
    began=time.monotonic();cpu_began=time.process_time()
    raw, retrieved = loader.fetch_resource(resource)
    download_seconds=time.monotonic()-began
    download_cpu=time.process_time()-cpu_began
    signal.alarm(0)
    result['sha256'] = hashlib.sha256(raw).hexdigest()
    original = loader.read_rows
    pending = [None]; seen = set()
    while pending:
        member = pending.pop(0)
        if member in seen: continue
        seen.add(member)
        try:
            signal.alarm(120)
            stage('read',member)
            began=time.monotonic();cpu_began=time.process_time()
            parsed = original(raw, resource['format'], resource['name'], member)
            read_seconds=time.monotonic()-began
            read_cpu=time.process_time()-cpu_began
            signal.alarm(0)
            rows, _, members, chosen = parsed
            seen.add(chosen)
            pending.extend(m for m in members if m not in seen and m not in pending)
            loader.read_rows = lambda *args, **kwargs: parsed
            fields = set()
            flat = []
            for row in rows:
                if not isinstance(row,dict): continue
                row = loader.flatten(row.get('properties') or {}) if row.get('type')=='Feature' else loader.flatten({k:v for k,v in row.items() if k!='_geometry'})
                fields.update(row); flat.append(row)
            normalized = {loader.norm(k): k for k in fields}
            yearfield = next((normalized[k] for k in ['any','year','nkany','anydata'] if k in normalized),None)
            import re
            years = sorted({str(r.get(yearfield)) for r in flat if yearfield and re.fullmatch(r'(19|20)\d{2}',str(r.get(yearfield)))})
            del flat
            for year in [None, *years]:
                case = {'member':chosen, 'year':year}
                try:
                    signal.alarm(120)
                    credit=download_seconds+read_seconds
                    signal.alarm(max(1,math.ceil(120-credit)))
                    stage('prepare',chosen,year,credit)
                    began=time.monotonic();cpu_began=time.process_time()
                    data = loader.prepare(raw,resource,chosen,year)
                    data.update(retrievedAt=retrieved, storageSource='Cloudflare R2')
                    case.update(fields=data['fields'],rows=data['totalRows'],unmapped=data['withoutGeometry'],excluded=data['excluded'])
                    if not data['mappedCount']: raise ValueError('No recognized map locations (zero mapped features)')
                    # Serialization is also a production requirement; reject NaN/Infinity.
                    payload = json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
                    if len(payload)>48*1024*1024: raise ValueError('Prepared preview exceeds the 48 MiB cached response limit')
                    identity = hashlib.sha256(json.dumps([chosen,year]).encode()).hexdigest()[:16]
                    with gzip.open(dest/(identity+'.json.gz'),'wb') as f: f.write(payload)
                    seconds=credit+time.monotonic()-began
                    if seconds>120: raise TimeoutError('Production 120-second combined processing deadline exceeded')
                    cpu_seconds=download_cpu+read_cpu+time.process_time()-cpu_began
                    if cpu_seconds>100:raise TimeoutError('Production 100-second parser CPU limit exceeded')
                    case.update(seconds=round(seconds,3),cpuSeconds=round(cpu_seconds,3),status='parsed', payload=str(dest/(identity+'.json.gz')), features=data['mappedCount'],
                                metrics=data['numericFields'], filters=data.get('filterOptions',[]), geometryTypes=data['geometryTypes'])
                except Exception as e: case.update(status='failed',error=f'{type(e).__name__}: {str(e)[:500]}')
                finally:
                    signal.alarm(0)
                    data=None; payload=None
                    gc.collect()
                result['cases'].append(case)
                (dest/'result.json').write_text(json.dumps(result,ensure_ascii=False))
        except Exception as e:
            result['cases'].append({'member':member,'year':None,'status':'failed','error':f'{type(e).__name__}: {str(e)[:500]}'})
        finally:
            signal.alarm(0); loader.read_rows = original
    result['complete'] = True
    (dest/'result.json').write_text(json.dumps(result,ensure_ascii=False))
    print(json.dumps({'resource':resource['id'],'cases':len(result['cases'])}))

if __name__ == '__main__':
    try: main()
    except Exception as e:
        print(json.dumps({'error':f'{type(e).__name__}: {str(e)[:500]}'}))
        sys.exit(1)
