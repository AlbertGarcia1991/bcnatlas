import type { Map, ExpressionSpecification, GeoJSONSource, LayerSpecification } from 'maplibre-gl';
import { filteredGeometry, type CatalogOverlay } from './catalog';
import type { Settings } from './data';
const sources = new WeakMap<Map, globalThis.Map<string, { data: CatalogOverlay['data']; district: number }>>();
export function renderCatalogOverlay(m: Map, overlay: CatalogOverlay, index: number, settings: Settings) {
  const id=`catalog-${index}`;
  let cache=sources.get(m);if(!cache){cache=new globalThis.Map();sources.set(m,cache);}
  const previous=cache.get(id);
  if(!m.getSource(id)||previous?.data!==overlay.data||previous.district!==settings.district){
    const collection=filteredGeometry(overlay,settings.district);
    const data={...collection,features:collection.features.map(f=>{
      const properties={...f.properties};
      overlay.data.numericFields.forEach((metric,i)=>{
        let value=String(f.properties?.[metric.name]??'').trim().replaceAll(' ','');
        if(value.includes(',')&&value.includes('.'))value=value.lastIndexOf(',')>value.lastIndexOf('.')?value.replaceAll('.','').replace(',','.'):value.replaceAll(',','');
        else value=value.replace(',','.');
        const number=value?Number(value):NaN;
        properties[`_atlas_metric_${i}`]=Number.isFinite(number)?number:null;
      });
      return {...f,properties};
    })};
    const source=m.getSource(id) as GeoJSONSource|undefined;
    if(source)source.setData(data);else m.addSource(id,{type:'geojson',data});
    cache.set(id,{data:overlay.data,district:settings.district});
  }
  const metricIndex=overlay.data.numericFields.findIndex(f=>f.name===overlay.metric);
  const metric=overlay.data.numericFields[metricIndex];
  const value:ExpressionSpecification=['get',`_atlas_metric_${metricIndex}`];
  const color:ExpressionSpecification|string=metric?['case',['==',value,null],'#a3aaa4',['interpolate',['linear'],value,metric.min,'#f2eedb',metric.max,overlay.color]]:overlay.color;
  const visibility=overlay.visible?'visible':'none';
  const layers:LayerSpecification[]=[
    {id:id+'-fill',type:'fill',source:id,filter:['==',['geometry-type'],'Polygon'],layout:{visibility},paint:{'fill-color':color,'fill-opacity':settings.opacity/100*.65,'fill-outline-color':overlay.color}},
    {id:id+'-line',type:'line',source:id,filter:['==',['geometry-type'],'LineString'],layout:{visibility},paint:{'line-color':color,'line-width':3,'line-opacity':settings.opacity/100}},
    {id:id+'-points',type:'circle',source:id,filter:['==',['geometry-type'],'Point'],layout:{visibility:overlay.visible&&overlay.render==='geometry'?'visible':'none'},paint:{'circle-color':color,'circle-radius':4,'circle-stroke-width':.6,'circle-stroke-color':'white','circle-opacity':settings.opacity/100}},
    {id:id+'-heat',type:'heatmap',source:id,filter:['==',['geometry-type'],'Point'],layout:{visibility:overlay.visible&&overlay.render==='heatmap'?'visible':'none'},paint:{'heatmap-color':['interpolate',['linear'],['heatmap-density'],0,'rgba(0,0,0,0)',.2,'#e9eed3',.7,overlay.color,1,overlay.color],'heatmap-weight':.1,'heatmap-radius':settings.radius,'heatmap-intensity':settings.intensity,'heatmap-opacity':settings.opacity/100}},
  ];
  for(const layer of layers){
    if(!m.getLayer(layer.id))m.addLayer(layer);
    else{
      m.setLayoutProperty(layer.id,'visibility',layer.layout?.visibility);
      for(const [name,paint] of Object.entries(layer.paint||{}))m.setPaintProperty(layer.id,name as Parameters<Map['setPaintProperty']>[1],paint);
    }
  }
}

export function forgetCatalogOverlay(m: Map, id: string) { sources.get(m)?.delete(id); }
