import { test, expect } from '@playwright/test';

// Live, official resources exercise UTF-16 CSV, projected GeoJSON and GPKG.
// Downloads are cached by the backend; no mocked geographic records are used.
test('catalog searches all datasets, previews pharmacies, restores and exports a layer', async ({page})=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await page.getByRole('button',{name:'Dataset catalog',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Find another perspective.'});
  await expect(dialog).toContainText('558 datasets');
  await expect(dialog).toContainText('6,825 published resources');
  await page.getByRole('textbox',{name:'Search all datasets'}).fill('sanitat-farmacies');
  await page.locator('.catalog-item').click();
  await expect(page.getByRole('region',{name:'Dataset details'})).toContainText('Pharmacies');
  await page.getByRole('button',{name:'Preview resource',exact:true}).click();
  await expect(page.locator('.preview-stats')).toContainText('1,135',{timeout:120000});
  await page.getByRole('button',{name:/Show table preview/}).click();
  await expect(page.locator('.table-scroll table')).toContainText('geo_epgs_4326_lat');
  await page.getByRole('button',{name:'Add to map',exact:true}).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.locator('.overlay-card')).toContainText('Pharmacies');
  await expect(page.locator('.overlay-card')).toContainText('Undated / current');
  await page.getByLabel('Explore an area').selectOption('2');
  await expect(page.locator('.overlay-card')).not.toContainText('1,135 features');
  const download=page.waitForEvent('download');await page.getByRole('button',{name:/Export Pharmacies/}).click();
  expect((await download).suggestedFilename()).toContain('.geojson');
  await page.reload();
  await expect(page.locator('.overlay-card')).toContainText('Pharmacies',{timeout:120000});
  await page.getByRole('button',{name:/Hide Pharmacies/}).click();
  await expect(page.locator('.map-footer')).toContainText('0 catalog overlays');
  await page.getByRole('button',{name:/Remove Pharmacies/}).click();
  await expect(page.locator('.overlay-card')).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('line and polygon geometry with metric coloring',async({page})=>{
  test.setTimeout(180000);
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  await page.goto('/?layers=');
  await page.getByRole('button',{name:'Dataset catalog',exact:true}).click();
  await page.getByRole('textbox',{name:'Search all datasets'}).fill('carril-bici');
  await page.locator('.catalog-item').filter({hasText:'Bicycle lanes of the city of Barcelona'}).click();
  // Choose the current GeoJSON explicitly instead of historical ZIP archives.
  const option=await page.locator('select[aria-label="Published resource"] option').evaluateAll(nodes=>nodes.find(n=>n.textContent?.startsWith('CARRIL_BICI.geojson'))?.getAttribute('value'));
  await page.getByLabel('Published resource',{exact:true}).selectOption(option!);
  await page.getByRole('button',{name:'Preview resource',exact:true}).click();
  await expect(page.locator('.preview-stats')).toContainText('LineString',{timeout:120000});
  await page.getByRole('button',{name:'Add to map',exact:true}).click();
  await expect(page.locator('.overlay-card')).toContainText('Bicycle lanes');
  await page.getByRole('button',{name:'Dataset catalog',exact:true}).click();
  await page.getByRole('textbox',{name:'Search all datasets'}).fill('poblacio-vulnerable');
  await page.locator('.catalog-item').click();
  await page.getByRole('button',{name:'Preview resource',exact:true}).click();
  await expect(page.locator('.preview-stats')).toContainText('Polygon',{timeout:120000});
  await page.getByRole('button',{name:'Add to map',exact:true}).click();
  await expect(page.locator('.overlay-card')).toHaveCount(2);
  const attribute=page.locator('.overlay-metric select').last();
  await attribute.selectOption({index:1});
  await expect(page.locator('.overlay-legend').last()).toContainText('d_');
  await page.waitForTimeout(1800);
  await page.screenshot({path:'test-results/catalog-map.png',fullPage:true});
  expect(errors).toEqual([]);
});

test('unsupported and failed resources remain explicitly linked to source',async({page})=>{
  await page.goto('/');await page.getByRole('button',{name:'Dataset catalog',exact:true}).click();
  await page.getByRole('textbox',{name:'Search all datasets'}).fill('mapa-acustic-wms');
  await page.locator('.catalog-item').click();
  await expect(page.getByRole('button',{name:'Preview resource',exact:true})).toBeDisabled();
  await expect(page.getByRole('link',{name:'Original download'})).toHaveAttribute('href',/^https:\/\/opendata-ajuntament.barcelona.cat/);
  await page.getByRole('textbox',{name:'Search all datasets'}).fill('sanitat-farmacies');
  await page.locator('.catalog-item').click();
  await page.route('**/api/resource/**',route=>route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({detail:'Resource exceeds the preview limit. Download the original.'})}));
  await page.getByRole('button',{name:'Preview resource',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('exceeds the preview limit');
  await expect(page.getByRole('button',{name:'Add to map',exact:true})).toHaveCount(0);
});

test('catalog works on a narrow screen',async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.goto('/');
  await page.getByRole('button',{name:'Dataset catalog',exact:true}).click();
  await page.getByRole('textbox',{name:'Search all datasets'}).fill('xarxa-refugis');
  await page.locator('.catalog-item').click();
  await expect(page.getByRole('region',{name:'Dataset details'})).toContainText('Climate shelters');
  await page.screenshot({path:'test-results/catalog-mobile.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole('button',{name:'Close dataset catalog',exact:true}).click();
  await expect(page.getByRole('button',{name:'Dataset catalog',exact:true})).toBeFocused();
});

test('income data stays a table and exposes its true record year',async({page})=>{
  await page.goto('/');await page.getByRole('button',{name:'Dataset catalog',exact:true}).click();
  await page.getByRole('textbox',{name:'Search all datasets'}).fill('renda-disponible-llars-bcn');
  await page.locator('.catalog-item').click();
  await page.getByRole('button',{name:'Preview resource',exact:true}).click();
  await expect(page.locator('.preview-stats')).toContainText('Table',{timeout:120000});
  await expect(page.getByRole('button',{name:'Add to map',exact:true})).toBeDisabled();
  await expect(page.getByLabel('Record year')).toContainText('2023');
  await page.getByLabel('Record year').selectOption('2023');
  await expect(page.locator('.preview-stats')).toContainText('1,068',{timeout:120000});
  await page.getByRole('button',{name:/Show table preview/}).click();
  await expect(page.locator('.table-scroll')).toContainText('Import_Euros');
  await expect(page.locator('.resource-notes')).toContainText('no locations have been invented');
});
