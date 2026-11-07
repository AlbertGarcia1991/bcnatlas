import { auditedSelection, auditedData } from './renderAudit';
import type { FeatureCollection, Geometry, GeoJsonProperties } from 'geojson';
export type CatalogResource = { id: string; name: string; format: string; url: string; modified: string | null; size: number | null; years: string[]; previewSupported: boolean; available?: boolean };
export type CatalogDataset = { id: string; title: string; description: string; geographic: boolean; mapMethods?: string[]; mapStatus?: string; license: string; licenseUrl: string; publisher: string; author: string; category: string; url: string; tags: string[]; modified: string; resources: CatalogResource[] };
export type Catalog = { retrievedAt: string; count: number; resourceCount: number; geographicCount: number; datasets: CatalogDataset[] };
export type ResourceData = { renderModes?: string[]; storageSource?: string; matchedRows?: number; locationMethods?: string[]; aggregated?: boolean; filters?: Record<string, string>; filterOptions?: { field: string; values: string[] }[]; referenceProvenance?: Record<string, unknown>; totalRows: number; selectedRows: number; mappedCount: number; excluded: number; withoutGeometry: number; fields: string[]; preview: Record<string, unknown>[]; geometry: FeatureCollection<Geometry, GeoJsonProperties>; geometryTypes: string[]; numericFields: { name: string; min: number; max: number; count: number }[]; years: string[]; yearField: string | null; selectedYear: string | null; members: string[]; member: string | null; hasDistrict: boolean; sourceSha256: string; retrievedAt: string; notes: string[] };
export type CatalogOverlay = { key: string; dataset: CatalogDataset; resource: CatalogResource; data: ResourceData; color: string; visible: boolean; metric: string; render: 'heatmap' | 'geometry' };
export const overlayColors = ['#327ca3', '#b85586', '#84713d', '#4f9760', '#ae653d', '#6f69ab'];
export const plainText = (s: string) => s.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&');
export function resourceKey(resource: CatalogResource, data: ResourceData) { return [resource.id, data.member || '', data.selectedYear || '', JSON.stringify(Object.fromEntries(Object.entries(data.filters || {}).sort(([a],[b])=>a.localeCompare(b))))].map(encodeURIComponent).join('~'); }
export function preferredResource(resources: CatalogResource[]) {
  const priority = ['GEOJSON', 'CSV', 'GPKG', 'JSON', 'ZIP', 'XLSX', 'XML', 'KML', 'KMZ'];
  return [...resources].sort((a,b) => {
    const ay = Math.max(0, ...a.years.map(Number)); const by = Math.max(0, ...b.years.map(Number));
    const ar = priority.indexOf(a.format.toUpperCase()); const br = priority.indexOf(b.format.toUpperCase());
    return Number(b.previewSupported) - Number(a.previewSupported) || Number(a.available === false) - Number(b.available === false) || by - ay || (ar < 0 ? 99 : ar) - (br < 0 ? 99 : br);
  })[0];
}
export async function loadResource(dataset: CatalogDataset, resource: CatalogResource, signal?: AbortSignal, member = '', year = '', filters: Record<string, string> = {}): Promise<ResourceData> {
  ({member,year}=auditedSelection(resource,member,year));
  const params = new URLSearchParams(); if (member) params.set('member', member); if (year) params.set('year', year); if (Object.keys(filters).length) params.set('filters', JSON.stringify(filters));
  const response = await fetch(`/api/resource/${encodeURIComponent(dataset.id)}/${resource.id}?${params}`, { signal });
  if (!response.headers.get('content-type')?.includes('application/json')) throw Error('The preview service is temporarily unavailable. Please retry shortly.');
  const body = await response.json();
  if (!response.ok) throw Error(typeof body.detail === 'string' ? body.detail : 'The resource could not be loaded. Try its original download.');
  return auditedData(resource, body);
}
export function filteredGeometry(overlay: CatalogOverlay, district: number) {
  return district && overlay.data.hasDistrict ? { ...overlay.data.geometry, features: overlay.data.geometry.features.filter(f => f.properties?._district === district || (Array.isArray(f.properties?._districts) && f.properties._districts.includes(district))) } : overlay.data.geometry;
}
export function overlayPeriod(overlay: CatalogOverlay) { return overlay.data.selectedYear || (overlay.resource.years.length ? overlay.resource.years.join('–') : 'Undated / current'); }
export function downloadOverlay(overlay: CatalogOverlay, district: number) {
  const data = { ...filteredGeometry(overlay, district), attribution: { publisher: overlay.dataset.publisher, license: overlay.dataset.license, licenseUrl: overlay.dataset.licenseUrl, dataset: overlay.dataset.url, resource: overlay.resource.url, retrievedAt: overlay.data.retrievedAt, sourceSha256: overlay.data.sourceSha256, selectedYear: overlay.data.selectedYear, member: overlay.data.member, storageSource: overlay.data.storageSource, processing: overlay.data.notes, reference: overlay.data.referenceProvenance, filters: overlay.data.filters } };
  const url = URL.createObjectURL(new Blob([JSON.stringify(data)], { type: 'application/geo+json' })); const link = document.createElement('a'); link.href=url; link.download=`${overlay.dataset.id}-${overlayPeriod(overlay).replaceAll(' / ', '-')}.geojson`; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export function defaultMetric(data: Pick<ResourceData, 'numericFields'>, preferred = ''): string {
  const fields = data.numericFields;
  return fields.find(f => f.name === preferred)?.name || fields.find(f => f.name !== '_records')?.name || fields[0]?.name || '';
}

export function canApplyFilter(filters: Record<string,string>, field: string, value: string): boolean {
  const next={...filters}; if(value)next[field]=value;else delete next[field];
  return (!value || (field.length<=200 && value.length<=500)) && Object.keys(next).length<=12 && JSON.stringify(next).length<=4096;
}
