"""Audit category combinations; exhaustive small spaces and explicit large-space samples."""
import concurrent.futures
import hashlib
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from scripts.audit_map_catalog import ROOT
from server import storage

EXHAUSTIVE_LIMIT=64

def usable_baseline(case):
    file=Path(case['payload'].replace('.json.gz','.render.json'))
    if not file.exists():return False
    checked=json.loads(file.read_text())
    checks=checked.get('checks',[])
    geometry=any(c['status']=='passed' and c['render']=='geometry' and not c.get('metric') for c in checks)
    metric=not case['metrics'] or any(c['status']=='passed' and c.get('metric') for c in checks)
    return geometry and metric and not checked.get('error')

def combinations(options):
    # Count legal requests exactly, including an unselected (All) option per field.
    options=[{'field':o['field'],'values':[v for v in o['values'] if v and len(v)<=500]} for o in options if len(o['field'])<=200]
    options=[o for o in options if o['values']]
    counts=[1]+[0]*12
    for option in options:
        n=len(option['values'])
        for size in range(12,0,-1):counts[size]+=counts[size-1]*n
    total=sum(counts)
    if total<=EXHAUSTIVE_LIMIT:
        candidates=({o['field']:v for o,v in zip(options,values) if v is not None} for values in itertools.product(*[[None,*o['values']] for o in options]))
        mode='exhaustive'
    else:
        mode='representative'; candidates=[{}]
        # Spread the sample across fields and values; never imply complete coverage.
        chosen=sorted(set(round(i*(len(options)-1)/min(11,len(options)-1)) for i in range(min(12,len(options))))) if len(options)>1 else [0]
        for index in chosen:
            o=options[index]
            candidates.extend([{o['field']:o['values'][0]},{o['field']:o['values'][-1]}])
        for index in chosen[:6]:
            pair=options[index:index+2]
            candidates.append({o['field']:o['values'][0] for o in pair})
        candidates.append({o['field']:o['values'][0] for o in options[:12]})
        candidates.append({o['field']:o['values'][-1] for o in options[-12:]})
    seen=set();result=[]
    for candidate in candidates:
        key=json.dumps(candidate,sort_keys=True,ensure_ascii=False,separators=(',',':'))
        if len(candidate)<=12 and len(key.encode('utf-16-le'))//2<=4096 and key not in seen:seen.add(key);result.append(candidate)
    return mode,total,result

