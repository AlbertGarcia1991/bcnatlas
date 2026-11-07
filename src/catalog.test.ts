import { describe, it, expect } from 'vitest';
import { filteredGeometry, preferredResource, type CatalogOverlay, type CatalogResource } from './catalog';

describe('catalog spatial selections', () => {
  it('keeps a cross-district street in each intersected district', () => {
    const features = [
      {type:'Feature',properties:{_district:0,_districts:[2,4]},geometry:{type:'LineString',coordinates:[[2.15,41.38],[2.17,41.40]]}},
      {type:'Feature',properties:{_district:1},geometry:{type:'Point',coordinates:[2.17,41.39]}},
    ];
    const overlay = {data:{hasDistrict:true,geometry:{type:'FeatureCollection',features}}} as unknown as CatalogOverlay;
    expect(filteredGeometry(overlay,2).features).toEqual([features[0]]);
    expect(filteredGeometry(overlay,4).features).toEqual([features[0]]);
    expect(filteredGeometry(overlay,1).features).toEqual([features[1]]);
    expect(filteredGeometry(overlay,0).features).toEqual(features);
  });
  it('prefers a supported available resource over an unmirrored newer year', () => {
    const resources = [
      {id:'new',format:'CSV',years:['2026'],previewSupported:true,available:false},
      {id:'available',format:'CSV',years:['2025'],previewSupported:true,available:true},
    ] as CatalogResource[];
    expect(preferredResource(resources).id).toBe('available');
  });
});
