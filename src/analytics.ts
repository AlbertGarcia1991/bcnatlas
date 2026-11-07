import analyticsRelease from '../config/analytics-release.json';
export type Area = {id:string;name:string;district:number;areaKm2:number;centroid:[number,number]};
export type Variable = {id:string;index:number;seriesId:string;dataset:string;datasetTitle:string;category:string;field:string;stratum:Record<string,string>;areaLevel:string;year:number|null;dateBasis:string;aggregation:string;values:(number|null)[];counts:number[];testable:boolean;eligibilityReason:string;limitation:string|null;summary:{median:number;min:number;max:number};n:number;resourceName:string;resourceUrl:string;datasetUrl:string;license:string;sha256:string;sourceRows:number;unmappedRows:number;retrievedAt:string;duplicateResources:string[]};
export type Pair = [number,number,number,number,number,number|null,number|null,number|null];
export type Diagnostic = {blockCI:[number,number]|null;leaveOneOutRange:[number,number];moranX:number;moranY:number;blocks:number};
export type Period = {year:number|null;areaLevel:string;variables:number;comparisons:number;spatialTests:number;controls:string;shards:number[];supported:number};
export type AnalyticsManifest = {version:number;generatedAt:string;seed:number;permutations:number;minAreas:number;fdrMethod:string;counts:Record<string,number>;areas:Record<string,Area[]>;periods:Record<string,Period>;sources:{title:string;url:string}[];datasetCoverage:{dataset:string;resource:string;fields:number;cases:{member:string|null;year:string|null;status:string;reason?:string;rawStratified?:boolean;strata?:number}[];sparseVariables:number}[]};
export const analyticsUrl=(name:string)=>'/api/analytics/'+name+'?release='+encodeURIComponent(analyticsRelease.prefix);
export async function readAnalytics<T>(name:string,signal?:AbortSignal):Promise<T>{const response=await fetch(analyticsUrl(name),{signal});if(!response.ok)throw Error('The analytics evidence could not load. Please retry.');return response.json();}
export const measureName=(v:Variable)=>v.field;
export const contextName=(v:Variable)=>Object.entries(v.stratum).map(([k,val])=>`${k}: ${val}`).join(' · ');
export function rankCorrelation(x:number[],y:number[]){
 const ranks=(a:number[])=>a.map(v=>{let less=0,equal=0;for(const n of a){if(n<v)less++;if(n===v)equal++;}return less+(equal+1)/2;});
 const rx=ranks(x),ry=ranks(y),avg=(x.length+1)/2;
 const xx=rx.map(v=>v-avg),yy=ry.map(v=>v-avg);const den=Math.sqrt(xx.reduce((s,v)=>s+v*v,0)*yy.reduce((s,v)=>s+v*v,0));return den?xx.reduce((s,v,i)=>s+v*yy[i],0)/den:null;
}
