import {describe,it,expect} from 'vitest';
import {rankCorrelation} from './analytics';
describe('descriptive matrix',()=>{
 it('handles ties, monotonic transformations and constants',()=>{
  expect(rankCorrelation([1,1,2,4],[8,8,10,20])).toBeCloseTo(1);
  expect(rankCorrelation([1,2,3],[9,5,1])).toBeCloseTo(-1);
  expect(rankCorrelation([1,1,1],[1,2,3])).toBeNull();
 });
});
