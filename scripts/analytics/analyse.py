"""Publish a versioned, reproducible cross-layer statistical evidence bundle."""
import collections,gzip,hashlib,itertools,json,math,os,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from scipy import stats
from scripts.analytics.statistics import *
from scripts.analytics.extract import CACHE,ROOT,AREAS,AREA_KM2,PROJECT,POLYS,locate,CATALOG,AUDIT
from server import storage
OUT=CACHE/'published'

def write(name,value):
    path=OUT/name;path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False))
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]

def curated():
    manifest=json.loads(storage.asset('manifest.json')[0]);out=[]
    for layer,d in manifest['datasets'].items():
      for year,snapshot in d['years'].items():
        raw=storage.asset(snapshot['file'].split('/')[-1])[0]
        # The provenance hash describes the original source; prepared points are
        # independently checked for count, finite coordinates and area assignment.
        points=json.loads(raw)
        if len(points)!=snapshot['count']:raise ValueError('Curated count mismatch')
        for kind,index in [('neighbourhood',0),('district',1)]:
          counts=np.zeros(len(AREAS[kind]))
          for p in points:
            place=locate({}, {'type':'Point','coordinates':p[:2]})[index]
            if place is not None:counts[place]+=1
          out.append({'dataset':'curated-'+layer,'datasetTitle':d['title'],'category':'Urban Nature' if 'trees' in layer else 'Mobility','resource':snapshot['resourceId'],'resourceName':snapshot['resourceName'],'resourceUrl':snapshot['url'],'datasetUrl':d['url'],'license':d['license'],'sha256':snapshot['sha256'],'member':None,'year':int(year),'dateBasis':'curated snapshot','sourceRows':snapshot['sourceRows'],'unmappedRows':snapshot['excluded'],'retrievedAt':manifest['retrievedAt'],'field':('Recorded trees' if 'trees' in layer else 'Recorded accidents')+' / km²','stratum':{},'areaLevel':kind,'aggregation':'Prepared mapped records / land area (km²); Q4 inventory for trees','values':(counts/AREA_KM2[kind]).tolist(),'counts':counts.astype(int).tolist(),'inferenceEligible':True,'limitation':'Tree counts are not canopy cover; accident counts are not exposure-adjusted risk','series':layer})
    return out

def requires_dictionary(field):
    import re
    n=re.sub('[^a-z0-9]','',field.lower())
    return n in {'f0','f2','cntnom','demrefon','dif1','dif2','dif3','dif4','dif1716','enter','exc','literal','niveson','pesaix','pesmos','rec_cp1','reccp1','tobreak','v39abcdem','valoritz1','valoritzac','vol','zua','act2018','actjulds18','adultbrk','cosocial','empilla','nivbarri','norm','oc','prioritat','vulbrk','bd om','bdom','bind','alqsumren','alqren16','alqren17','numeropuntcritic'} or bool(re.fullmatch(r'p\d+(?:\d+)?',n)) or n.startswith('estat')

