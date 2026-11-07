"""Publish immutable derived evidence; upload manifest last."""
import concurrent.futures,gzip,hashlib,json
from scripts.analytics.analyse import OUT,ROOT
from server import storage

def upload(path):
    raw=path.read_bytes();name=str(path.relative_to(OUT));encoded=not name.endswith('.gz')
    data=gzip.compress(raw,mtime=0) if encoded else raw
    prefix=json.loads((ROOT/'config/analytics-release.json').read_text())['prefix']
    args={'Bucket':storage.public_bucket(),'Key':prefix+'/'+name,'Body':data,'ContentType':'application/json' if encoded else 'application/gzip','CacheControl':'public, max-age=300','Metadata':{'sha256':hashlib.sha256(raw).hexdigest()}}
    if encoded:args['ContentEncoding']='gzip'
    storage.client().put_object(**args)
    return name

def main():
    manifest=json.loads((OUT/'manifest.json').read_text())
    names=['top-associations.json','diagnostics.json','variables.json.gz','variable-inventory.json.gz']
    for period,meta in manifest['periods'].items():
        names.append(f'variables/{period}.json')
        names.extend(f'pairs/{period}-{shard}.json' for shard in meta['shards'])
    files=[OUT/name for name in names]
    if not all(path.is_file() for path in files):raise ValueError('Evidence bundle is incomplete')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i,name in enumerate(pool.map(upload,files),1):
            if i%25==0:print(f'Published {i}/{len(files)} analytics assets',flush=True)
    upload(OUT/'manifest.json');print('Published manifest last',flush=True)
if __name__=='__main__':main()
