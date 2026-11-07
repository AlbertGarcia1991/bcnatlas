import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
// Bundle the module worker explicitly; Vite's dependency optimizer relocates the main module.
maplibregl.setWorkerUrl(workerUrl);
import type { Map as GLMap, GeoJSONSource } from 'maplibre-gl';
import { Crosshair, Minus, Plus, Maximize2 } from 'lucide-react';
import { type CatalogOverlay } from './catalog';
import { renderCatalogOverlay, forgetCatalogOverlay } from './mapOverlay';
import { centers, layers, type LayerId, type Point, type Settings } from './data';

export default function MapView({ points, settings, overlays, onInspect, onViewport }: { overlays: CatalogOverlay[]; points: Partial<Record<LayerId, Point[]>>; settings: Settings; onInspect: (p: [number, number]) => void; onViewport: (b: [number, number, number, number]) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<GLMap | null>(null);
  const callbacks = useRef({ onInspect, onViewport }); callbacks.current = { onInspect, onViewport };
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let m: GLMap;
    try {
      m = new maplibregl.Map({ container: container.current!, center: centers[0], zoom: 12.4, minZoom: 10, maxZoom: 18, maxBounds: [[1.99, 41.26], [2.32, 41.55]], attributionControl: { compact: false }, style: {
        version: 8,
        sources: {
          base: { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors' },
        },
        layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#e9eeea' } }, { id: 'base', type: 'raster', source: 'base', paint: { 'raster-saturation': -.8, 'raster-opacity': .65 } }],
      } });
      map.current = m;
    } catch { setError('The map needs WebGL. Please enable hardware acceleration or try another browser.'); return; }
    m.on('load', () => { setReady(true); const b = m.getBounds(); callbacks.current.onViewport([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]); });
    m.on('moveend', () => { const b = m.getBounds(); callbacks.current.onViewport([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]); });
    m.on('click', e => {
      callbacks.current.onInspect([e.lngLat.lng, e.lngLat.lat]);
      const candidates=(m.getStyle().layers||[]).filter(l=>l.id.startsWith('catalog-')&&!l.id.endsWith('-heat')).map(l=>l.id);
      if(!candidates.length)return;
      const hit=m.queryRenderedFeatures(e.point,{layers:candidates})[0];
      if(!hit)return;
      const content=document.createElement('div');content.className='feature-popup';
      const title=document.createElement('strong');title.textContent='Catalog feature';content.append(title);
      for(const [key,value] of Object.entries(hit.properties||{}).filter(([k])=>!k.startsWith('_')).slice(0,12)){
        const row=document.createElement('div');const name=document.createElement('b');name.textContent=key+': ';row.append(name,document.createTextNode(String(value).slice(0,200)));content.append(row);
      }
      new maplibregl.Popup({maxWidth:'310px'}).setLngLat(e.lngLat).setDOMContent(content).addTo(m);
    });
    m.on('error', e => { if (String(e.error?.message).includes('AJAXError') || e.error?.message?.includes('Failed to fetch')) setError('Base map tiles could not load. Check your connection; dataset layers remain available.'); else { console.error('Map rendering failed:', e.error); setError('A map layer could not render. Remove the latest overlay or try reloading the page.'); } });
    m.addControl(new maplibregl.ScaleControl({ maxWidth: 100 }), 'bottom-left');
    const observer = new ResizeObserver(() => m.resize()); observer.observe(container.current!);
    return () => { observer.disconnect(); m.remove(); map.current = null; setReady(false); };
  }, []);
  useEffect(() => {
    const m = map.current; if (!ready || !m) return;
    for (const layer of layers) {
      const id = layer.id;
      const data = { type: 'FeatureCollection' as const, features: (points[id] || []).map(p => ({ type: 'Feature' as const, properties: {}, geometry: { type: 'Point' as const, coordinates: [p[0], p[1]] } })) };
      if (m.getSource(id)) (m.getSource(id) as GeoJSONSource).setData(data);
      else {
        m.addSource(id, { type: 'geojson', data });
        m.addLayer({ id: id + '-heat', type: 'heatmap', source: id, paint: {
          'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(0,0,0,0)', .15, layer.colors[0], .5, layer.colors[1], 1, layer.colors[2]],
          'heatmap-weight': id === 'accidents' ? .1 : .025,
        } });
        m.addLayer({ id: id + '-points', type: 'circle', source: id, paint: { 'circle-color': layer.color, 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 1, 16, 4], 'circle-stroke-width': .4, 'circle-stroke-color': '#fff' } });
      }
    }
  }, [points, ready]);
  useEffect(() => {
    const m = map.current; if (!ready || !m) return;
    for (const { id } of layers) {
      if (!m.getLayer(id + '-heat')) continue;
      m.setLayoutProperty(id + '-heat', 'visibility', settings.enabled.includes(id) && settings.mode === 'heatmap' ? 'visible' : 'none');
      m.setLayoutProperty(id + '-points', 'visibility', settings.enabled.includes(id) && settings.mode === 'points' ? 'visible' : 'none');
      m.setPaintProperty(id + '-heat', 'heatmap-radius', settings.radius);
      m.setPaintProperty(id + '-heat', 'heatmap-intensity', settings.intensity);
      m.setPaintProperty(id + '-heat', 'heatmap-opacity', settings.opacity / 100);
      m.setPaintProperty(id + '-points', 'circle-opacity', settings.opacity / 100);
    }
  }, [settings, ready, points]);
  useEffect(() => {
    const m=map.current;if(!ready||!m)return;
    const active=new Set(overlays.map((_,i)=>`catalog-${i}`));
    for(const layer of [...(m.getStyle().layers||[])].reverse())if(layer.id.startsWith('catalog-')&&!active.has(layer.id.replace(/-(fill|line|points|heat)$/, '')))m.removeLayer(layer.id);
    for(const id of Object.keys(m.getStyle().sources))if(id.startsWith('catalog-')&&!active.has(id)){m.removeSource(id);forgetCatalogOverlay(m,id);}
    for(const [index,overlay] of overlays.entries()){
      renderCatalogOverlay(m, overlay, index, settings);
    }
  },[ready,overlays,settings.district,settings.opacity,settings.radius,settings.intensity]);
  useEffect(() => { if (ready) map.current?.flyTo({ center: centers[settings.district], zoom: settings.district ? 13.6 : 12.4, duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 700 }); }, [settings.district, ready]);
  return <><div className="map-canvas" ref={container} aria-label="Interactive Barcelona map. Use arrow keys to pan and plus or minus to zoom." />
    {error && <div className="map-error" role="alert">{error}<button onClick={() => setError('')} aria-label="Dismiss map message">×</button></div>}
    <div className="map-controls"><button title="Zoom in" aria-label="Zoom in" onClick={() => map.current?.zoomIn()}><Plus size={19}/></button><button title="Zoom out" aria-label="Zoom out" onClick={() => map.current?.zoomOut()}><Minus size={19}/></button><span/><button title="Reset map view" aria-label="Reset map view" onClick={() => map.current?.flyTo({ center: centers[0], zoom: 12.4, bearing: 0, pitch: 0 })}><Crosshair size={19}/></button><button title="Full screen" aria-label="Full screen" onClick={() => { if (document.fullscreenElement) void document.exitFullscreen(); else void container.current?.parentElement?.requestFullscreen().catch(() => setError('Full screen is unavailable in this browser.')); }}><Maximize2 size={17}/></button></div>
  </>;
}
