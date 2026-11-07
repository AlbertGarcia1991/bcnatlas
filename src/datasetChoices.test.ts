import { describe, expect, it } from 'vitest';
import { datasetSeries, seriesResource, seriesYears } from './datasetChoices';
import type { CatalogResource } from './catalog';
const resource=(id:string,name:string,years:string[],format='CSV'):CatalogResource=>({id,name,years,format,url:'',modified:null,size:null,previewSupported:true});
describe('dataset editions',()=>{
  it('consolidates annual files and duplicate formats without combining observations',()=>{
    const series=datasetSeries([resource('a','2024_income.csv',['2024']),resource('b','2023_income.csv',['2023']),resource('c','2024_income.json',['2024'],'JSON')]);
    expect(series).toHaveLength(1);expect(seriesYears(series[0])).toEqual(['2024','2023']);expect(seriesResource(series[0],'2024')?.id).toBe('a');
  });
  it('keeps quarters and geographical breakdowns separate',()=>{
    const series=datasetSeries([resource('a','2024_4T_trees.csv.zip',['2024'],'ZIP'),resource('b','2023_4T_trees.json.zip',['2023'],'ZIP'),resource('c','2024_3T_trees.csv.zip',['2024'],'ZIP'),resource('d','2024_districts.csv',['2024']),resource('e','2024_neighbourhoods.csv',['2024'])]);
    expect(series).toHaveLength(4);expect(series[0].resources).toHaveLength(2);
  });
  it('handles current editions and excludes unsupported resources',()=>{
    const series=datasetSeries([resource('a','pharmacies.csv',[]),resource('b','pharmacies-js.json',[],'JSON'),{...resource('c','service',[],'WMS'),previewSupported:false}]);
    expect(series).toHaveLength(1);expect(seriesYears(series[0])).toEqual(['current']);expect(seriesResource(series[0],'2022')).toBeUndefined();
  });
  it('prefers a mirrored alternative format for a chosen year',()=>{
    const series=datasetSeries([{...resource('a','2024_income.csv',['2024']),available:false},resource('b','2024_income.json',['2024'],'JSON')]);
    expect(seriesResource(series[0],'2024')?.id).toBe('b');
  });
});
