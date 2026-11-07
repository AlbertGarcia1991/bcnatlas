"""Isolated reader process. stdout is one JSON result; errors are safe public messages."""
import json
import sys
import resource
from server.loader import fetch_resource, prepare, ResourceError
from server import storage
# Limit parser CPU and address space; API also enforces a wall-clock deadline.
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
resource.setrlimit(resource.RLIMIT_CPU,(100,100))
try:
    request=json.load(sys.stdin)
    key = None
    if storage.source_mode() == 'r2':
        key = storage.processed_key(request['resource'], request.get('member'), request.get('year'))
        cached = storage.read_processed(key)
        if cached is not None:
            print(json.dumps(cached, ensure_ascii=False, separators=(',', ':'), allow_nan=False))
            sys.exit(0)
    raw,retrieved=fetch_resource(request['resource'])
    result=prepare(raw,request['resource'],request.get('member'),request.get('year'))
    result['retrievedAt']=retrieved
    result['storageSource'] = 'Cloudflare R2' if storage.source_mode() == 'r2' else 'Municipal source'
    if key:
        result['notes'].append('Read from the R2 mirror. Retrieved date is the mirror upload time; source attribution and source checksum remain attached.')
        storage.write_processed(key, result)
    print(json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False))
except (ResourceError, storage.StorageError) as e: print(json.dumps({'error':str(e)}))
except Exception as e:
    print(type(e).__name__+': '+str(e),file=sys.stderr)
    print(json.dumps({'error':'This source uses a structure or coordinate system that needs a dedicated adapter. Open its original resource; no approximate data was substituted.'}))
