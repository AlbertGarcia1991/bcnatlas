"""Server-only R2 access. Credentials never enter the browser or API responses."""
import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
for filename in ('.env.local', '.env.secrets'):
    load_dotenv(ROOT / filename, override=False)

PARSER_VERSION = '2'

class StorageError(Exception): pass
class MissingObject(StorageError): pass


def source_mode():
    mode = os.environ.get('BCN_DATA_SOURCE', 'local')
    if mode not in ('local', 'r2'):
        raise StorageError('BCN_DATA_SOURCE must be local or r2.')
    return mode


def raw_bucket(): return os.environ.get('BCN_R2_RAW_BUCKET', 'bcn-atlas-raw')
def public_bucket(): return os.environ.get('BCN_R2_PUBLIC_BUCKET', 'bcn-atlas-public')
def raw_prefix(): return os.environ.get('BCN_R2_RAW_PREFIX', 'snapshots/initial-2026-11-07').strip('/')
def app_prefix(): return os.environ.get('BCN_R2_APP_PREFIX', 'app/v1.2.0').strip('/')


@lru_cache(maxsize=1)
def client():
    required = ['CLOUDFLARE_R2_S3_ENDPOINT', 'CLOUDFLARE_R2_ACCESS_KEY_ID', 'CLOUDFLARE_R2_ACCESS_KEY_SECRET']
    if not all(os.environ.get(name) for name in required):
        raise StorageError('R2 is selected but server credentials are not configured.')
    return boto3.client('s3', endpoint_url=os.environ[required[0]],
                        aws_access_key_id=os.environ[required[1]],
                        aws_secret_access_key=os.environ[required[2]], region_name='auto',
                        config=Config(connect_timeout=10, read_timeout=35,
                                      retries={'max_attempts': 3, 'mode': 'standard'}, max_pool_connections=8))


def object_bytes(bucket, key, limit):
    try:
        response = client().get_object(Bucket=bucket, Key=key)
        try:
            if response['ContentLength'] > limit:
                raise StorageError('The R2 resource exceeds the interactive size limit. Use the original download.')
            data = response['Body'].read(limit + 1)
            if len(data) > limit:
                raise StorageError('The R2 resource exceeds the interactive size limit.')
        finally:
            response['Body'].close()
        return data, response
    except ClientError as e:
        if e.response['Error']['Code'] in ('NoSuchKey', '404', 'NotFound'):
            raise MissingObject('This resource is not yet available in the R2 mirror. Use the original download or retry after the mirror completes.') from e
        raise StorageError('R2 could not serve this resource. Check server credentials and bucket access.') from e
    except BotoCoreError as e:
        raise StorageError('R2 is temporarily unreachable. Please retry shortly.') from e


def valid_asset(name):
    return bool(re.fullmatch(r'(catalog|manifest|mirror-status)\.json|(?:accidents|street-trees|park-trees)-\d{4}\.json', name))


def asset(name):
    if not valid_asset(name): raise MissingObject('Unknown data asset.')
    if source_mode() == 'local':
        path = ROOT / 'public/data' / name
        if not path.exists(): raise MissingObject('Data asset is unavailable.')
        data = path.read_bytes()
        return data, {'ETag': '"' + hashlib.sha256(data).hexdigest() + '"'}
    return object_bytes(public_bucket(), f'{app_prefix()}/data/{name}', 24 * 1024 * 1024)


def catalog():
    return json.loads(asset('catalog.json')[0])


def resource_key(resource):
    dataset = resource.get('_dataset_id', '')
    rid = resource.get('id', '')
    if not re.fullmatch(r'[a-z0-9_-]+', dataset) or not re.fullmatch(r'[a-f0-9-]{36}', rid):
        raise StorageError('R2 resource identity is missing or invalid.')
    return f'{raw_prefix()}/raw/{dataset}/{rid}/source'


def raw_resource(resource, limit):
    data, response = object_bytes(raw_bucket(), resource_key(resource), limit)
    return data, response['LastModified'].isoformat()


def processed_key(resource, member, year):
    # Raw ETag invalidates derived data when a mirrored source changes.
    try:
        head = client().head_object(Bucket=raw_bucket(), Key=resource_key(resource))
    except ClientError as e:
        if e.response['Error']['Code'] in ('NoSuchKey', '404', 'NotFound'):
            raise MissingObject('This resource is not yet available in the R2 mirror.') from e
        raise StorageError('Unable to check the R2 source version.') from e
    except BotoCoreError as e:
        raise StorageError('R2 is temporarily unreachable. Please retry shortly.') from e
    identity = json.dumps([PARSER_VERSION, raw_prefix(), resource['id'], head['ETag'], member, year], separators=(',', ':'))
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return f'processed/v{PARSER_VERSION}/{resource["id"]}/{digest}.json'


def read_processed(key):
    try: return json.loads(object_bytes(public_bucket(), key, 48 * 1024 * 1024)[0])
    except MissingObject: return None


def write_processed(key, payload):
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    client().put_object(Bucket=public_bucket(), Key=key, Body=raw, ContentType='application/json',
                        CacheControl='public, max-age=31536000, immutable',
                        Metadata={'sha256': hashlib.sha256(raw).hexdigest(), 'parser-version': PARSER_VERSION})
