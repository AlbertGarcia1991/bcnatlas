import { datasetSeries } from './datasetChoices';
import { preferredResource, type CatalogOverlay, type CatalogResource } from './catalog';
import { auditedCases } from './renderAudit';

// Undated sources belong to this snapshot year, not every historical year.
export const CURRENT_YEAR = 2026;
export type Edition = { resource: CatalogResource; member: string; year: string; timelineYear: number };
export function editions(resources: CatalogResource[], member?: string): Edition[] {
  return resources.flatMap(resource => {
    const allCases = auditedCases(resource);
    // A null-year audit case is an unfiltered preview when dated cases exist.
    // It must not masquerade as a current or filename-year edition.
    const cases = allCases.filter(c=>c.year || !allCases.some(other=>other.member===c.member && other.year));
    const scoped = member && cases.some(c=>c.member===member) ? cases.filter(c=>c.member===member) : cases;
    return scoped.flatMap(c => (c.year ? [c.year] : resource.years.length ? resource.years : [String(CURRENT_YEAR)])
      .filter(y=>/^\d{4}$/.test(y) && +y>=1800 && +y<=CURRENT_YEAR)
      .map(y=>({resource,member:c.member || '',year:c.year || '',timelineYear:+y})));
  });
}
export function overlayEditions(o: CatalogOverlay) {
  const group=datasetSeries(o.dataset.resources).find(g=>g.resources.some(r=>r.id===o.resource.id));
  return editions(group?.resources || [o.resource],o.data.member || undefined);
}
export function editionForYear(choices: Edition[], year: number, preferred?: CatalogResource) {
  const matching=choices.filter(c=>c.timelineYear===year);
  const resource=matching.find(c=>c.resource.id===preferred?.id)?.resource || preferredResource(matching.map(c=>c.resource));
  return matching.find(c=>c.resource.id===resource?.id);
}
export function matchesEdition(o: CatalogOverlay, e?: Edition) {
  return !!e && o.resource.id===e.resource.id && (o.data.member || '')===e.member && (o.data.selectedYear || '')===e.year;
}
export type CoverageLayer = { id: string; title: string; years: number[] };
export function yearCoverage(layers: CoverageLayer[], year: number) {
  const missing=layers.filter(l=>!l.years.includes(year));
  return { missing, available:layers.length-missing.length, state:!layers.length?'idle':!missing.length?'full':missing.length===layers.length?'none':'partial' };
}
export function timelineYears(layers: CoverageLayer[], selected: number) {
  const available=layers.flatMap(l=>l.years);
  const first=Math.min(selected, ...(available.length?available:[2023]));
  return Array.from({length:CURRENT_YEAR-first+1},(_,i)=>first+i);
}