def audit(resource):
    directory=ROOT/'resources'/resource['id'];dest=directory/'filters.json'
    while True:
        source=directory/'result.json'
        try: base=json.loads(source.read_text())
        except Exception: base={}
        parsed=[c for c in base.get('cases',[]) if c['status']=='parsed']
        if base.get('complete') and all(Path(c['payload'].replace('.json.gz','.render.json')).exists() for c in parsed):break
        time.sleep(2)
    eligible={(c['member'],c['year']) for c in parsed if usable_baseline(c)}
    if dest.exists():
        previous=json.loads(dest.read_text())
        if previous.get('complete') and {(c['member'],c['year']) for c in previous.get('cases',[])}==eligible and not previous.get('resourceError'):return
        dest.unlink()
    process=subprocess.Popen([str(storage.ROOT/'.venv/bin/python'),'-m','scripts.audit_map_filters','--worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
    first=True;started=time.time()
    try:
        while True:
            try:
                out,err=process.communicate(input=json.dumps(resource) if first else None,timeout=5);break
            except subprocess.TimeoutExpired:
                first=False
                try: stage=json.loads((directory/'filter-stage.json').read_text())
                except Exception:stage={'started':started}
                if time.time()-max(started,stage['started'])>120:
                    process.kill();process.communicate();raise TimeoutError('Filter processing exceeded the 120-second deadline')
        if process.returncode:raise RuntimeError(out[-500:] or 'Filter worker stopped unexpectedly')
    except Exception as e:
        try:result=json.loads(dest.read_text())
        except Exception:result={'cases':[]}
        result.update(complete=True,resourceError=str(e),status='failed')
        dest.write_text(json.dumps(result,ensure_ascii=False))

def worker(resource):
    import gc,gzip,resource as limits,signal
    from server import loader,spatial
    limits.setrlimit(limits.RLIMIT_AS,(2*1024**3,2*1024**3))
    def expired(*_):raise TimeoutError('Filter processing exceeded the 120-second deadline')
    signal.signal(signal.SIGALRM,expired)
    directory=ROOT/'resources'/resource['id'];dest=directory/'filters.json'
    record=json.loads((directory/'result.json').read_text());result={'cases':[]}
    base_cases=[]
    for case in record['cases']:
        if case['status']!='parsed':continue
        if usable_baseline(case):base_cases.append(case)
    def save():dest.write_text(json.dumps(result,ensure_ascii=False))
    if not base_cases:result.update(complete=True);save();return
    def stage(name,credit=0):
        (directory/'filter-stage.json').write_text(json.dumps({'started':time.time()-credit,'stage':name}))
        signal.alarm(max(1,int(120-credit)))
    if all(not c.get('filters') for c in base_cases):
        result['cases']=[{'member':c['member'],'year':c['year'],'status':'passed','mode':'exhaustive','totalCombinations':'1','checks':[{'filters':{},'status':'baseline'}]} for c in base_cases]
        result.update(complete=True);save();return
    stage('download');began=time.monotonic();cpu_began=time.process_time();raw,retrieved=loader.fetch_resource(resource);download_seconds=time.monotonic()-began;download_cpu=time.process_time()-cpu_began
    reference=json.loads(gzip.decompress((ROOT/'reference.json.gz').read_bytes()));spatial.reference=lambda:reference
    original=loader.read_rows;cached_member=object();parsed=None;flat=[];masks={};payload_cache={}
    for case in base_cases:
        entry={'member':case['member'],'year':case['year'],'status':'running','checks':[]};result['cases'].append(entry);save()
        if not case.get('filters'):
            entry.update(status='passed',mode='exhaustive',totalCombinations='1',checks=[{'filters':{},'status':'baseline'}]);save();continue
        mode,total,variants=combinations(case['filters'])
        needed={key for filters in variants for key in filters}
        if cached_member!=case['member']:
            stage('read');began=time.monotonic();cpu_began=time.process_time();parsed=original(raw,resource['format'],resource['name'],case['member']);read_seconds=time.monotonic()-began;read_cpu=time.process_time()-cpu_began
            cached_member=case['member'];flat=[]
            for row in parsed[0]:
                if isinstance(row,dict):flat.append(loader.flatten(row.get('properties') or {}) if row.get('type')=='Feature' else loader.flatten({k:v for k,v in row.items() if k!='_geometry'}))
            fields=list(dict.fromkeys(key for row in flat for key in row))[:500];normalized={loader.norm(k):k for k in fields};yearfield=next((normalized[k] for k in ['any','year','nkany','anydata'] if k in normalized),None)
            masks={};payload_cache={}
            options=[o for o in case['filters'] if o['field'] in needed]
            buffers={(o['field'],v):bytearray((len(flat)+7)//8) for o in options for v in o['values']}
            values={}
            for i,row in enumerate(flat):
                offset=i>>3; bit=1<<(i&7)
                for option in options:
                    value=row.get(option['field']);cache_key=(type(value),value)
                    try:
                        if cache_key not in values:values[cache_key]=str(loader.scalar(value))
                        value=values[cache_key]
                    except TypeError:value=str(loader.scalar(value))
                    key=(option['field'],value)
                    if key in buffers:buffers[key][offset]|=bit
            masks={key:int.from_bytes(value,'little') for key,value in buffers.items()}
            del buffers,values
            signal.alarm(0)
        all_rows=(1<<len(flat))-1
        if case['year'] is not None:all_rows=sum(1<<i for i,row in enumerate(flat) if str(row.get(yearfield))==case['year'])
        mode,total,variants=combinations(case['filters']);entry.update(mode=mode,totalCombinations=str(total))
        loader.read_rows=lambda *args,**kwargs:parsed
        for filters in variants:
            check={'filters':filters}
            if not filters:check['status']='baseline';entry['checks'].append(check);continue
            selected=all_rows
            for key,value in filters.items():selected &= masks.get((key,value),0)
            if not selected:check.update(status='empty',selectedRows=0);entry['checks'].append(check);continue
            identity=hashlib.sha256(selected.to_bytes((selected.bit_length()+7)//8,'little')).hexdigest()[:20]
            if selected==all_rows:check.update(status='baseline-equivalent',selectedRows=selected.bit_count());entry['checks'].append(check);continue
            if identity in payload_cache:check.update(payload_cache[identity]);entry['checks'].append(check);continue
            try:
                credit=download_seconds+read_seconds;stage('prepare',credit);began=time.monotonic();cpu_began=time.process_time()
                data=loader.prepare(raw,resource,case['member'],case['year'],filters);data.update(retrievedAt=retrieved,storageSource='Cloudflare R2')
                if data['selectedRows']!=selected.bit_count():raise RuntimeError('Filter row-selection verification mismatch')
                if data['selectedRows'] and not data['mappedCount']:raise ValueError('Selected category records have no recognized map geometry')
                body=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
                if len(body)>48*1024*1024:raise ValueError('Filtered response exceeds the interactive response limit')
                payload=directory/('filter-'+hashlib.sha256(str(case['member']).encode()).hexdigest()[:8]+'-'+identity+'.json.gz')
                with gzip.open(payload,'wb') as stream:stream.write(body)
                if credit+time.monotonic()-began>120:raise TimeoutError('Combined filter processing exceeded the 120-second deadline')
                cpu_seconds=download_cpu+read_cpu+time.process_time()-cpu_began
                if cpu_seconds>100:raise TimeoutError('Production 100-second parser CPU limit exceeded')
                summary={'status':'parsed','payload':str(payload),'selectedRows':data['selectedRows'],'cpuSeconds':round(cpu_seconds,3)};payload_cache[identity]=summary;check.update(summary)
            except Exception as e:
                check.update(status='failed',error=f'{type(e).__name__}: {str(e)[:400]}');entry['status']='failed'
            finally:signal.alarm(0);data=None;body=None;gc.collect()
            entry['checks'].append(check);save()
            if entry['status']=='failed':break
        if entry['status']!='failed':entry['status']='passed'
        save();loader.read_rows=original
    result['complete']=True;save()

def main():
    catalog=json.loads((ROOT/'catalog.json').read_text());resources=[{**r,'_dataset_id':d['id']} for d in catalog['datasets'] if d.get('mapMethods') for r in d['resources'] if r['previewSupported']]
    pending=resources
    (ROOT/'filter-progress.json').write_text(json.dumps({'complete':False,'total':len(pending)}))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for index,_ in enumerate(pool.map(audit,pending)):
            if index%25==0:print(f'Filter resources {index+1}/{len(pending)}',flush=True)
    (ROOT/'filter-progress.json').write_text(json.dumps({'complete':True,'total':len(pending)}))
    print('Filter pass finished.',flush=True)

if __name__=='__main__':
    if '--worker' in sys.argv:
        try:worker(json.load(sys.stdin))
        except Exception as e:print(f'{type(e).__name__}: {str(e)[:400]}');sys.exit(1)
    else:main()
