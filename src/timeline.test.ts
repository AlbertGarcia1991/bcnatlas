import { describe, it, expect, vi } from 'vitest';
import type { CatalogResource, CatalogOverlay } from './catalog';
vi.mock('./renderAudit',()=>({auditedCases:(r:CatalogResource)=>r.id==='records'?[{member:'table',year:null},{member:'table',year:'2021'},{member:'table',year:'2023'},{member:'other',year:'2020'}]:[{member:null,year:null}]}));
import { editions, editionForYear, matchesEdition, timelineYears, yearCoverage } from './timeline';
const resource=(id:string,years:string[]=[]):CatalogResource=>({id,years,name:id+'.csv',format:'CSV',url:'',modified:null,size:null,previewSupported:true});
describe('shared timeline',()=>{
 it('uses audited record years instead of publication years and respects worksheet coverage',()=>{
  const values=editions([resource('records',['2025'])],'table');
  expect(values.map(e=>e.timelineYear)).toEqual([2021,2023]);
  expect(editionForYear(values,2022)).toBeUndefined();
  expect(editionForYear(values,2023)?.year).toBe('2023');
 });
 it('assigns undated editions only to 2026 without inventing a record year',()=>{
  const values=editions([resource('current')]);
  expect(values[0]).toMatchObject({timelineYear:2026,year:''});
  expect(editionForYear(values,2025)).toBeUndefined();
 });
 it('uses filename years when there is no year inside the records',()=>{
  expect(editions([resource('annual',['2020'])])[0]).toMatchObject({timelineYear:2020,year:''});
 });
 it('fills gaps and distinguishes full, partial and absent coverage',()=>{
  const layers=[{id:'a',title:'A',years:[2021,2023]},{id:'b',title:'B',years:[2023,2026]}];
  expect(timelineYears(layers,2023)).toEqual([2021,2022,2023,2024,2025,2026]);
  expect(yearCoverage(layers,2023).state).toBe('full');
  expect(yearCoverage(layers,2021)).toMatchObject({state:'partial',available:1});
  expect(yearCoverage(layers,2022).state).toBe('none');
 });
 it('rejects stale editions while the requested year is loading',()=>{
  const r=resource('records');const target=editionForYear(editions([r],'table'),2023);
  const o={resource:r,data:{member:'table',selectedYear:'2021'}} as CatalogOverlay;
  expect(matchesEdition(o,target)).toBe(false);
  expect(matchesEdition({...o,data:{...o.data,selectedYear:'2023'}},target)).toBe(true);
 });
});
