import io
import json
import os
import unittest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from server import storage
from server.app import app
from server.loader import fetch_resource, ResourceError

class StorageTests(unittest.TestCase):
    def test_assets_allowlist_blocks_arbitrary_paths(self):
        for name in ['../.env.secrets','secrets.json','catalog.json/other','a/b.json']:
            self.assertFalse(storage.valid_asset(name))
        self.assertTrue(storage.valid_asset('catalog.json'))
        self.assertTrue(storage.valid_asset('accidents-2025.json'))
    def test_r2_mode_bypasses_disk_and_municipal_fetch(self):
        with patch('server.storage.source_mode',return_value='r2'), patch('server.storage.raw_resource',return_value=(b'real source', 'timestamp')) as r2, patch('server.loader.urllib.request.build_opener') as municipal:
            self.assertEqual(fetch_resource({'id':'test'}),(b'real source','timestamp'))
            r2.assert_called_once();municipal.assert_not_called()
    def test_missing_r2_object_never_silently_falls_back(self):
        with patch('server.storage.source_mode',return_value='r2'), patch('server.storage.raw_resource',side_effect=storage.MissingObject('Not mirrored')), patch('server.loader.urllib.request.build_opener') as municipal:
            with self.assertRaisesRegex(ResourceError,'Not mirrored'):fetch_resource({'id':'test'})
            municipal.assert_not_called()
    def test_read_bounds_and_closes_stream(self):
        body=io.BytesIO(b'too big');mock=MagicMock();mock.get_object.return_value={'ContentLength':7,'Body':body}
        with patch('server.storage.client',return_value=mock):
            with self.assertRaises(storage.StorageError):storage.object_bytes('bucket','key',3)
        self.assertTrue(body.closed)
    def test_missing_object_is_distinct_from_auth_failure(self):
        mock=MagicMock();mock.get_object.side_effect=ClientError({'Error':{'Code':'NoSuchKey'}},'GetObject')
        with patch('server.storage.client',return_value=mock):
            with self.assertRaises(storage.MissingObject):storage.object_bytes('bucket','key',100)
        mock.get_object.side_effect=ClientError({'Error':{'Code':'AccessDenied','Message':'secret endpoint details'}},'GetObject')
        with patch('server.storage.client',return_value=mock):
            with self.assertRaises(storage.StorageError) as caught:storage.object_bytes('bucket','key',100)
            self.assertNotIn('secret',str(caught.exception))
    def test_processed_key_changes_with_raw_version_and_filters(self):
        mock=MagicMock();mock.head_object.return_value={'ETag':'old'}
        resource={'_dataset_id':'sanitat-farmacies','id':'b89329ea-81ea-496c-9cd0-6758336e6c20'}
        with patch('server.storage.client',return_value=mock):
            first=storage.processed_key(resource,None,None)
            self.assertNotEqual(first,storage.processed_key(resource,None,'2023'))
            self.assertNotEqual(first,storage.processed_key(resource,None,None,{'Sexe':'F'}))
            mock.head_object.return_value={'ETag':'new'}
            self.assertNotEqual(first,storage.processed_key(resource,None,None))
    def test_api_serves_r2_data_without_credentials(self):
        with patch('server.storage.asset',return_value=(b'{"count":558}',{'ETag':'"hash"'})),patch('server.storage.source_mode',return_value='r2'):
            response=TestClient(app).get('/api/data/catalog.json')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['x-data-source'],'r2')
        self.assertEqual(response.json(),{'count':558})
    def test_asset_outage_returns_503(self):
        with patch('server.storage.asset',side_effect=storage.StorageError('R2 unavailable')):
            response=TestClient(app).get('/api/data/catalog.json')
        self.assertEqual(response.status_code,503)
    def test_resource_key_requires_known_identity(self):
        with self.assertRaises(storage.StorageError):storage.resource_key({'_dataset_id':'../../secrets','id':'anything'})
