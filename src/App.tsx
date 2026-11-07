import { auditedCatalog, auditedCuratedLayers } from './renderAudit';
import { dataUrl } from './dataSource';
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Layers, ArrowUpRight, Share2, Check, SlidersHorizontal, X, MapPin, Info, Download, RotateCcw, MousePointer2 } from 'lucide-react';
import MapView from './Map';
import CatalogExplorer from './CatalogExplorer';
import Timeline from './Timeline';
import useTimelineOverlays from './useTimelineOverlays';
import { editions, overlayEditions, editionForYear } from './timeline';
import DatasetLayers from './DatasetLayers';
import { curatedDatasetIds } from './datasetChoices';
import { defaultMetric, loadResource, resourceKey, overlayColors, type Catalog, type CatalogOverlay } from './catalog';
import { layers, districts, filterPoints, distanceMeters, format, readSettings, settingsQuery, type LayerId, type Manifest, type Point, type Settings } from './data';

const Analytics = lazy(()=>import('./Analytics'));
const cache = new Map<string, Point[]>();
// Prepared snapshots remain usable where the equivalent raw file failed its audit.
// Never substitute a Q4 snapshot for a different quarter or drop category filters.
function snapshotFallback(o:CatalogOverlay):LayerId|undefined {
  const id=curatedDatasetIds[o.dataset.id];
  return id && !Object.keys(o.data.filters || {}).length && (id==='accidents' || /4t|q4/i.test(o.resource.name)) ? id : undefined;
}
function readAuditedSettings(search:string) {
  const settings=readSettings(search);
  return {...settings,enabled:auditedCuratedLayers(settings.enabled,curatedDatasetIds)};
}
export default function App() {
  const [view,setView]=useState(new URLSearchParams(location.search).get('view')==='analytics'?'analytics':'map');
  const [layerCatalog,setLayerCatalog] = useState<Catalog>();
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [overlays, setOverlays] = useState<CatalogOverlay[]>([]);
  const initialCatalog = useRef(new URLSearchParams(location.search).get('catalog'));
  const [restoring, setRestoring] = useState(!!initialCatalog.current);
  const [restoreError, setRestoreError] = useState('');
  const [settings, setSettings] = useState(() => readAuditedSettings(location.search));
  const temporal=useTimelineOverlays(overlays,setOverlays,settings.year,restoring);
  const coverageLayers = useMemo(()=>[...settings.enabled.map(id=>({id,title:layers.find(l=>l.id===id)!.title,years:[2023,2024,2025,...editions(layerCatalog?.datasets.find(d=>curatedDatasetIds[d.id]===id)?.resources.filter(r=>id==='accidents' || /4t|q4/i.test(r.name)) || []).map(e=>e.timelineYear)]})),...overlays.filter(o=>o.visible).map(o=>({id:o.dataset.id,title:o.dataset.title,years:[...overlayEditions(o).map(e=>e.timelineYear),...(snapshotFallback(o)?[2023,2024,2025]:[])]}))],[settings.enabled,overlays,layerCatalog]);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [loaded, setLoaded] = useState<{ year: number; data: Partial<Record<LayerId, Point[]>> }>({ year: 0, data: {} });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [sources, setSources] = useState(false);
  const [sidebar, setSidebar] = useState(false);
  const [copied, setCopied] = useState(false);
  const [shareError, setShareError] = useState('');
  const [inspection, setInspection] = useState<[number, number] | null>(null);
  const [viewport, setViewport] = useState<[number, number, number, number] | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  function changeYear(year:number) {
    const fallback=overlays.filter(o=>o.visible && snapshotFallback(o) && manifest?.datasets[snapshotFallback(o)!].years[year] && !editionForYear(overlayEditions(o),year,o.resource));
    if(fallback.length)setOverlays(current=>current.filter(o=>!fallback.includes(o)));
    setSettings(s=>({...s,year,enabled:[...new Set([...s.enabled,...fallback.map(o=>snapshotFallback(o)!)])]}));
  }
  useEffect(()=>{
    if(restoring)return;
    const fallback=overlays.filter(o=>o.visible && snapshotFallback(o) && manifest?.datasets[snapshotFallback(o)!].years[settings.year] && !editionForYear(overlayEditions(o),settings.year,o.resource));
    if(!fallback.length)return;
    setOverlays(current=>current.filter(o=>!fallback.includes(o)));
    setSettings(s=>({...s,enabled:[...new Set([...s.enabled,...fallback.map(o=>snapshotFallback(o)!)])]}));
  },[overlays,manifest,settings.year,restoring]);
  const patch = (value: Partial<Settings>) => setSettings(s => ({ ...s, ...value }));
  useEffect(() => { const abort = new AbortController(); fetch(dataUrl('manifest.json'), { signal: abort.signal }).then(r => { if (!r.ok) throw Error('Source manifest unavailable'); return r.json(); }).then(setManifest).catch(e => { if (e.name !== 'AbortError') setError('Could not load the data catalog. Please retry.'); }); return () => abort.abort(); }, [retry]);
  useEffect(() => {
    const q = new URLSearchParams(settingsQuery(settings));
    if(view==='analytics')q.set('view','analytics');
    if (restoring && initialCatalog.current) q.set('catalog', initialCatalog.current);
    else if (overlays.length) q.set('catalog', JSON.stringify(overlays.map(o=>({resource:o.resource.id,member:o.data.member,year:o.data.selectedYear,filters:o.data.filters,metric:o.metric,render:o.render,visible:o.visible}))));
    history.replaceState(null, '', '?' + q.toString());
  }, [settings, overlays, restoring, view]);
  useEffect(() => {
    if (!initialCatalog.current) return;
    const ac = new AbortController();
    async function restore() {
      try {
        const specs = JSON.parse(initialCatalog.current!);
        if (!Array.isArray(specs) || specs.length > 6) throw Error('Invalid shared catalog selection.');
        const response=await fetch(dataUrl('catalog.json'),{signal:ac.signal});if(!response.ok)throw Error('Catalog unavailable');
        const catalog:Catalog=auditedCatalog(await response.json());const restored:CatalogOverlay[]=[];
        for(const spec of specs) {
          const dataset=catalog.datasets.find(d=>d.resources.some(r=>r.id===spec.resource));const resource=dataset?.resources.find(r=>r.id===spec.resource);
          if(!dataset||!resource)throw Error('A shared resource is no longer in the catalog snapshot.');
          const data=await loadResource(dataset,resource,ac.signal,typeof spec.member==='string'?spec.member:'',typeof spec.year==='string'?spec.year:'',spec.filters || {});
          if(!data.mappedCount && !(data.selectedRows===0 && Object.keys(data.filters||{}).length))throw Error('A shared resource has no map geometry.');
          const key=resourceKey(resource,data);if(restored.some(o=>o.dataset.id===dataset.id))continue;
          restored.push({key,dataset,resource,data,color:overlayColors[restored.length],visible:spec.visible!==false,metric:defaultMetric(data,spec.metric),render:spec.render==='heatmap'&&(!data.renderModes||data.renderModes.includes('heatmap'))?'heatmap':'geometry'});
        }
        if(!ac.signal.aborted)setOverlays(restored);
      } catch(e) { if(!ac.signal.aborted)setRestoreError('Shared catalog layers could not be restored. Open the dataset catalog to load them again.'); }
      finally { if(!ac.signal.aborted)setRestoring(false); }
    }
    void restore();return()=>ac.abort();
  }, []);
  useEffect(() => { const restore = () => setSettings(readAuditedSettings(location.search)); window.addEventListener('popstate', restore); return () => window.removeEventListener('popstate', restore); }, []);
  const enabledKey = settings.enabled.join(',');
  useEffect(() => {
    if (!manifest) return;
    const controller = new AbortController(); let current = true;
    setLoading(true); setError('');
    Promise.all(settings.enabled.map(async id => {
      const snapshot = manifest.datasets[id].years[settings.year];
      if (!snapshot) return [id, []] as const;
      if (!cache.has(snapshot.file)) {
        const r = await fetch(dataUrl(snapshot.file), { signal: controller.signal });
        if (!r.ok) throw Error('Snapshot could not be downloaded');
        const points: Point[] = await r.json();
        if (!Array.isArray(points) || points.length !== snapshot.count) throw Error('Snapshot count does not match the source manifest');
        cache.set(snapshot.file, points);
      }
      return [id, cache.get(snapshot.file)!] as const;
    })).then(entries => { if (current) setLoaded({ year: settings.year, data: Object.fromEntries(entries) }); }).catch(e => { if (current && e.name !== 'AbortError') { setLoaded({ year: settings.year, data: {} }); setError('A data snapshot could not load. Check your connection and retry.'); } }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; controller.abort(); };
  }, [manifest, settings.year, enabledKey, retry]);
  const points = useMemo(() => Object.fromEntries(settings.enabled.map(id => [id, filterPoints(loaded.year === settings.year ? loaded.data[id] || [] : [], settings.district)])) as Partial<Record<LayerId, Point[]>>, [loaded, enabledKey, settings.year, settings.district]);
  const total = Object.values(points).reduce((sum, p) => sum + p.length, 0);
  const visible = useMemo(() => viewport ? Object.values(points).reduce((sum, list) => sum + list.filter(p => p[0] >= viewport[0] && p[0] <= viewport[2] && p[1] >= viewport[1] && p[1] <= viewport[3]).length, 0) : 0, [points, viewport]);
  const localCounts = useMemo(() => layers.filter(l => settings.enabled.includes(l.id)).map(l => ({ ...l, count: inspection ? (points[l.id] || []).filter(p => distanceMeters(inspection, [p[0], p[1]]) <= 300).length : 0 })), [inspection, points, enabledKey]);
  const busy = !error && (loading || loaded.year !== settings.year || settings.enabled.some(id => !loaded.data[id]));
  useEffect(() => { if (sources) dialog.current?.showModal(); else dialog.current?.close(); }, [sources]);
  async function share() { try { await navigator.clipboard.writeText(location.href); setCopied(true); setShareError(''); setTimeout(() => setCopied(false), 2500); } catch { setShareError('Copy the URL from your address bar to share this view.'); } }
  function exportData() {
    const csv = ['dataset,year,longitude,latitude,district_code', ...settings.enabled.flatMap(id => (points[id] || []).map(p => `${id},${settings.year},${p.join(',')}`))].join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); const a = document.createElement('a'); a.href = url; a.download = `barcelona-atlas-${settings.year}.csv`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <div className="app">
    <header className="header"><a className="brand" href="/" aria-label="Barcelona Atlas home"><img className="brand-icon" src="/barcelona-atlas-logo.png" alt="" width="52" height="52"/><span>barcelona<span className="brand-light">atlas</span><small>THE CITY, THROUGH DATA</small></span></a><nav aria-label="Main navigation"><button aria-pressed={view==='map'} className={view==='map'?'nav-active':''} onClick={()=>setView('map')}>Explore the map</button><button onClick={() => setCatalogOpen(true)}>Dataset catalog</button><button onClick={() => setSources(true)}>Data & sources <ArrowUpRight size={14}/></button><button aria-pressed={view==='analytics'} className={'analytics-nav '+(view==='analytics'?'nav-active':'')} onClick={()=>setView('analytics')}>Analytics</button></nav><div className="header-right"><span className="city-badge"><span/> Barcelona, ES</span><button className="share-button" onClick={share}>{copied ? <Check size={16}/> : <Share2 size={16}/>}<span>{copied ? 'Link copied' : 'Share view'}</span></button></div></header>
    {view==='analytics'?<Suspense fallback={<main className="analytics-loading" role="status">Loading analytics…</main>}><Analytics/></Suspense>:<div className="workspace">
      <button className="mobile-toggle" onClick={() => setSidebar(!sidebar)} aria-expanded={sidebar}><SlidersHorizontal size={17}/>{sidebar ? 'Close controls' : 'Map controls'}</button>
      <aside className={'sidebar ' + (sidebar ? 'open' : '')} aria-label="Map settings">
        <div className="intro"><div className="eyebrow">BARCELONA OPEN DATA EXPLORER</div><h1>A city, in layers.</h1><p>Look a little closer. Discover the patterns that shape Barcelona.</p></div>
        <section className="location-section"><label className="section-label" htmlFor="district"><MapPin size={14}/> Explore an area</label><select id="district" value={settings.district} onChange={e => patch({ district: Number(e.target.value) })}>{districts.map((d, i) => <option key={d} value={i}>{d}</option>)}</select></section>
        <DatasetLayers overlays={overlays} setOverlays={setOverlays} curated={settings.enabled} curatedYear={settings.year} disableCurated={id=>setSettings(s=>({...s,enabled:s.enabled.filter(x=>x!==id)}))} district={settings.district} restoring={restoring} onCatalog={setLayerCatalog} temporal={temporal}/>
        <section className="appearance"><div className="section-heading"><h2><SlidersHorizontal size={15}/> Map appearance</h2><button className="text-button" title="Reset appearance" aria-label="Reset appearance" onClick={() => patch({ radius: 22, opacity: 75, intensity: 1, mode: 'heatmap' })}><RotateCcw size={14}/></button></div><div className="segmented" aria-label="Visualization style"><button aria-pressed={settings.mode === 'heatmap'} className={settings.mode === 'heatmap' ? 'selected' : ''} onClick={() => patch({ mode: 'heatmap' })}>Heatmap</button><button aria-pressed={settings.mode === 'points'} className={settings.mode === 'points' ? 'selected' : ''} onClick={() => patch({ mode: 'points' })}>Individual points</button></div>
          <label className="range-label" htmlFor="opacity">Layer opacity <span>{settings.opacity}%</span></label><input id="opacity" type="range" min="20" max="100" value={settings.opacity} onChange={e => patch({ opacity: +e.target.value })}/>
          {settings.mode === 'heatmap' && <><label className="range-label" htmlFor="radius">Heat radius <span>{settings.radius} px</span></label><input id="radius" type="range" min="8" max="50" value={settings.radius} onChange={e => patch({ radius: +e.target.value })}/><label className="range-label" htmlFor="intensity">Intensity <span>{settings.intensity.toFixed(1)}×</span></label><input id="intensity" type="range" min="0.2" max="3" step="0.1" value={settings.intensity} onChange={e => patch({ intensity: +e.target.value })}/></>}
        </section>
        <div className="sidebar-footer"><span className="open-dot"/> Open data. Open possibilities.<button onClick={() => setSources(true)}>About this project <ArrowUpRight size={13}/></button><a className="github-link" href="https://github.com/AlbertGarcia1991/bcnatlas" target="_blank" rel="noopener noreferrer">View project on GitHub <ArrowUpRight size={13}/></a><small>BARCELONA ATLAS <span>v1.3.0</span></small></div>
      </aside>
      <main className="map-area" aria-label="Map explorer"><MapView points={points} settings={settings} overlays={temporal.mapOverlays} onInspect={setInspection} onViewport={setViewport}/>
        <div className="map-top"><div className="area-pill"><span className="open-dot"/>{districts[settings.district]}<span className="pill-divider"/>{settings.year}</div><span className="interaction-hint"><MousePointer2 size={14}/> Click the map to explore nearby</span></div>
        {(restoring || restoreError) && <div className="catalog-restore" role="status">{restoring?"Restoring shared catalog overlays…":restoreError}{restoreError&&<button aria-label="Dismiss restore message" onClick={()=>setRestoreError('')}><X size={14}/></button>}</div>}
        {shareError && <div className="toast" role="status">{shareError}<button onClick={() => setShareError('')} aria-label="Dismiss share message"><X size={14}/></button></div>}
        {error ? <div className="status-banner error" role="alert">{error}<button onClick={() => setRetry(n => n + 1)}>Retry</button></div> : busy && settings.enabled.length > 0 ? <div className="status-banner" role="status"><span className="spinner"/> Loading {settings.year} snapshots…</div> : null}
        {!settings.enabled.length && !overlays.some(o=>o.visible) && <div className="empty-state"><Layers size={28}/><strong>Your city. Your perspective.</strong><p>Turn on a data layer to start exploring.</p><button onClick={() => { patch({ enabled: ['accidents'] }); setSidebar(false); }}>Explore traffic accidents</button></div>}
        {inspection && !!settings.enabled.length && <section className="inspection"><div className="section-heading"><h2>Around this point</h2><button aria-label="Close nearby details" onClick={() => setInspection(null)}><X size={16}/></button></div><p>Curated records within 300 metres · {settings.year}</p>{localCounts.map(l => <div className="inspection-row" key={l.id}><span><i style={{ background: l.color }}/>{l.title}</span><strong>{busy ? '…' : format(l.count)}</strong></div>)}<small>{inspection[1].toFixed(5)}° N, {inspection[0].toFixed(5)}° E</small></section>}
        {settings.enabled.some(id=>manifest?.datasets[id].years[settings.year]) && <div className="legend"><div className="legend-heading">{settings.mode === 'heatmap' ? 'Record concentration' : 'Record locations'}<button onClick={() => setSources(true)} aria-label="How to read the map"><Info size={14}/></button></div>{layers.filter(l => settings.enabled.includes(l.id)).map(l => <div className="legend-row" key={l.id}><span>{l.title}</span>{settings.mode === 'heatmap' ? <div className="gradient" style={{ background: `linear-gradient(90deg, ${l.colors.join(',')})` }}/> : <i style={{ background: l.color }}/>}</div>)}{settings.mode === 'heatmap' && <div className="legend-scale"><span>Lower</span><span>Higher</span></div>}<small>Relative density · not a risk or canopy measure</small></div>}
        <Timeline year={settings.year} onChange={changeYear} layers={coverageLayers}/>

        <footer className="map-footer"><span aria-live="polite">{busy && settings.enabled.length ? 'Loading records…' : `${overlays.length ? 'Curated: ' : ''}${format(visible)} in view · ${format(total)} selected records${overlays.length ? ` · ${temporal.mapOverlays.filter(o=>o.visible).length} catalog overlays` : ''}`}</span><button disabled={!total || busy} onClick={exportData}><Download size={13}/><span>Export curated CSV</span></button></footer>
      </main>
    </div>}
    <CatalogExplorer open={catalogOpen} onClose={()=>setCatalogOpen(false)} overlays={overlays} onAdd={overlay=>{setView('map');const curatedId=curatedDatasetIds[overlay.dataset.id];if(curatedId)setSettings(s=>({...s,enabled:s.enabled.filter(id=>id!==curatedId)}));setOverlays(current=>current.length>=6&&!current.some(o=>o.dataset.id===overlay.dataset.id)?current:[...current.filter(o=>o.dataset.id!==overlay.dataset.id),overlay]);}}/>
    <dialog ref={dialog} onCancel={() => setSources(false)} onClose={() => setSources(false)} onClick={e => { if (e.target === dialog.current) setSources(false); }} aria-labelledby="sources-title"><div className="dialog-content"><button className="close-dialog" aria-label="Close sources" onClick={() => setSources(false)}><X size={21}/></button><div className="eyebrow">TRANSPARENT BY DESIGN</div><h2 id="sources-title">Every layer has a source.</h2><p>Public records from Ajuntament de Barcelona, made explorable. Datasets are served from the configured data store. All active layers follow the map timeline. Current or undated resources are assigned to 2026 for navigation, without inferring an observation date. Missing years hide a layer until a covered year is selected. Catalog overlays retain their original licenses and provenance; see Source & processing on each overlay for the storage source.</p><div className="methodology"><h3>Reading the map</h3><p>Heatmaps show the concentration of records. Each accident or tree has equal weight within its layer. Colours are relative within each layer, not comparable across datasets. Zoom, radius and intensity change the appearance. Overlapping colours do not imply a statistical relationship.</p><p>Accidents cover a calendar year; tree layers are Q4 inventory snapshots, not trees planted that year or a measure of canopy cover. All three layers have 2023–2025 coverage. The city’s dataset defines geographic scope; district filters use the source district codes.</p></div>
      {manifest && layers.map(l => { const d = manifest.datasets[l.id]; const r = d.years[settings.year]; if(!r)return null; return <article className="source-card" key={l.id}><div className="source-heading"><span style={{ background: l.color }}/><h3>{l.title}</h3><span>{settings.year}</span></div><p>{d.title}</p><dl><div><dt>Publisher</dt><dd>{d.publisher}</dd></div><div><dt>Period</dt><dd>{r.period}</dd></div><div><dt>Mapped records</dt><dd>{format(r.count)} / {format(r.sourceRows)}</dd></div><div><dt>Excluded coordinates</dt><dd>{format(r.excluded)}</dd></div><div><dt>License</dt><dd><a href={d.licenseUrl} target="_blank" rel="noreferrer">{d.license}</a></dd></div></dl><div className="source-links"><a href={d.url} target="_blank" rel="noreferrer">Dataset page <ArrowUpRight size={14}/></a><a href={r.url} target="_blank" rel="noreferrer">Original {r.resourceName.endsWith('.zip') ? 'ZIP' : 'CSV'} <Download size={14}/></a></div></article>; })}
      <section className="colour-story" aria-labelledby="colour-story-title"><div className="eyebrow">ROOTED IN BARCELONA</div><h3 id="colour-story-title">A city, in colour.</h3><div className="heritage-swatches" aria-label="Navy, Mediterranean blue, gold, Sant Jordi red and warm ivory"><span/><span/><span/><span/><span/></div><p>Gold and red echo Barcelona’s heraldry: the four red bars on gold and the cross of Sant Jordi. The logo’s blues evoke the Mediterranean; warm ivory gives the map room to breathe.</p><p>The flower is a nod to the city’s iconic <em>panot</em> paving tiles. Fontanella was the first street fully paved with the flower design in 1908. These shades are our interpretation, not an official municipal palette.</p><div className="heritage-links"><a href="https://www.barcelona.cat/culturapopular/sites/default/files/retallables8.pdf" target="_blank" rel="noreferrer">Barcelona’s heraldry ↗</a><a href="https://beteve.cat/va-passar-aqui/panot-paviment-iconic-barcelona/" target="_blank" rel="noreferrer">The story of the panot ↗</a></div></section>
      <div className="methodology"><h3>Processing & attribution</h3><p>Coordinates are rounded to six decimals; invalid or missing coordinates and points outside a broad Barcelona sanity envelope are excluded and counted above. Records are not sampled. The map preserves separate records at identical coordinates. Exports include selected datasets and the district filter, across the full district rather than only the visible map.</p><p>Data: © Ajuntament de Barcelona, CC BY 4.0. Adapted by Barcelona Atlas. Basemap: © OpenStreetMap contributors. Rendering: MapLibre GL JS.</p><p>Retrieved {manifest ? new Date(manifest.retrievedAt).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }) : '…'}. <a href={dataUrl('manifest.json')} target="_blank" rel="noreferrer">Download provenance manifest</a> for resource identifiers, timestamps and checksums.</p></div><div className="dialog-footer">An independent open-data explorer · v1.3.0<br/>Not an official Ajuntament de Barcelona service.</div></div></dialog>
  </div>;
}
