"""Reuse verified local originals to seed the exact mirrored resource identity."""
import hashlib
import json
from botocore.exceptions import ClientError
from server import storage

catalog=json.loads((storage.ROOT/'.cache/r2-mirror/catalog.json').read_text())
count=0
for dataset in catalog['datasets']:
    for resource in dataset['resources']:
        cache_key=hashlib.sha256((resource['id']+str(resource.get('modified'))).encode()).hexdigest()
        local=storage.ROOT/'.cache/resources'/cache_key
        if not local.is_file():continue
        key=f'{storage.raw_prefix()}/raw/{dataset["id"]}/{resource["id"]}/source'
        try:storage.client().head_object(Bucket=storage.raw_bucket(),Key=key);continue
        except ClientError as e:
            if e.response['Error']['Code'] not in ('404','NoSuchKey','NotFound'):raise
        raw=local.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        storage.client().put_object(Bucket=storage.raw_bucket(),Key=key,Body=raw,ContentType='application/octet-stream',Metadata={'sha256':digest,'source':'verified-local-download-cache'})
        returned,_=storage.object_bytes(storage.raw_bucket(),key,len(raw)+1)
        if hashlib.sha256(returned).hexdigest()!=digest:raise RuntimeError('Seed checksum mismatch')
        count+=1;print('Seeded and verified',dataset['id'],resource['name'],flush=True)
print('Seeded resources:',count)
