"""Inventory every audited field and construct explicit, area-level variables.

No city totals are downscaled to neighbourhoods. Mixed-category map averages
are replaced by source-row strata. Missing measurements are never zero-filled.
"""
import collections, concurrent.futures, gzip, hashlib, json, os, re, unicodedata
from pathlib import Path
import numpy as np
from shapely.geometry import shape, Point
from shapely.ops import transform
from shapely.strtree import STRtree
from pyproj import Transformer
from server import loader, spatial, storage
ROOT=storage.ROOT
CACHE=ROOT/'.cache/analytics'
AUDIT=json.loads((ROOT/'config/map-render-audit.json').read_text())
CATALOG=json.loads((ROOT/'.cache/map-audit/catalog.json').read_text()) if (ROOT/'.cache/map-audit/catalog.json').exists() else {'datasets':[]}
REF=json.loads(gzip.decompress((ROOT/'.cache/map-audit/reference.json.gz').read_bytes())) if (ROOT/'.cache/map-audit/reference.json.gz').exists() else {'district':{},'neighbourhood':{},'names':{}}
PROJECT=Transformer.from_crs(4326,25831,always_xy=True).transform
AREAS={kind:[{'id':key,'name':v['name'],'district':int(v['district']), 'geometry':v['geometry']} for key,v in sorted(REF[kind].items(),key=lambda kv:int(kv[0]))] for kind in ('neighbourhood','district')}
POLYS={kind:[shape(a['geometry']) for a in areas] for kind,areas in AREAS.items()}
TREES={kind:STRtree(polys) for kind,polys in POLYS.items()}
INDEX={kind:{a['id']:i for i,a in enumerate(areas)} for kind,areas in AREAS.items()}
AREA_KM2={kind:np.array([transform(PROJECT,g).area/1e6 for g in polys]) for kind,polys in POLYS.items()}
GEOCACHE={}

def norm(value):return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',str(value)).encode('ascii','ignore').decode().lower())
def numeric(value):
    n=loader.numeric(value)
    return n if n is not None and abs(n)<1e15 else None

def role(field):
    n=norm(field)
    if field.startswith('_'):return 'processing metadata'
    if n in ('any','year','nkany','anydata') or re.fullmatch(r'\d{4}',field.strip()):return 'time axis; wide-year column needs reshaping' if n.isdigit() else 'time axis'
    if any(x in n for x in ('coordenad','etrs','ed50','latitud','longitudx','longitudy','geoep','geometr','shape','gisx','gisy')) or n in ('geom','wkt'):return 'geometry / coordinate'
    if n.startswith(('id','fid','objectid','codi','addresses','secondaryfilters','register','institution')) or n.endswith(('id','codi','code')) or any(x in n for x in ('telefon','postal','carrer','nomvia','nomdistr','nombarri','secc','district','zipcode','nomcient','nomcastella','nomcatala')) or n in ('cp','cbarri','cdistri','nkbarri','dte','dtenum','barnum','num1','num2','porta','pis','poligon','zona','terme','illa','gridcode','ngis','codi','numvia','num','nom','name','url','web','email','valuesvalue'):
        return 'identifier / geography / contact metadata'
    if n.startswith(('data','created','modified','anyalta','anyauditoria')) or n in ('mes','mesany','mesdeany','diames','diademes','diasetmana','diadesetmana','hora','horadia','horadedia'):return 'time or coded dimension'
    if n in ('tipusnum','metode','indicador','state','stationid','vehicle_type','slotlevel','slotspace','es_seu_principal'):return 'coded dimension'
    return 'candidate'

def locate(props, geom=None):
    cols=spatial.columns(props.keys())
    def area(kind):
        raw=props.get(cols.get(kind,'')); key=spatial.code(raw)
        if key in INDEX[kind]:return INDEX[kind][key]
        key=REF['names'].get(kind,{}).get(spatial.norm(props.get(cols.get(kind+'Name',''),raw)))
        return INDEX[kind].get(key)
    ni=area('neighbourhood');di=area('district')
    if ni is not None:return ni,INDEX['district'][str(AREAS['neighbourhood'][ni]['district'])]
    method=props.get('_location_method','')
    # A district polygon or district-only statistical row cannot create 73 observations.
    if method=='district' or (geom is None and di is not None and not cols.get('section') and not cols.get('aeb')):return None,di
    if geom is None:
        key=(props.get(cols.get('district','')),props.get(cols.get('section','')),props.get(cols.get('aeb','')))
        if key not in GEOCACHE:
            match,method,_=spatial.resolve(props,cols,REF)
            GEOCACHE[key]=match['geometry'] if match and method in ('census section','statistical area','neighbourhood') else None
        geom=GEOCACHE[key]
    if geom is not None:
        try:
            g=shape(geom);p=g if g.geom_type=='Point' else g.representative_point()
            hits=TREES['neighbourhood'].query(p,predicate='intersects')
            if len(hits):
                ni=int(min(hits));return ni,INDEX['district'][str(AREAS['neighbourhood'][ni]['district'])]
            if di is None:
                hits=TREES['district'].query(p,predicate='intersects')
                if len(hits):di=int(min(hits))
        except Exception:pass
    return None,di

