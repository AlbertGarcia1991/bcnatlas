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

app=FastAPI(title='Barcelona Atlas catalog API',version='1.3.0',docs_url=None,redoc_url=None)
slots=asyncio.Semaphore(max(1, min(2, int(os.environ.get('BCN_PARSER_CONCURRENCY', '2')))))
# Process boundaries bound parser memory/failure and allow hard timeouts.
@app.get('/api/health')
def health(): return {'status':'ok','version':'1.3.0','dataSource':storage.source_mode()}

@app.get('/api/ready')
def ready():
    try:
        catalog = storage.catalog()
        return {'status': 'ok', 'dataSource': storage.source_mode(), 'datasets': catalog['count']}
    except (storage.StorageError, ValueError, KeyError):
        raise HTTPException(503, 'Data storage is not ready. Check the server configuration.')

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
async def resource(dataset_id:str,resource_id:str,member:str|None=Query(None,max_length=300),year:str|None=Query(None,pattern=r'^(19|20)\d{2}$'),filters:str='{}'):
    try:
        if len(filters) > 4096: raise ValueError()
        selected_filters = json.loads(filters)
        if not isinstance(selected_filters, dict) or len(selected_filters) > 12 or any(not isinstance(k,str) or not isinstance(v,str) or len(k)>200 or len(v)>500 for k,v in selected_filters.items()): raise ValueError()
    except (ValueError, TypeError): raise HTTPException(400, 'Invalid record filters.')
    try: catalog=await asyncio.to_thread(storage.catalog)
    except storage.StorageError as e: raise HTTPException(503,str(e))
    dataset=next((d for d in catalog['datasets'] if d['id']==dataset_id),None)
    selected=next((r for r in dataset['resources'] if r['id']==resource_id),None) if dataset else None
    if not selected: raise HTTPException(404,'Dataset/resource pair is not in the catalog snapshot.')
    selected = {**selected, '_dataset_id': dataset_id}
    if selected['format'].upper() not in SUPPORTED: raise HTTPException(422,'Preview is unavailable for this format. Use the original resource.')
    try:
        await asyncio.wait_for(slots.acquire(), timeout=0.1)
    except asyncio.TimeoutError:
        raise HTTPException(503, 'The preview service is busy. Please retry shortly.', headers={'Retry-After': '3'})
    try:
        env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'}
        process=await asyncio.create_subprocess_exec(sys.executable,'-m','server.worker',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,cwd=ROOT,env=env)
        try:
            out,err=await asyncio.wait_for(process.communicate(json.dumps({'resource':selected,'member':member,'year':year,'filters':selected_filters}).encode()),timeout=120)
        except (asyncio.TimeoutError,asyncio.CancelledError) as e:
            process.kill();await process.wait()
            if isinstance(e,asyncio.CancelledError): raise
            raise HTTPException(504,'Resource processing timed out. Please use the original download.')
        if process.returncode!=0: raise HTTPException(422,'The resource could not be parsed within the supported limits. Use its original download.')
        payload=json.loads(out)
        if 'error' in payload: raise HTTPException(422,payload['error'])
        return JSONResponse(payload,headers={'Cache-Control':'private, max-age=300'})
    finally:
        slots.release()

if (ROOT/'dist').exists(): app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='web')
