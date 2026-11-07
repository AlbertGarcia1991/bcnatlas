import { auditedCatalog } from './renderAudit';
import { useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { Search } from 'lucide-react';
import { dataUrl } from './dataSource';
import { canApplyFilter, defaultMetric, loadResource, overlayColors, preferredResource, resourceKey, type Catalog, type CatalogDataset, type CatalogOverlay, type CatalogResource } from './catalog';
import { curatedDatasetIds, datasetTitles, datasetSeries } from './datasetChoices';
import type { LayerId } from './data';
import { editions, editionForYear } from './timeline';
import OverlayPanel from './OverlayPanel';

type Selection = { resource: string; member?: string; year?: string; filters?: Record<string,string> };
type Props = { overlays: CatalogOverlay[]; setOverlays: Dispatch<SetStateAction<CatalogOverlay[]>>; curated: LayerId[]; curatedYear: number; disableCurated: (id: LayerId) => void; district: number; restoring: boolean; onCatalog: (catalog: Catalog) => void; temporal: {status:Record<string,string>; failures:Record<string,string>; retry:()=>void} };
export default function DatasetLayers({ overlays, setOverlays, curated, curatedYear, disableCurated, district, restoring, onCatalog, temporal }: Props) {
  const [catalog, setCatalog] = useState<Catalog>();
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [query, setQuery] = useState('');
  const [activeOnly, setActiveOnly] = useState(false);
  const [selections, setSelections] = useState<Record<string, Selection>>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const requests = useRef(new Map<string, AbortController>());
  const queue = useRef(Promise.resolve());
  const currentOverlays = useRef(overlays); currentOverlays.current = overlays;
  useEffect(() => {
    const ac = new AbortController(); setError('');
    Promise.all([
      fetch(dataUrl('catalog.json'), {signal:ac.signal}).then(r => { if(!r.ok) throw Error('Layer catalog unavailable'); return r.json() as Promise<Catalog>; }),
      fetch(dataUrl('mirror-status.json'), {signal:ac.signal, cache:'no-cache'}).then(r=>r.ok?r.json():null).catch(()=>null),
    ]).then(([c,status]) => {
      if(ac.signal.aborted)return;
      const missing = new Set<string>(status?.missing?.map((m:{key:string})=>m.key.split('/')[2]) || []);
      const approved=auditedCatalog(c);
      const available={...approved,datasets:approved.datasets.map(d=>({...d,resources:d.resources.map(r=>({...r,available:!missing.has(r.id)}))}))};
      setCatalog(available); onCatalog(available);
    }).catch(e=>{if(!ac.signal.aborted)setError(e.message)});
    return ()=>ac.abort();
  }, [retry]);
  useEffect(()=>()=>{for(const ac of requests.current.values()) ac.abort();},[]);
  const datasets = useMemo(()=> (catalog?.datasets || []).filter(d=>d.mapMethods?.length && d.resources.some(r=>r.previewSupported))
    .sort((a,b)=>Number(!!curatedDatasetIds[b.id])-Number(!!curatedDatasetIds[a.id]) || a.title.localeCompare(b.title)),[catalog]);
  useEffect(()=>{
    if(!catalog || restoring || [2023,2024,2025].includes(curatedYear))return;
    for(const d of datasets.filter(d=>curated.includes(curatedDatasetIds[d.id]))) {
      if(requests.current.has(d.id))continue;
      const target=editionForYear(editions(d.resources.filter(r=>curatedDatasetIds[d.id]==='accidents' || /4t|q4/i.test(r.name))),curatedYear);
      if(target)start(d,target.resource,{resource:target.resource.id,member:target.member,year:target.year});
    }
  },[catalog,curatedYear,curated.join(','),restoring]);
  const shown = datasets.filter(d=> (!activeOnly || overlays.some(o=>o.dataset.id===d.id) || curated.includes(curatedDatasetIds[d.id]) || pending[d.id]) && query.toLowerCase().split(/\s+/).every(w=>[d.title,d.id,d.category,datasetTitles[d.id],...d.tags].join(' ').toLowerCase().includes(w)));
  function stop(d:CatalogDataset) {
    requests.current.get(d.id)?.abort(); requests.current.delete(d.id);
    setPending(p=>({...p,[d.id]:false}));
    setOverlays(os=>os.filter(o=>o.dataset.id!==d.id));
    if(curatedDatasetIds[d.id])disableCurated(curatedDatasetIds[d.id]);
  }
  function start(d:CatalogDataset, resource:CatalogResource, selection:Selection) {
    const occupied = new Set([...currentOverlays.current.map(o=>o.dataset.id),...requests.current.keys()]);
    if(!occupied.has(d.id) && occupied.size>=6) {setErrors(e=>({...e,[d.id]:'Six layers are loaded. Turn one off to add another.'}));return;}
    const group=datasetSeries(d.resources).find(g=>g.resources.some(r=>r.id===resource.id));
    const target=editionForYear(editions(group?.resources || [resource],selection.member),curatedYear,resource);
    if(target){resource=target.resource;selection={...selection,resource:resource.id,member:target.member,year:target.year};}
    requests.current.get(d.id)?.abort();
    const ac = new AbortController(); requests.current.set(d.id,ac);
    setPending(p=>({...p,[d.id]:true})); setErrors(e=>({...e,[d.id]:''})); setSelections(s=>({...s,[d.id]:selection}));
    // Keep the previous edition visible until its replacement is ready. Serialize heavy parses.
    queue.current = queue.current.then(async()=>{
      if(ac.signal.aborted)return;
      try {
        let data = await loadResource(d,resource,ac.signal,selection.member,selection.year,selection.filters);
        if(!selection.year && !data.selectedYear && data.years.length>0) data=await loadResource(d,resource,ac.signal,data.member || '',[...data.years].sort().at(-1),selection.filters);
        if(ac.signal.aborted)return;
        if(!data.mappedCount && !(data.selectedRows===0 && Object.keys(selection.filters||{}).length))throw Error('No matching map locations in this edition. Choose another year or breakdown.');
        const overlay:CatalogOverlay = {key:resourceKey(resource,data),dataset:d,resource,data,color:overlayColors[datasets.findIndex(x=>x.id===d.id)%overlayColors.length],visible:true,metric:defaultMetric(data),render:(!data.renderModes||data.renderModes.includes('heatmap'))&&!defaultMetric(data)&&!data.locationMethods?.length&&data.geometryTypes.every(t=>t==='Point'||t==='MultiPoint')?'heatmap':'geometry'};
        setOverlays(os=>[...os.filter(o=>o.dataset.id!==d.id),overlay]);
        if(curatedDatasetIds[d.id])disableCurated(curatedDatasetIds[d.id]);
      } catch(e) {if(!ac.signal.aborted)setErrors(es=>({...es,[d.id]:e instanceof Error?e.message:'Could not load layer.'}));}
      finally { if(requests.current.get(d.id)===ac){requests.current.delete(d.id);setPending(p=>({...p,[d.id]:false}));} }
    });
  }
  return <section className="dataset-layers" aria-label="Map layers">
    <div className="section-heading"><h2>Map layers</h2><span>{datasets.length} datasets</span></div>
    <p className="section-description">Toggle a dataset to map it. Use the bottom timeline for every layer’s year.</p>
    <label className="layer-search"><Search size={14}/><input aria-label="Search map layers" placeholder="Search all map layers…" value={query} onChange={e=>setQuery(e.target.value)}/></label>
    <label className="active-only"><input type="checkbox" checked={activeOnly} onChange={e=>setActiveOnly(e.target.checked)}/>Show active layers only</label>
    {error&&<p role="alert">{error} <button onClick={()=>setRetry(n=>n+1)}>Retry</button></p>}
    {!catalog&&!error&&<p role="status">Loading map layers…</p>}
    <div className="dataset-list">{shown.map(d=>{
      const overlay=overlays.find(o=>o.dataset.id===d.id);
      const active=!!overlay?.visible || curated.includes(curatedDatasetIds[d.id]);
      const groups=datasetSeries(d.resources);
      const selection=selections[d.id];
      const curatedResource = curated.includes(curatedDatasetIds[d.id]) ? preferredResource(d.resources.filter(r=>r.years.includes(String(curatedYear)) && (!d.id.startsWith('arbrat-') || /4t/i.test(r.name)))) : undefined;
      const resource=d.resources.find(r=>r.id===(selection?.resource || overlay?.resource.id)) || curatedResource || preferredResource(d.resources.filter(r=>r.previewSupported))!;
      const group=groups.find(g=>g.resources.some(r=>r.id===resource.id))!;
      const year=curatedYear;
      const choose=(r:CatalogResource|undefined)=>{if(!r)return;const s={resource:r.id,filters:overlay?.data.filters};setSelections(ss=>({...ss,[d.id]:s}));if(active||pending[d.id])start(d,r,s);};
      const title=datasetTitles[d.id] || d.title;
      return <article className={'dataset-card '+(active?'active':'')} key={d.id}>
        <button className="layer-toggle" role="switch" aria-checked={active||!!pending[d.id]} aria-label={title} disabled={restoring} onClick={()=>active||pending[d.id]?stop(d):start(d,resource,selection||{resource:resource.id})}>
          <span className="layer-copy"><small>{d.category}</small><strong>{title}</strong></span><span className="switch"><span/></span>
        </button>
        <div className="edition-controls"><p className="edition-summary">{year}{curated.includes(curatedDatasetIds[d.id])&&[2023,2024,2025].includes(year)?' · Curated snapshot':''} · Follows map timeline{groups.length>1?` · ${group.label}`:''}</p>{(active||pending[d.id])&&<div className="dataset-selectors">
          {groups.length>1&&<label>Breakdown<select aria-label={`Breakdown for ${title}`} value={group.key} onChange={e=>{const g=groups.find(g=>g.key===e.target.value)!;choose(editionForYear(editions(g.resources),year)?.resource || preferredResource(g.resources));}}>{groups.map(g=><option key={g.key} value={g.key}>{g.label}</option>)}</select></label>}
        </div>}</div>
        {active&&temporal.status[d.id]==='missing'&&<p className="year-unavailable" role="status">No data for {year}. Layer stays enabled; choose another year on the timeline.</p>}
        {active&&curated.includes(curatedDatasetIds[d.id])&&![2023,2024,2025].includes(year)&&!pending[d.id]&&<p className="year-unavailable" role="status">No snapshot for {year}. Choose another year on the timeline.</p>}
        {active&&temporal.status[d.id]==='loading'&&<p role="status">Loading {year}… Other years are hidden.</p>}
        {active&&temporal.status[d.id]==='error'&&<p role="alert" className="error">{temporal.failures[d.id]} <button onClick={temporal.retry}>Retry year</button></p>}
        {pending[d.id]&&<p role="status">Loading layer…  <button onClick={()=>stop(d)}>Cancel</button></p>}
        {errors[d.id]&&<p className="error" role="alert">{errors[d.id]} <button onClick={()=>start(d,resource,selection||{resource:resource.id})}>Retry</button></p>}
        {resource.available===false&&<p>This edition is awaiting archive upload.</p>}
        {overlay&&(!overlay.visible || temporal.status[d.id]==='ready')&&<>
          {overlay.data.selectedRows===0&&<p role="status">No records match these filters. Clear a filter or choose another combination.</p>}
          {!!overlay.data.members.length&&<label className="resource-subselect">Layer / worksheet<select aria-label={`Worksheet for ${title}`} value={overlay.data.member||''} onChange={e=>start(d,overlay.resource,{resource:overlay.resource.id,member:e.target.value})}>{overlay.data.members.map(m=><option key={m}>{m}</option>)}</select></label>}

          {overlay.data.filterOptions?.map(f=><label className="resource-subselect" key={f.field}>{f.field}<select aria-label={`${f.field} for ${title}`} value={overlay.data.filters?.[f.field]||''} onChange={e=>{const filters={...overlay.data.filters};if(e.target.value)filters[f.field]=e.target.value;else delete filters[f.field];start(d,overlay.resource,{resource:overlay.resource.id,member:overlay.data.member||'',year:overlay.data.selectedYear||'',filters});}}><option value="">All categories</option>{f.values.filter(Boolean).map(v=><option key={v} disabled={!canApplyFilter(overlay.data.filters||{},f.field,v)}>{v}</option>)}</select></label>)}
          <details className="layer-details"><summary>Style, source & export · {overlay.data.mappedCount.toLocaleString()} features</summary><OverlayPanel overlays={[overlay]} district={district} onChange={next=>setOverlays(os=>os.flatMap(o=>o.dataset.id===d.id?next:o))}/></details>
        </>}
      </article>;
    })}</div>
    {catalog&&!shown.length&&<p>No matching map layers.</p>}
  </section>;
}
