"""Local catalog API and production static host. Run via scripts/dev.mjs or uvicorn."""
import asyncio
import json
import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from server.loader import ResourceError, SUPPORTED, fetch_resource, prepare, ROOT
from server import storage

app=FastAPI(title='Barcelona Atlas catalog API',version='1.2.0',docs_url=None,redoc_url=None)
slots=asyncio.Semaphore(2)
# Process boundaries bound parser memory/failure and allow hard timeouts.
@app.get('/api/health')
def health(): return {'status':'ok','version':'1.2.0','dataSource':storage.source_mode()}

@app.get('/api/data/{name}')
def data_asset(name: str):
    try:
        raw, metadata = storage.asset(name)
        return Response(raw, media_type='application/json', headers={
            'Cache-Control': 'public, max-age=300', 'ETag': metadata.get('ETag', ''),
            'X-Data-Source': storage.source_mode(),
        })
    except storage.MissingObject as e: raise HTTPException(404, str(e))
    except storage.StorageError as e: raise HTTPException(503, str(e))


@app.get('/api/resource/{dataset_id}/{resource_id}')
async def resource(dataset_id:str,resource_id:str,member:str|None=Query(None,max_length=300),year:str|None=Query(None,pattern=r'^(19|20)\d{2}$')):
    try: catalog=await asyncio.to_thread(storage.catalog)
    except storage.StorageError as e: raise HTTPException(503,str(e))
    dataset=next((d for d in catalog['datasets'] if d['id']==dataset_id),None)
    selected=next((r for r in dataset['resources'] if r['id']==resource_id),None) if dataset else None
    if not selected: raise HTTPException(404,'Dataset/resource pair is not in the catalog snapshot.')
    selected = {**selected, '_dataset_id': dataset_id}
    if selected['format'].upper() not in SUPPORTED: raise HTTPException(422,'Preview is unavailable for this format. Use the original resource.')
    async with slots:
        env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
        process=await asyncio.create_subprocess_exec(sys.executable,'-m','server.worker',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,cwd=ROOT,env=env)
        try:
            out,err=await asyncio.wait_for(process.communicate(json.dumps({'resource':selected,'member':member,'year':year}).encode()),timeout=120)
        except (asyncio.TimeoutError,asyncio.CancelledError) as e:
            process.kill();await process.wait()
            if isinstance(e,asyncio.CancelledError): raise
            raise HTTPException(504,'Resource processing timed out. Please use the original download.')
        if process.returncode!=0: raise HTTPException(422,'The resource could not be parsed within the supported limits. Use its original download.')
        payload=json.loads(out)
        if 'error' in payload: raise HTTPException(422,payload['error'])
        return JSONResponse(payload,headers={'Cache-Control':'private, max-age=300'})

if (ROOT/'dist').exists(): app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='web')
