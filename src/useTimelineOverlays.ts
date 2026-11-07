import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { defaultMetric, loadResource, resourceKey, type CatalogOverlay } from './catalog';
import { editionForYear, matchesEdition, overlayEditions } from './timeline';

export default function useTimelineOverlays(overlays: CatalogOverlay[], setOverlays: Dispatch<SetStateAction<CatalogOverlay[]>>, year: number, restoring: boolean) {
  const [failed,setFailed]=useState<Record<string,{key:string;message:string}>>({});
  const failuresRef=useRef(failed);failuresRef.current=failed;
  const signature=(o:CatalogOverlay)=>JSON.stringify([year,o.resource.id,o.data.member,o.data.filters]);
  const [retry,setRetry]=useState(0);
  useEffect(()=>{
    if(restoring)return;
    const ac=new AbortController();
    void (async()=>{
      for(const o of overlays.filter(o=>o.visible)) {
        const target=editionForYear(overlayEditions(o),year,o.resource);
        if(!target || matchesEdition(o,target) || failuresRef.current[o.dataset.id]?.key===signature(o))continue;
        try {
          const data=await loadResource(o.dataset,target.resource,ac.signal,target.member,target.year,o.data.filters);
          if(ac.signal.aborted)return;
          if(!matchesEdition({...o,resource:target.resource,data},target))throw Error('The source returned a different edition than requested.');
          setOverlays(current=>current.map(existing=>existing===o?{...o,resource:target.resource,data,key:resourceKey(target.resource,data),metric:defaultMetric(data,o.metric),render:data.renderModes?.includes(o.render)===false?'geometry':o.render}:existing));
        } catch(error) {
          if(ac.signal.aborted)return;
          const failure={key:signature(o),message:error instanceof Error?error.message:'Could not load this year.'};
          failuresRef.current={...failuresRef.current,[o.dataset.id]:failure};
          setFailed(f=>({...f,[o.dataset.id]:failure}));
        }
      }
    })();
    return ()=>ac.abort();
  },[overlays,year,restoring,retry,setOverlays]);
  const failures=Object.fromEntries(overlays.filter(o=>failed[o.dataset.id]?.key===signature(o)).map(o=>[o.dataset.id,failed[o.dataset.id].message]));
  const status=Object.fromEntries(overlays.map(o=>{
    const target=editionForYear(overlayEditions(o),year,o.resource);
    return [o.dataset.id,!target?'missing':matchesEdition(o,target)?'ready':failures[o.dataset.id]?'error':'loading'];
  }));
  return { mapOverlays:overlays.filter(o=>status[o.dataset.id]==='ready'), status, failures, retry:()=>{failuresRef.current={};setFailed({});setRetry(n=>n+1);} };
}
