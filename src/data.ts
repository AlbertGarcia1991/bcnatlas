export type LayerId = 'accidents' | 'street-trees' | 'park-trees';
export type Point = [number, number, number];
export type Snapshot = { file: string; count: number; excluded: number; sourceRows: number; resourceId: string; resourceName: string; url: string; period: string; sourceModified: string; sha256: string };
export type Manifest = { retrievedAt: string; years: number[]; datasets: Record<LayerId, { title: string; publisher: string; license: string; licenseUrl: string; url: string; years: Record<string, Snapshot> }> };
export const layers: { id: LayerId; title: string; description: string; color: string; colors: [string, string, string]; category: string }[] = [
  { id: 'accidents', title: 'Traffic accidents', description: 'Incidents recorded by the local police', color: '#b8323e', colors: ['#fff0b5', '#ffd23f', '#b8323e'], category: 'MOBILITY' },
  { id: 'street-trees', title: 'Street trees', description: 'The trees along our everyday routes', color: '#197bea', colors: ['#dcefff', '#19a0e5', '#0b3062'], category: 'URBAN NATURE' },
  { id: 'park-trees', title: 'Park trees', description: 'Tree inventories in the city’s parks', color: '#8a74bf', colors: ['#e0d4f2', '#a88cd4', '#66439c'], category: 'URBAN NATURE' },
];
export const districts = ['All Barcelona', 'Ciutat Vella', 'Eixample', 'Sants-Montjuïc', 'Les Corts', 'Sarrià-Sant Gervasi', 'Gràcia', 'Horta-Guinardó', 'Nou Barris', 'Sant Andreu', 'Sant Martí'];
export const centers: [number, number][] = [[2.166, 41.395], [2.177, 41.381], [2.163, 41.394], [2.145, 41.36], [2.125, 41.386], [2.124, 41.411], [2.156, 41.411], [2.152, 41.435], [2.176, 41.446], [2.19, 41.434], [2.202, 41.409]];
export const format = (n: number) => n.toLocaleString('en-GB');
export function filterPoints(points: Point[], district: number): Point[] { return district ? points.filter(p => p[2] === district) : points; }
export function distanceMeters(a: [number, number], b: [number, number]): number {
  const rad = Math.PI / 180;
  const x = Math.sin((b[1] - a[1]) * rad / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin((b[0] - a[0]) * rad / 2) ** 2;
  return 6371000 * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
}
export type Settings = { year: number; enabled: LayerId[]; district: number; radius: number; opacity: number; intensity: number; mode: 'heatmap' | 'points' };
export function readSettings(search: string): Settings {
  const q = new URLSearchParams(search);
  const numeric = (key: string, fallback: number, min: number, max: number) => { const n = q.has(key) ? Number(q.get(key)) : fallback; return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback; };
  return { year: Math.round(numeric('year', 2025, 1800, 2026)), enabled: q.has('layers') ? layers.filter(l => q.get('layers')!.split(',').includes(l.id)).map(l => l.id) : ['accidents'], district: Math.round(numeric('district', 0, 0, 10)), radius: numeric('radius', 22, 8, 50), opacity: numeric('opacity', 75, 20, 100), intensity: numeric('intensity', 1, .2, 3), mode: q.get('mode') === 'points' ? 'points' : 'heatmap' };
}
export function settingsQuery(s: Settings): string { return new URLSearchParams({ year: String(s.year), layers: s.enabled.join(','), district: String(s.district), radius: String(s.radius), opacity: String(s.opacity), intensity: String(s.intensity), mode: s.mode }).toString(); }