def family(dataset):
    return {'curated-accidents':'accidents-gu-bcn','curated-street-trees':'arbrat-viari','curated-park-trees':'arbrat-parcs'}.get(dataset,dataset)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    variables=[];inventory=[];cases=[];sparse=0;dedup={};duplicates=0
    for path in sorted((CACHE/'resources-v2').glob('*.json')):
        payload=json.loads(path.read_text());inventory.append({'dataset':payload['dataset'],'resource':payload['resource'],'fields':payload['fields'],'cases':payload['cases'],'sparseVariables':payload['sparseVariables']});sparse+=payload['sparseVariables'];cases+=payload['cases'];variables+=payload['variables']
    variables+=curated()
    for v in variables:
        key=digest([v['dataset'],v['field'],v['stratum'],v['year'],v['areaLevel'],v['values']])
        if key in dedup:dedup[key]['duplicateResources'].append(v['resource']);duplicates+=1;continue
        v['id']=key;v['duplicateResources']=[];v['aggregation']=v['aggregation'].replace('land area','municipal boundary area');v['seriesId']=digest([v['dataset'],v['series'],v['member'],v['field'],v['stratum'],v['areaLevel']])
        finite=np.array([x for x in v['values'] if x is not None]);unique=len(np.unique(finite))
        v['n']=len(finite);v['uniqueValues']=unique
        v['comparisonEligible']=bool(unique>=2 and len(finite)>=(MIN_AREAS if v['areaLevel']=='neighbourhood' else 8))
        v['summary']={'median':float(np.median(finite)),'min':float(finite.min()),'max':float(finite.max())} if len(finite) else None
        unclear=requires_dictionary(v['field'])
        if unclear:v['inferenceEligible']=False;v['limitation']='Numeric code with unresolved definition or units; requires a source dictionary'
        v['testable']=bool(v['inferenceEligible'] and v['dateBasis']!='undated' and v['areaLevel']=='neighbourhood' and v['n']>=MIN_AREAS and unique>=5)
        v['eligibilityReason']='Spatial inference eligible' if v['testable'] else 'Undated: no aligned observation year' if v['dateBasis']=='undated' else 'Only 10 districts: descriptive comparison' if v['areaLevel']=='district' else 'Too few areas or distinct values' if v['n']<MIN_AREAS or unique<5 else v['limitation'] or 'Unresolved coded strata: descriptive only'
        dedup[key]=v
    variables=sorted(dedup.values(),key=lambda v:(str(v['year']),v['areaLevel'],v['dataset'],v['field'],str(v['stratum'])))
    # Keep constant/sparse variables in the inventory, not the association family.
    usable=[v for v in variables if v['uniqueValues']>=2 and v['n']>=(30 if v['areaLevel']=='neighbourhood' else 8)]
    print(f'{len(variables)} variables; {len(usable)} nonconstant; {sum(v["testable"] for v in variables)} inference eligible',flush=True)
    areas=json.loads((CACHE/'areas.json').read_text())
    buckets=collections.defaultdict(list)
    for i,v in enumerate(usable):v['index']=i;buckets[(v['year'],v['areaLevel'])].append(v)
    variable_set=digest([v['id'] for v in usable])
    metadata={};all_p=[];p_locations=[];results={}
    for (year,level),vs in sorted(buckets.items(),key=lambda kv:str(kv[0])):
        label=f'{year or "undated"}-{level}';coords=np.array([a['centroid'] for a in areas[level]]);districts=np.array([a['district'] for a in areas[level]])
        checkpoint=CACHE/f'pairs-{label}.json'
        if checkpoint.exists() and json.loads(checkpoint.read_text()).get('variableSet')==variable_set:
            saved=json.loads(checkpoint.read_text());results[label]=saved['rows'];metadata[label]=saved['meta']
            for k,row in enumerate(saved['rows']):
                if not usable[row[0]]['testable'] or not usable[row[1]]['testable']:row[6]=None;row[7]=None
                if row[6] is not None:all_p.append(row[6]);p_locations.append((label,k))
            metadata[label]['spatialTests']=sum(row[6] is not None for row in saved['rows'])
            print(f'{label}: cached',flush=True);continue
        arrays=np.array([[np.nan if x is None else x for x in v['values']] for v in vs])
        density=next((arrays[i] for i,v in enumerate(vs) if v['dataset']=='est-densitat' and v['field']=='Densitat (hab/ha)' and not v['stratum']),None)
        rows=[];groups=collections.defaultdict(list);vector_cache={};control_cache={}
        def transformed(i,mask):
            key=(i,mask.tobytes())
            if key not in vector_cache:
                raw=arrays[i,mask];unique=len(np.unique(raw));rank=standardized(raw,True);plain=standardized(raw)
                partial=None
                if level=='neighbourhood' and len(raw)>=MIN_AREAS:
                    mk=mask.tobytes()
                    if mk not in control_cache:
                        ds=districts[mask];c=np.column_stack([np.ones(len(ds)),*[ds==g for g in np.unique(ds)[1:]]])
                        if density is not None and np.isfinite(density[mask]).all():c=np.column_stack([c,stats.rankdata(density[mask])])
                        control_cache[mk]=np.eye(len(ds))-c@np.linalg.pinv(c)
                    residual=control_cache[mk]@rank
                    if np.linalg.norm(residual)>1e-9:partial=residual/np.linalg.norm(residual)
                vector_cache[key]=(rank,plain,partial,unique)
            return vector_cache[key]
        for i,j in itertools.combinations(range(len(vs)),2):
            if family(vs[i]['dataset'])==family(vs[j]['dataset']):continue
            mask=np.isfinite(arrays[i])&np.isfinite(arrays[j]);n=int(mask.sum())
            if n<(MIN_AREAS if level=='neighbourhood' else 8):continue
            rx,px,ax,ux=transformed(i,mask);ry,py,ay,uy=transformed(j,mask)
            if min(ux,uy)<2:continue
            rho=float(rx@ry);pearson=float(px@py);partial=float(ax@ay) if ax is not None and ay is not None else None
            row=[vs[i]['index'],vs[j]['index'],n,round(rho,6),round(pearson,6),None if partial is None else round(partial,6),None,None]
            k=len(rows);rows.append(row)
            if vs[i]['testable'] and vs[j]['testable'] and n>=MIN_AREAS and min(ux,uy)>=5:
                groups[tuple(np.flatnonzero(mask))].append((k,i,j))
        print(f'{label}: {len(vs)} variables / {len(rows)} cross-layer comparisons / {sum(map(len,groups.values()))} spatial tests',flush=True)
        for indices,entries in groups.items():
            idx=np.array(indices)
            for start in range(0,len(entries),256):
                batch=entries[start:start+256]
                x=np.column_stack([arrays[i,idx] for _,i,j in batch]);y=np.column_stack([arrays[j,idx] for _,i,j in batch])
                ps=spatial_pvalues(x,y,coords[idx],seed=SEED+sum(indices))
                for (k,_,_),p in zip(batch,ps):rows[k][6]=float(p);all_p.append(float(p));p_locations.append((label,k))
        metadata[label]={'year':year,'areaLevel':level,'variables':len(vs),'comparisons':len(rows),'spatialTests':sum(map(len,groups.values())),'controls':'District fixed effects + population-density rank' if density is not None else 'District fixed effects'}
        results[label]=rows
        checkpoint.write_text(json.dumps({'rows':rows,'meta':metadata[label],'variableSet':variable_set},separators=(',',':')))
    if all_p:
        adjusted=stats.false_discovery_control(np.array(all_p),method='by')
        for (label,k),q in zip(p_locations,adjusted):results[label][k][7]=float(q)
    diagnostics={};summaries={}
    for label,rows in results.items():
        # Rank evidence first, then effect magnitude; no forced discoveries.
        ordered=sorted(rows,key=lambda r:(r[7] if r[7] is not None else 2,-abs(r[3]),-r[2]))
        candidates=[r for r in ordered if r[2]>=MIN_AREAS and r[6] is not None]
        display=candidates[:200] if candidates else ordered[:200]
        for row in candidates[:12]:
            a,b=usable[row[0]],usable[row[1]];x=np.array(a['values'],dtype=float);y=np.array(b['values'],dtype=float);mask=np.isfinite(x)&np.isfinite(y);x=x[mask];y=y[mask]
            ds=np.array([area['district'] for area in areas[a['areaLevel']]])[mask]
            loo=[]
            for i in range(len(x)):
                z=standardized(np.delete(np.column_stack([x,y]),i,axis=0),True);loo.append(float(z[:,0]@z[:,1]))
            w=weights(np.array([area['centroid'] for area in areas[a['areaLevel']]])[mask])
            diagnostics[f'{row[0]}:{row[1]}']={'blockCI':cluster_interval(x,y,ds),'leaveOneOutRange':[min(loo),max(loo)],'moranX':moran(stats.rankdata(x),w),'moranY':moran(stats.rankdata(y),w),'blocks':len(np.unique(ds))}
        shards=collections.defaultdict(list)
        for row in rows:shards[row[0]%32].append(row)
        for shard,values in shards.items():write(f'pairs/{label}-{shard}.json',values)
        write(f'variables/{label}.json',[v for v in usable if v['year']==metadata[label]['year'] and v['areaLevel']==metadata[label]['areaLevel']])
        metadata[label]['shards']=list(shards);metadata[label]['supported']=sum(r[7] is not None and r[7]<=.05 for r in rows)
        summaries[label]=display
    # Full field-by-field coverage, including every rejected identifier/constant.
    with gzip.open(OUT/'variable-inventory.json.gz','wt') as f:json.dump(inventory,f,ensure_ascii=False,separators=(',',':'))
    with gzip.open(OUT/'variables.json.gz','wt') as f:json.dump(variables,f,ensure_ascii=False,separators=(',',':'))
    write('diagnostics.json',diagnostics);write('top-associations.json',summaries)
    write('manifest.json',{'version':1,'generatedAt':datetime.now(timezone.utc).isoformat(),'auditSha256':hashlib.sha256((ROOT/'config/map-render-audit.json').read_bytes()).hexdigest(),'catalogSha256':hashlib.sha256((ROOT/'.cache/map-audit/catalog.json').read_bytes()).hexdigest(),'seed':SEED,'permutations':PERMUTATIONS,'minAreas':MIN_AREAS,'fdrMethod':'Benjamini–Yekutieli, one global family across all tested years and cross-layer pairs','counts':{'datasets':len({i['dataset'] for i in inventory}),'resources':len(inventory),'editions':len(cases),'failedEditions':sum(c['status']=='excluded' for c in cases),'fieldsScreened':sum(len(i['fields']) for i in inventory),'derivedVariables':len(variables),'usableVariables':len(usable),'sparseStrataExcluded':sparse,'duplicateVariables':duplicates,'comparisons':sum(len(r) for r in results.values()),'spatialTests':len(all_p),'supported':int(np.sum(adjusted<=.05)) if all_p else 0},'areas':areas,'periods':metadata,'datasetCoverage':[{'dataset':i['dataset'],'resource':i['resource'],'fields':len(i['fields']),'cases':i['cases'],'sparseVariables':i['sparseVariables']} for i in inventory],'sources':[{'title':'Moran spectral randomization — Wagner & Dray (2015)','url':'https://doi.org/10.1111/2041-210X.12407'},{'title':'SciPy multiple-testing adjustment','url':'https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.false_discovery_control.html'},{'title':'Spearman rank correlation','url':'https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html'}]})
    print('Published analytics bundle',flush=True)
if __name__=='__main__':main()
