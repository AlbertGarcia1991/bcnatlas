import { describe, it, expect } from 'vitest';
import { dataUrl } from './dataSource';
describe('remote data paths',()=>{
  it('routes metadata and legacy snapshot paths through the configured data service',()=>{
    expect(dataUrl('catalog.json')).toBe('/api/data/catalog.json');
    expect(dataUrl('/data/accidents-2025.json')).toBe('/api/data/accidents-2025.json');
  });
  it('does not accept query-string or credential paths',()=>{
    expect(()=>dataUrl('catalog.json?token=secret')).toThrow();
    expect(()=>dataUrl('.env.secrets')).toThrow();
  });
});
