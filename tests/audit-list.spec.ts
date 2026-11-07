import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
const audit=JSON.parse(readFileSync(new URL('../config/map-render-audit.json',import.meta.url),'utf8')) as {excludedDatasets:string[];resources:Record<string,unknown>};
test('failed datasets are absent from both layer selectors',async({page})=>{
  const id=audit.excludedDatasets[0];expect(id).toBeTruthy();
  await page.goto('/');
  await page.getByRole('textbox',{name:'Search map layers'}).fill(id);
  await expect(page.locator('.dataset-card')).toHaveCount(0);
  await page.getByRole('button',{name:'Dataset catalog',exact:true}).click();
  await page.getByRole('textbox',{name:'Search all datasets'}).fill(id);
  await expect(page.locator('.catalog-item')).toHaveCount(0);
});
test('a retained dataset offers only its verified resource files',async({page,request})=>{
  const response=await request.get('/api/data/catalog.json');const catalog=await response.json();
  const dataset=catalog.datasets.find((d:{resources:{id:string}[]})=>d.resources.some(r=>audit.resources[r.id])&&d.resources.some(r=>!audit.resources[r.id]));
  expect(dataset).toBeTruthy();
  await page.goto('/');await page.getByRole('button',{name:'Dataset catalog',exact:true}).click();
  await page.getByRole('textbox',{name:'Search all datasets'}).fill(dataset.id);
  await page.locator('.catalog-item').getByText(dataset.title,{exact:true}).click();
  const ids=await page.getByLabel('Published resource',{exact:true}).locator('option').evaluateAll(options=>options.map(o=>(o as HTMLOptionElement).value));
  expect(ids.length).toBeGreaterThan(0);
  expect(ids.every(id=>!!audit.resources[id])).toBe(true);
  expect(ids.length).toBeLessThan(dataset.resources.length);
});
