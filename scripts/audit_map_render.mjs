// Replay every parsed edition through the application's actual MapLibre renderer.
import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import zlib from 'node:zlib';
import {createHash} from 'node:crypto';
const shard=Number(process.argv[2]||0), shards=Number(process.argv[3]||1);
const only=new Set((process.env.AUDIT_RESOURCE_IDS||'').split(',').filter(Boolean));
const root=path.resolve('.cache/map-audit');
await fs.mkdir(path.join(root,'render-cache'),{recursive:true});
const rendererHash=createHash('sha256').update(await fs.readFile('src/mapOverlay.ts')).digest('hex');
async function writeResult(file, result){const temporary=file+'.tmp';await fs.writeFile(temporary,JSON.stringify(result));await fs.rename(temporary,file);}
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader','--js-flags=--max-old-space-size=1536']});
let page;
async function reset(){if(page)await page.close();page=await browser.newPage({viewport:{width:800,height:800}});await page.goto('http://127.0.0.1:5174/scripts/map-audit.html');await page.waitForFunction(()=>window.auditReady);}
await reset();
let count=0;let lastReport=0;
try{
 while(true){
  let found=false;
  const directories=await fs.readdir(path.join(root,'resources')).catch(()=>[]);
  for(const id of directories.filter(id=>(!only.size||only.has(id))&&parseInt(id.slice(0,8),16)%shards===shard)){
   let result;try{result=JSON.parse(await fs.readFile(path.join(root,'resources',id,'result.json'),'utf8'));}catch{continue;}
   let entries=result.cases.filter(c=>c.status==='parsed');
   if(process.argv.includes('--filters')){
    let filtered;try{filtered=JSON.parse(await fs.readFile(path.join(root,'resources',id,'filters.json'),'utf8'));}catch{continue;}
    entries=filtered.resourceError?[]:filtered.cases.filter(c=>c.status!=='failed').flatMap(c=>c.checks||[]).filter(c=>c.status==='parsed');
   }
   for(const entry of entries){
    const output=entry.payload.replace('.json.gz','.render.json');
    try{if(JSON.parse(await fs.readFile(output,'utf8')).rendererHash===rendererHash)continue;}catch{}
    found=true;
    try{
     const data=JSON.parse(zlib.gunzipSync(await fs.readFile(entry.payload)));
     const hash=createHash('sha256').update(rendererHash).update(JSON.stringify([data.geometry,data.numericFields,data.geometryTypes])).digest('hex');
     const cached=path.join(root,'render-cache',hash+'.json');
     let checked;
     try{checked={...JSON.parse(await fs.readFile(cached,'utf8')),identicalRenderInput:hash};}catch{
      const checks=await page.evaluate(data=>window.auditLayer(data),data);
      checked={rendererHash,checks,status:checks.every(c=>c.status==='passed')?'passed':'failed'};
      if(checked.status==='passed')await fs.writeFile(cached,JSON.stringify(checked));
     }
     await writeResult(output,checked);
    }catch(e){await writeResult(output,{rendererHash,status:'failed',error:String(e.message||e).slice(0,500)});await reset();}
    count++;if(count%5===0)await reset();
    global.gc?.();
    if(count%10===0)console.log(`Rendered ${count} editions`);
   }
  }
  let progress={};try{progress=JSON.parse(await fs.readFile(path.join(root,'progress.json'),'utf8'));}catch{}
  await writeResult(path.join(root,`${process.argv.includes('--filters')?'filter-':''}render-progress-${shard}.json`),{rendered:count,updatedAt:new Date().toISOString()});
  let filtersDone=true;if(process.argv.includes('--filters')){try{filtersDone=JSON.parse(await fs.readFile(path.join(root,'filter-progress.json'),'utf8')).complete;}catch{filtersDone=false;}}
  if(!found&&progress.done===progress.total&&filtersDone)break;
  if(Date.now()-lastReport>60000){console.log(`Rendered ${count} editions; parser ${progress.done||0}/${progress.total||'?'}`);lastReport=Date.now();}
  if(!found)await new Promise(r=>setTimeout(r,3000));
 }
}finally{await browser.close();}
