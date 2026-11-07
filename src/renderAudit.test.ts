import { expect, it } from 'vitest';
import { auditedCatalog, auditedCuratedLayers, auditedData, auditedSelection, type RenderAudit } from './renderAudit';
import type { Catalog, CatalogResource, ResourceData } from './catalog';
const evidence:RenderAudit={resources:{good:{sha256:'source-v1',cases:[{member:'data.csv',year:'2023',metrics:['income'],renderModes:['geometry']},{member:'data.csv',year:'2024',metrics:['income'],renderModes:['geometry']}]}}};
it('cannot restore a hidden legacy layer through a shared URL',()=>{
 expect(auditedCuratedLayers(['accidents','street-trees'],{'arbrat-viari':'street-trees'},{...evidence,excludedDatasets:['arbrat-viari']})).toEqual(['accidents']);
});
it('hides failed resources and removes datasets without a verified edition',()=>{
 const catalog={datasets:[{id:'partial',resources:[{id:'good'},{id:'bad'}]},{id:'failed',resources:[{id:'bad'}]}]} as unknown as Catalog;
 const filtered=auditedCatalog(catalog,evidence);
 expect(filtered.datasets.map(d=>d.id)).toEqual(['partial']);expect(filtered.datasets[0].resources.map(r=>r.id)).toEqual(['good']);
});
it('selects the newest audited year and rejects unverified selections',()=>{
 const resource={id:'good'} as CatalogResource;
 expect(auditedSelection(resource,'','',evidence)).toEqual({member:'data.csv',year:'2024'});
 expect(auditedSelection(resource,'','2023',evidence).year).toBe('2023');
 expect(()=>auditedSelection(resource,'broken.csv','',evidence)).toThrow('did not pass');
 expect(()=>auditedSelection(resource,'','2022',evidence)).toThrow('did not pass');
});
it('removes failing attributes and years and rejects changed source bytes',()=>{
 const resource={id:'good'} as CatalogResource;
 const data={sourceSha256:'source-v1',member:'data.csv',selectedYear:'2024',numericFields:[{name:'income'},{name:'broken'}],members:['data.csv','broken.csv'],years:['2022','2023','2024']} as ResourceData;
 const checked=auditedData(resource,data,evidence);
 expect(checked.numericFields.map(f=>f.name)).toEqual(['income']);expect(checked.years).toEqual(['2023','2024']);expect(checked.members).toEqual(['data.csv']);
 expect(()=>auditedData(resource,{...data,sourceSha256:'changed'},evidence)).toThrow('changed');
});
