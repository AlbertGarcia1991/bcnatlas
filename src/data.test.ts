import { describe, it, expect } from 'vitest';
import { readSettings, settingsQuery, distanceMeters, filterPoints, type Point } from './data';
describe('URL state', () => {
  it('round trips a multi-layer view, including controls', () => {
    const state = readSettings('?year=2023&layers=street-trees,park-trees&district=2&radius=40&opacity=60&intensity=1.5&mode=points');
    expect(readSettings(settingsQuery(state))).toEqual(state);
    expect(state.enabled).toEqual(['street-trees', 'park-trees']);
  });
  it('clamps invalid parameters and rejects unknown layers', () => {
    expect(readSettings('?year=NaN&district=999&radius=-4&opacity=Infinity&layers=bad,accidents')).toMatchObject({ year: 2025, district: 10, radius: 8, opacity: 75, enabled: ['accidents'] });
  });
  it('retains an intentionally empty selection', () => { expect(readSettings('?layers=').enabled).toEqual([]); });
});
describe('spatial analysis', () => {
  it('uses metre distances and handles coincident records', () => {
    expect(distanceMeters([2.17, 41.39], [2.17, 41.39])).toBe(0);
    expect(distanceMeters([2.17, 41.39], [2.17, 41.40])).toBeCloseTo(1111.95, 0);
    expect(distanceMeters([2.17, 41.39], [2.17, 41.391])).toBeLessThan(300);
  });
  it('filters by source district without dropping coincident records', () => {
    const points: Point[] = [[2.17, 41.39, 2], [2.17, 41.39, 2], [2.18, 41.38, 1], [2.15, 41.40, 0]];
    expect(filterPoints(points, 2)).toHaveLength(2);
    expect(filterPoints(points, 0)).toHaveLength(4);
  });
});
