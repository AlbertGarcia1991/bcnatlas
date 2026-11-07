import { preferredResource, type CatalogResource } from './catalog';

export type DatasetSeries = { key: string; label: string; resources: CatalogResource[] };
// Collapse file formats and annual editions, preserving quarters, geography and subject.
export function datasetSeries(resources: CatalogResource[]): DatasetSeries[] {
  const groups = new Map<string, CatalogResource[]>();
  for (const r of resources.filter(r => r.previewSupported)) {
    const key = r.name.toLowerCase().replace(/\.(zip|csv|json|geojson|gpkg|xlsx|xml|kml|kmz)$/g, '')
      .replace(/\.(csv|json|geojson|gpkg|xlsx|xml|kml|kmz)$/, '')
      .replace(/(^|[^0-9])(?:19|20)\d{2}(?=[^0-9]|$)/g, '$1')
      .replace(/[-_]js$/, '').replace(/[_\s.-]+/g, ' ').trim();
    groups.set(key, [...(groups.get(key) || []), r]);
  }
  const keys = [...groups.keys()];
  const common = new Set((keys[0] || '').split(' ').filter(word=>keys.every(key=>key.split(' ').includes(word))));
  return [...groups].map(([key, entries]) => {
    const distinct = key.split(' ').filter(word=>!common.has(word)).join(' ').replace(/\b([1-4])t\b/g, 'Q$1');
    return { key, label: distinct || (entries.every(r=>!r.years.length) ? 'Current / undated' : 'Published data'), resources: entries };
  });
}
export function seriesYears(series: DatasetSeries) {
  return [...new Set(series.resources.flatMap(r => r.years.length ? r.years : ['current']))]
    .sort((a,b) => a === 'current' ? -1 : b === 'current' ? 1 : b.localeCompare(a));
}
export function seriesResource(series: DatasetSeries, year: string) {
  return preferredResource(series.resources.filter(r => year === 'current' ? !r.years.length : r.years.includes(year)));
}
export const curatedDatasetIds: Record<string, 'accidents' | 'street-trees' | 'park-trees'> = {
  'accidents-gu-bcn': 'accidents', 'arbrat-viari': 'street-trees', 'arbrat-parcs': 'park-trees',
};
export const datasetTitles: Record<string, string> = {
  'accidents-gu-bcn': 'Traffic accidents', 'arbrat-viari': 'Street trees', 'arbrat-parcs': 'Park trees',
};