def series_name(name):
    return re.sub(r'[_\s.\-]+',' ',re.sub(r'(?<!\d)(?:19|20)\d{2}(?!\d)','',re.sub(r'\.(zip|csv|json|geojson|gpkg|xlsx|xml|kml|kmz)$','',name.lower()))).strip()

def process(resource):
    rid=resource['id']; dest=CACHE/'resources-v2'/f'{rid}.json';dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():return rid,'cached'
    d=next(d for d in CATALOG['datasets'] if d['id']==resource['_dataset_id'])
    result=json.loads((ROOT/'.cache/map-audit/resources'/rid/'result.json').read_text())
    approved=AUDIT['resources'][rid]['cases']
    cases=[ca for ca in result['cases'] if ca.get('payload') and any(ca['member']==c['member'] and ca['year']==c['year'] for c in approved)]
    cases=[ca for ca in cases if ca['year'] or not any(c['year'] and c['member']==ca['member'] for c in cases)]
    out={'resource':rid,'dataset':d['id'],'variables':[],'fields':[],'cases':[],'sparseVariables':0};raw=None;parsed={}
    for ca in cases:
      try:
        data=json.loads(gzip.decompress(Path(ca['payload']).read_bytes()))
        if data['sourceSha256']!=AUDIT['resources'][rid]['sha256']:raise ValueError('Audit/source hash mismatch')
        published=resource.get('years',[])
        year=ca['year'] or (published[0] if len(published)==1 else None)
        date_basis='record' if ca['year'] else 'filename' if year else 'undated'
        # Unknown/current map display year is not an observed 2026 measurement.
        year=int(year) if year and re.fullmatch(r'(19|20)\d{2}',str(year)) else None
        keybase={'dataset':d['id'],'datasetTitle':d['title'],'category':d['category'],'resource':rid,'resourceName':resource['name'],'resourceUrl':resource['url'],'datasetUrl':d['url'],'license':d['license'],'sha256':data['sourceSha256'],'member':ca['member'],'year':year,'dateBasis':date_basis,'sourceRows':data['selectedRows'],'unmappedRows':data['withoutGeometry']+data['excluded'],'retrievedAt':data['retrievedAt']}
        fields=data['fields']; metrics=[f['name'] for f in data['numericFields'] if role(f['name'])=='candidate' or re.fullmatch(r'(19|20)\d{2}',f['name'])]
        categories=[f['field'] for f in data.get('filterOptions',[]) if role(f['field'])=='candidate']
        for field in fields:out['fields'].append({'member':ca['member'],'year':year,'field':field,'role':'wide-year measurement (reshaped)' if field in metrics and re.fullmatch(r'(19|20)\d{2}',field) else role(field) if role(field)!='candidate' else 'numeric measurement candidate' if field in metrics else 'categorical dimension' if field in categories else 'text / constant / insufficient numeric coverage'})
        rows=[];strata=[];raw_strata=False
        if data['aggregated']:
            if raw is None:
                raw,_=loader.fetch_resource(resource)
                if hashlib.sha256(raw).hexdigest()!=data['sourceSha256']:raise ValueError('Raw source changed since audit')
            if ca['member'] not in parsed:parsed[ca['member']]=loader.read_rows(raw,resource['format'],resource['name'],ca['member'])[0]
            fields_map=spatial.columns(fields); geo_fields=set(v for v in fields_map.values() if v)
            dimensions=[f for f in fields if f not in metrics and f not in geo_fields and f!=data['yearField'] and f in categories and role(f) not in ('geometry / coordinate','time axis')]
            for row in parsed[ca['member']]:
                props=loader.flatten(row.get('properties') or {}) if row.get('type')=='Feature' else loader.flatten({k:v for k,v in row.items() if k!='_geometry'})
                if ca['year'] and str(props.get(data['yearField']))!=ca['year']:continue
                place=locate(props)
                rows.append((props,place));strata.append(tuple((f,str(props.get(f,''))) for f in dimensions))
            raw_strata=True
        else:
            for f in data['geometry']['features']:rows.append((f['properties'],locate(f['properties'],f['geometry'])));strata.append(())
        point_source=all(t in ('Point','MultiPoint') for t in data['geometryTypes']) and not data.get('locationMethods')
        native=all(m in ('census section','statistical area','neighbourhood','district','postal address') for m in data.get('locationMethods',[]))
        geometry_safe=point_source or (bool(data.get('locationMethods')) and native)
        grouped=collections.defaultdict(list)
        for row,stratum in zip(rows,strata):grouped[stratum].append(row)
        for stratum,records in grouped.items():
          for kind,position in [('neighbourhood',0),('district',1)]:
            for metric in metrics:
                buckets=collections.defaultdict(list)
                for props,place in records:
                    value=numeric(props.get(metric))
                    if place[position] is not None and value is not None:buckets[place[position]].append(value)
                values=[float(np.median(buckets[i])) if i in buckets else None for i in range(len(AREAS[kind]))]
                if sum(v is not None for v in values)<(10 if kind=='neighbourhood' else 3):
                    out['sparseVariables']+=1;continue
                out['variables'].append({**keybase,**({'year':int(metric),'dateBasis':'column'} if re.fullmatch(r'(19|20)\d{2}',metric) else {}),'sourceField':metric,'field':'Annual value' if re.fullmatch(r'(19|20)\d{2}',metric) else metric,'stratum':dict(stratum),'areaLevel':kind,'aggregation':'Median of source observations within each area' if not raw_strata else 'Median of source observations within each area and category stratum','values':values,'counts':[len(buckets.get(i,[])) for i in range(len(values))], 'inferenceEligible':geometry_safe and not any(norm(f).startswith('codi') and f not in geo_fields and f not in dimensions for f in fields) if raw_strata else geometry_safe,'limitation':None if geometry_safe else 'Non-point geographic support not validated for spatial inference; source codes or representative points used descriptively','series':series_name(resource['name'])})
        if point_source:
          for kind,position in [('neighbourhood',0),('district',1)]:
            # Counts are recorded features, not independently verified service coverage.
            count=np.zeros(len(AREAS[kind]));loc=0
            for props,place in rows:
                if place[position] is not None:count[place[position]]+=1;loc+=1
            if loc:
                out['variables'].append({**keybase,'field':'Recorded features / km²','stratum':{},'areaLevel':kind,'aggregation':'Count of mapped source features divided by land area (km²)','values':(count/AREA_KM2[kind]).tolist(),'counts':count.astype(int).tolist(),'inferenceEligible':True,'limitation':'Recorded feature density is not population-adjusted provision or a complete inventory guarantee','series':series_name(resource['name'])})
                for field in categories:
                    vals=sorted({str(props.get(field)) for props,place in rows if props.get(field) is not None})
                    for val in vals:
                        cat=np.zeros(len(count))
                        for props,place in rows:
                            if place[position] is not None and str(props.get(field))==val:cat[place[position]]+=1
                        shares=[float(cat[i]/count[i]*100) if count[i] else None for i in range(len(count))]
                        out['variables'].append({**keybase,'field':field+' — '+val+' (%)','stratum':{field:val},'areaLevel':kind,'aggregation':'Share of recorded features in this category, within area (%)','values':shares,'counts':count.astype(int).tolist(),'inferenceEligible':True,'limitation':'Category shares are compositional; an increase in one share reduces others','series':series_name(resource['name'])})
        out['cases'].append({'member':ca['member'],'year':year,'status':'processed','rawStratified':raw_strata,'strata':len(grouped)})
      except Exception as error:out['cases'].append({'member':ca['member'],'year':ca['year'],'status':'excluded','reason':str(error)[:500]})
    dest.write_text(json.dumps(out,ensure_ascii=False,allow_nan=False,separators=(',',':')))
    return rid,'processed'

def main():
    CACHE.mkdir(exist_ok=True)
    jobs=[{**r,'_dataset_id':d['id']} for d in CATALOG['datasets'] for r in d['resources'] if r['id'] in AUDIT['resources']]
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        for i,result in enumerate(pool.map(process,jobs),1):
            if i%25==0 or i==len(jobs):print(f'Extracted {i}/{len(jobs)} audited resources',flush=True)
    (CACHE/'areas.json').write_text(json.dumps({k:[{**{key:v for key,v in a.items() if key!='geometry'},'areaKm2':float(AREA_KM2[k][i]),'centroid':list(transform(PROJECT,POLYS[k][i]).centroid.coords)[0]} for i,a in enumerate(areas)] for k,areas in AREAS.items()}))
if __name__=='__main__':main()
