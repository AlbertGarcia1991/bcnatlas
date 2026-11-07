import { expect, it, vi } from 'vitest';
import type { Map as GLMap } from 'maplibre-gl';
import { renderCatalogOverlay } from './mapOverlay';
import type { CatalogOverlay } from './catalog';
import type { Settings } from './data';
it('reuses geometry when colouring changes and refreshes it when the data changes',()=>{
  const layers=new Set<string>();let exists=false;
  const setData=vi.fn();const addSource=vi.fn(()=>{exists=true;});
  const map={getSource:()=>exists?{setData}:undefined,addSource,getLayer:(id:string)=>layers.has(id),addLayer:(layer:{id:string})=>layers.add(layer.id),setLayoutProperty:vi.fn(),setPaintProperty:vi.fn()} as unknown as GLMap;
  const overlay={data:{hasDistrict:false,geometry:{type:'FeatureCollection',features:[{type:'Feature',geometry:{type:'Point',coordinates:[2.17,41.39]},properties:{value:'1.234,5'}}]},numericFields:[{name:'value',min:0,max:2000}]},metric:'',visible:true,render:'geometry',color:'#327ca3'} as unknown as CatalogOverlay;
  const settings={district:0,opacity:75,radius:22,intensity:1} as Settings;
  renderCatalogOverlay(map,overlay,0,settings);
  renderCatalogOverlay(map,{...overlay,metric:'value'},0,settings);
  expect(addSource).toHaveBeenCalledTimes(1);expect(setData).not.toHaveBeenCalled();
  expect(overlay.data.geometry.features[0].properties?.value).toBe('1.234,5');
  renderCatalogOverlay(map,{...overlay,data:{...overlay.data}},0,settings);
  expect(setData).toHaveBeenCalledTimes(1);
});
