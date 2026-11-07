"""Publish and verify the app data assets; never uploads credentials or app source."""
import hashlib
import json
from datetime import datetime, timezone
from server import storage


def put_verified(bucket, key, raw, content_type='application/json'):
    digest = hashlib.sha256(raw).hexdigest()
    storage.client().put_object(Bucket=bucket, Key=key, Body=raw, ContentType=content_type,
        CacheControl='public, max-age=300', Metadata={'sha256':digest})
    actual, meta = storage.object_bytes(bucket, key, max(len(raw)+1, 1024))
    if hashlib.sha256(actual).hexdigest() != digest:
        raise RuntimeError('R2 verification failed for '+key)
    print(f'Verified {key} ({len(raw):,} bytes)', flush=True)


def main():
    for path in sorted((storage.ROOT/'public/data').glob('*.json')):
        if storage.valid_asset(path.name):
            put_verified(storage.public_bucket(), f'{storage.app_prefix()}/data/{path.name}', path.read_bytes())
    frozen = storage.ROOT/'.cache/r2-mirror'
    for name in ('catalog.json', 'service-references.json'):
        put_verified(storage.raw_bucket(), f'{storage.raw_prefix()}/{name}', (frozen/name).read_bytes())
    release={'version':'1.2.0','publishedAt':datetime.now(timezone.utc).isoformat(),
             'appPrefix':storage.app_prefix(),'rawPrefix':storage.raw_prefix()}
    put_verified(storage.public_bucket(), f'{storage.app_prefix()}/release.json',json.dumps(release).encode())

if __name__=='__main__': main()
