import { dataUrl } from './dataSource';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, X, ArrowUpRight, Database, Layers, ChevronLeft, ChevronRight, Plus, Check, Download } from 'lucide-react';
import { format } from './data';
import { defaultMetric, loadResource, plainText, preferredResource, resourceKey, overlayColors, type Catalog, type CatalogDataset, type CatalogResource, type ResourceData, type CatalogOverlay } from './catalog';

export default function CatalogExplorer({ open, onClose, onAdd, overlays }: { open: boolean; onClose: () => void; onAdd: (o: CatalogOverlay) => void; overlays: CatalogOverlay[] }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogError, setCatalogError] = useState('');
  const [mirror, setMirror] = useState<{ uploadedResources: number; plannedResources: number; missingResources: number; missing?: {key:string}[] } | null>(null);
  const [query, setQuery] = useState('');
  const [geography, setGeography] = useState('all');
  const [formatFilter, setFormatFilter] = useState('all');
  const [page, setPage] = useState(0);
  const [dataset, setDataset] = useState<CatalogDataset | null>(null);
  const [resource, setResource] = useState<CatalogResource | null>(null);
  const [resourceYear, setResourceYear] = useState('all');
  const [data, setData] = useState<ResourceData | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [table, setTable] = useState(false);
  const [tableSearch, setTableSearch] = useState('');
  const [tablePage, setTablePage] = useState(0);
  const request = useRef<AbortController | null>(null);
  useEffect(() => { if (open) dialog.current?.showModal(); else dialog.current?.close(); }, [open]);
  useEffect(() => {
    if (!open || catalog) return;
    const ac = new AbortController(); setCatalogError('');
    fetch(dataUrl('catalog.json'), { signal: ac.signal }).then(r => { if (!r.ok) throw Error(); return r.json(); }).then(setCatalog).catch(e => { if (e.name !== 'AbortError') setCatalogError('The catalog could not load. Close and reopen to retry.'); });
    return () => ac.abort();
  }, [open, catalog]);
  useEffect(() => {
    if (!open) return;
    const ac = new AbortController();
    const refresh = () => fetch(dataUrl('mirror-status.json'), { signal: ac.signal, cache: 'no-cache' })
      .then(r => r.ok ? r.json() : null).then(value => {
        if (value && Number.isInteger(value.uploadedResources) && Number.isInteger(value.plannedResources) && Number.isInteger(value.missingResources)) setMirror(value);
      }).catch(() => {});
    refresh(); const timer = window.setInterval(refresh, 60000);
    return () => { ac.abort(); window.clearInterval(timer); };
  }, [open]);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => { if (!open) { request.current?.abort(); setPending(false); } }, [open]);
  const filtered = useMemo(() => {
    const words=query.toLocaleLowerCase().split(/\s+/).filter(Boolean);
    return (catalog?.datasets || []).filter(d => !!d.mapMethods?.length && (geography==='all' || (geography==='geographic' ? d.mapMethods?.some(m=>m==='geometry'||m==='coordinates') : d.mapMethods?.some(m=>m!=='geometry'&&m!=='coordinates'))) && (formatFilter==='all' || d.resources.some(r=>r.format.toUpperCase()===formatFilter)) && words.every(w=>[d.title,d.id,d.category,...d.tags].join(' ').toLocaleLowerCase().includes(w)));
  }, [catalog,query,geography,formatFilter]);
  useEffect(()=>setPage(0),[query,geography,formatFilter]);
  const formats=useMemo(()=>[...new Set(catalog?.datasets.filter(d=>d.mapMethods?.length).flatMap(d=>d.resources.map(r=>r.format.toUpperCase())) || [])].sort(),[catalog]);
  const years=[...new Set(dataset?.resources.flatMap(r=>r.years) || [])].sort().reverse();
  const resources=dataset?.resources.filter(r=>resourceYear==='all' || (resourceYear==='undated' ? !r.years.length : r.years.includes(resourceYear))) || [];
  function selectDataset(source:CatalogDataset) { const missing=new Set(mirror?.missing?.map(item=>item.key.split('/')[2])||[]);const d={...source,resources:source.resources.map(r=>({...r,available:!missing.has(r.id)}))}; request.current?.abort();setPending(false);setDataset(d);setResource(preferredResource(d.resources));setResourceYear('all');setData(null);setError('');setTable(false);setTableSearch('');setTablePage(0); }
  function selectResource(r:CatalogResource|undefined) { request.current?.abort();setPending(false);setResource(r||null);setData(null);setError('');setTable(false); }
  async function preview(member='',year='',filters:Record<string,string>={}) {
    if (!dataset || !resource) return;
    request.current?.abort();const ac=new AbortController();request.current=ac;setPending(true);setError('');
    try { const loaded=await loadResource(dataset,resource,ac.signal,member,year,filters);if(!ac.signal.aborted) {setData(loaded);setTableSearch('');setTablePage(0);} }
    catch(e) { if(!ac.signal.aborted) {setData(null);setError(e instanceof Error ? e.message : 'Resource preview failed.');} }
    finally { if(!ac.signal.aborted) setPending(false); }
  }
  const added=!!(resource && data && overlays.some(o=>o.key===resourceKey(resource,data)));
  function add() {
    if(!dataset || !resource || !data || !data.mappedCount || added || overlays.length>=6)return;
    onAdd({ key:resourceKey(resource,data),dataset,resource,data,color:overlayColors[overlays.length%overlayColors.length],visible:true,metric:defaultMetric(data),render:!defaultMetric(data)&&!data.locationMethods?.length && data.geometryTypes.every(t=>t==='Point'||t==='MultiPoint')?'heatmap':'geometry' });
    onClose();
  }
  const previewRows=(data?.preview || []).filter(row=>Object.values(row).some(v=>String(v??'').toLowerCase().includes(tableSearch.toLowerCase())));
  return <dialog className="catalog-dialog" ref={dialog} onCancel={onClose} onClose={onClose} onClick={e=>{if(e.target===dialog.current)onClose();}} aria-labelledby="catalog-title">
    <div className="catalog-header"><div><div className="eyebrow">BARCELONA MAP DATASETS</div><h2 id="catalog-title">Find another perspective.</h2><p>{catalog ? `${format(catalog.datasets.filter(d=>d.mapMethods?.length).length)} map datasets · coordinates and location references` : 'Loading the municipal catalog…'}</p></div><button aria-label="Close dataset catalog" onClick={onClose}><X size={22}/></button></div>
    {mirror && mirror.missingResources > 0 && <p className="catalog-message" role="status">Archive transfer in progress: {format(mirror.uploadedResources)} of {format(mirror.plannedResources)} files available. Some previews are pending; original-source links remain available.</p>}
    {catalogError && <div role="alert" className="catalog-message error">{catalogError}</div>}
    <div className="catalog-tools"><label className="catalog-search"><Search size={17}/><input autoComplete="off" aria-label="Search all datasets" placeholder="Search schools, air quality, population…" value={query} onChange={e=>setQuery(e.target.value)}/></label><select aria-label="Geography filter" value={geography} onChange={e=>setGeography(e.target.value)}><option value="all">All map datasets</option><option value="geographic">Coordinates / geometry</option><option value="tables">Location references</option></select><select aria-label="Format filter" value={formatFilter} onChange={e=>setFormatFilter(e.target.value)}><option value="all">All formats</option>{formats.map(f=><option key={f}>{f}</option>)}</select></div>
    <div className="catalog-body"><div className="catalog-results"><div className="results-count">{format(filtered.length)} matching datasets <span>Catalog snapshot {catalog && new Date(catalog.retrievedAt).toLocaleDateString('en-GB')}</span></div>
      {filtered.slice(page*25,(page+1)*25).map(d=><button className={'catalog-item '+(dataset?.id===d.id?'chosen':'')} key={d.id} onClick={()=>selectDataset(d)}><span className="catalog-item-icon">{d.geographic?<Layers size={18}/>:<Database size={18}/>}</span><span><strong>{d.title}</strong><small>{d.resources.length} resources · {d.mapMethods?.length ? d.mapMethods.join(' · ') : 'Location inspection pending'}</small><span className="format-tags">{[...new Set(d.resources.map(r=>r.format))].slice(0,4).map(f=><i key={f}>{f}</i>)}</span></span><ChevronRight size={15}/></button>)}
      {!filtered.length && catalog && <p className="catalog-message">No matching datasets. Try another word or clear the filters.</p>}
      {filtered.length>25&&<div className="catalog-pagination"><button aria-label="Previous catalog page" disabled={page===0} onClick={()=>setPage(p=>p-1)}><ChevronLeft size={16}/></button><span>{page+1} / {Math.ceil(filtered.length/25)}</span><button aria-label="Next catalog page" disabled={(page+1)*25>=filtered.length} onClick={()=>setPage(p=>p+1)}><ChevronRight size={16}/></button></div>}
    </div><section className="catalog-detail" aria-label="Dataset details">
      {!dataset?<div className="catalog-welcome"><Layers size={36}/><h3>One catalog. Many ways to explore.</h3><p>Select a dataset, choose its published resource, then preview its records. Add supported points, lines and polygons to your map.</p><p>Coordinates and geometry appear directly. Districts, neighbourhoods, census sections, street names and postal addresses are matched to official municipal references. Unmatched records are reported explicitly.</p><div className="catalog-feature-list"><span>CSV, JSON, GeoJSON & XML tables</span><span>GeoPackage, KML & ZIP geometry</span><span>XLSX sheets & archived resources</span></div></div>:<>
        <div className="eyebrow">{dataset.mapMethods?.join(' · ').toUpperCase() || 'SPATIAL DATASET'}</div><h3>{dataset.title}</h3><p className="dataset-description">{plainText(dataset.description).slice(0,1500)}</p><div className="catalog-source-links"><a href={dataset.url} target="_blank" rel="noreferrer">Official dataset <ArrowUpRight size={14}/></a>{dataset.licenseUrl?<a href={dataset.licenseUrl} target="_blank" rel="noreferrer">{dataset.license} <ArrowUpRight size={13}/></a>:<span>{dataset.license}</span>}</div>
        <p className="catalog-publisher">Publisher: {dataset.publisher}{dataset.author ? ` · ${dataset.author}` : ''} · Metadata updated {new Date(dataset.modified).toLocaleDateString('en-GB')}</p>
        <div className="resource-controls"><label>Published resource year<select aria-label="Published resource year" value={resourceYear} onChange={e=>{const value=e.target.value;setResourceYear(value);selectResource(preferredResource(dataset.resources.filter(r=>value==='all'||(value==='undated'?!r.years.length:r.years.includes(value)))));}}><option value="all">All published years</option><option value="undated">Undated / current</option>{years.map(y=><option key={y}>{y}</option>)}</select></label><label>Resource<select aria-label="Published resource" value={resource?.id||''} onChange={e=>selectResource(dataset.resources.find(r=>r.id===e.target.value))}>{!resources.length&&<option value="">No resource for this selection</option>}{resources.map(r=><option key={r.id} value={r.id}>{r.name} · {r.format}{r.available===false?' · awaiting upload':''}</option>)}</select></label></div>
        {resource&&<><div className="resource-meta"><span>{resource.years.length?`Year in filename: ${resource.years.join(', ')}`:'Undated / current resource — no observation year inferred'}</span><a href={resource.url} target="_blank" rel="noreferrer">Original download <Download size={13}/></a></div><div className="resource-actions"><button className="primary-action" disabled={pending||!resource.previewSupported} onClick={()=>void preview()}>{pending?<><span className="spinner"/>Reading resource…</>:<><Database size={15}/>Preview resource</>}</button>{data&&<button className="primary-action" disabled={pending||!data.mappedCount||added||overlays.length>=6} onClick={add}>{added?<Check size={15}/>:<Plus size={15}/>} {added?'Added to map':'Add to map'}</button>}</div>{!resource.previewSupported&&<p className="catalog-message">{resource.format} requires specialist software or a service-specific viewer. Use the original download; this resource is still included in the catalog.</p>}</>}
        {pending&&<p className="catalog-message" role="status">Loading and validating the selected resource. Large files can take up to two minutes. Prepared previews are cached for reuse.</p>}
        {error&&<p className="catalog-message error" role="alert">{error}</p>}
        {data&&!pending&&<div className="resource-preview"><div className="preview-stats"><div><strong>{format(data.selectedRows)}</strong><span>selected records</span></div><div><strong>{format(data.mappedCount)}</strong><span>map features</span></div><div><strong>{data.geometryTypes.length?data.geometryTypes.join(', '):'Table'}</strong><span>detected geometry</span></div></div>
          {!!data.members.length&&<label className="resource-subselect">Archive / layer / worksheet<select aria-label="Resource member" value={data.member||''} onChange={e=>void preview(e.target.value)}>{data.members.map(m=><option key={m}>{m}</option>)}</select></label>}
          {!!data.years.length&&<label className="resource-subselect">Year inside the records ({data.yearField})<select aria-label="Record year" value={data.selectedYear||''} onChange={e=>void preview(data.member||'',e.target.value,data.filters)}><option value="">All record years</option>{data.years.map(y=><option key={y}>{y}</option>)}</select></label>}
          {!!data.filterOptions?.length&&<div className="record-filters">{data.filterOptions.map(option=><label className="resource-subselect" key={option.field}>{option.field}<select aria-label={`Filter ${option.field}`} value={data.filters?.[option.field]||''} onChange={e=>{const filters={...data.filters};if(e.target.value)filters[option.field]=e.target.value;else delete filters[option.field];void preview(data.member||'',data.selectedYear||'',filters);}}><option value="">All categories</option>{option.values.map(v=><option key={v}>{v}</option>)}</select></label>)}</div>}
          <div className="resource-notes">{data.notes.map(note=><p key={note}>{note}</p>)}{overlays.length>=6&&<p>Six catalog overlays are active. Remove one before adding another.</p>}</div><button className="table-toggle" onClick={()=>setTable(!table)}>{table?'Hide':'Show'} table preview · first {data.preview.length} records</button>
          {table&&<div className="table-preview"><input aria-label="Search preview rows" placeholder="Search the first 100 rows…" value={tableSearch} onChange={e=>{setTableSearch(e.target.value);setTablePage(0);}}/><div className="table-scroll"><table><thead><tr>{data.fields.map(f=><th key={f}>{f}</th>)}</tr></thead><tbody>{previewRows.slice(tablePage*20,(tablePage+1)*20).map((r,i)=><tr key={i}>{data.fields.map(f=><td key={f}>{String(r[f]??'—')}</td>)}</tr>)}</tbody></table></div><div className="catalog-pagination"><button aria-label="Previous preview page" disabled={tablePage===0} onClick={()=>setTablePage(p=>p-1)}><ChevronLeft size={15}/></button><span>Preview page {tablePage+1} / {Math.max(1,Math.ceil(previewRows.length/20))} · {previewRows.length} preview rows</span><button aria-label="Next preview page" disabled={(tablePage+1)*20>=previewRows.length} onClick={()=>setTablePage(p=>p+1)}><ChevronRight size={15}/></button></div></div>}
          <details className="provenance-details"><summary>Resource provenance</summary><p>Retrieved {new Date(data.retrievedAt).toLocaleString('en-GB')}</p><p>Resource ID: {resource?.id}</p><p>Storage source: {data.storageSource || 'Municipal source'}</p><p>Source SHA-256: {data.sourceSha256}</p><p>{format(data.totalRows)} original records · {format(data.excluded)} invalid/outside geometry · {format(data.withoutGeometry)} without recognized geometry</p></details>
        </div>}
      </>}
    </section></div><div className="catalog-bottom">Resources load on demand. Location matches use official municipal references; unsupported or oversized files remain available at source. Up to six catalog overlays at once.</div>
  </dialog>;
}
