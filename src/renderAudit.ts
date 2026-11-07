import manifest from '../config/map-render-audit.json';
import type { Catalog, CatalogResource, ResourceData } from './catalog';
export type AuditedCase = { member: string | null; year: string | null; metrics: string[]; renderModes: string[]; filterAudit?: {mode:string;testedCombinations:number;totalCombinations:string} };
export type RenderAudit = { excludedDatasets?: string[]; resources: Record<string, { sha256: string; cases: AuditedCase[] }> | null };
const audit: RenderAudit = manifest;
export function auditedCuratedLayers<T extends string>(layers: T[], datasetIds: Record<string,T>, evidence: RenderAudit = audit): T[] {
  const excluded=new Set((evidence.excludedDatasets||[]).map(id=>datasetIds[id]));
  return layers.filter(id=>!excluded.has(id));
}
export function auditedCatalog(catalog: Catalog, evidence: RenderAudit = audit): Catalog {
  if (!evidence.resources) return catalog;
  const datasets = catalog.datasets.map(d => ({ ...d, resources: d.resources.filter(r => evidence.resources![r.id]?.cases.length) })).filter(d => d.resources.length);
  return { ...catalog, datasets, count: datasets.length, resourceCount: datasets.reduce((n,d)=>n+d.resources.length,0) };
}
export function auditedSelection(resource: CatalogResource, member = '', year = '', evidence: RenderAudit = audit) {
  if (!evidence.resources) return { member, year };
  const record = evidence.resources[resource.id];
  const matches = record?.cases.filter(c => (!member || c.member === member) && (!year || c.year === year));
  const chosen = matches?.sort((a,b)=>(b.year || '').localeCompare(a.year || ''))[0];
  if (!chosen) throw Error('This edition did not pass the map audit. See the rendering review for its original source.');
  return { member: chosen.member || '', year: chosen.year || '' };
}
export function auditedData(resource: CatalogResource, data: ResourceData, evidence: RenderAudit = audit): ResourceData {
  if (!evidence.resources) return data;
  const record = evidence.resources[resource.id];
  const checked = record?.cases.find(c=>(c.member || '')===(data.member || '') && (c.year || '')===(data.selectedYear || ''));
  if (!checked || record.sha256 !== data.sourceSha256) throw Error('This source edition has changed or has not passed the current map audit. It needs to be checked again.');
  return {...data,
    numericFields:data.numericFields.filter(f=>checked.metrics.includes(f.name)),
    members:data.members.filter(m=>record.cases.some(c=>c.member===m)),
    years:data.years.filter(y=>record.cases.some(c=>c.member===data.member && c.year===y)),
    renderModes:checked.renderModes,
    notes:[...(data.notes||[]),...(checked.filterAudit?.mode==='representative'?[`Category filters were tested with ${checked.filterAudit.testedCombinations} representative selections; exhaustive coverage is incomplete. See the filter audit coverage report.`]:[])],
  };
}

export function auditedCases(resource: CatalogResource): AuditedCase[] {
  return audit.resources?.[resource.id]?.cases || [];
}
