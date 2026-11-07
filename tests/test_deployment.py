import asyncio
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from server import app as api
from server import storage

class ReadinessTests(unittest.TestCase):
    def test_readiness_reads_remote_catalog_and_exposes_no_credentials(self):
        with patch('server.storage.catalog', return_value={'count': 558}), patch('server.storage.source_mode', return_value='r2'):
            response = TestClient(api.app).get('/api/ready')
        self.assertEqual(response.json(), {'status': 'ok', 'dataSource': 'r2', 'datasets': 558})
    def test_readiness_fails_closed_on_storage_error(self):
        with patch('server.storage.catalog', side_effect=storage.StorageError('private endpoint')):
            response = TestClient(api.app).get('/api/ready')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private endpoint', response.text)

class AdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_parser_does_not_create_an_unbounded_wait_queue(self):
        catalog={'datasets': [{'id': 'example', 'resources': [{'id': 'resource', 'format': 'CSV'}]}]}
        with patch.object(api, 'slots', asyncio.Semaphore(0)), patch('server.storage.catalog', return_value=catalog), patch('asyncio.create_subprocess_exec') as spawn:
            with self.assertRaises(HTTPException) as caught:
                await api.resource('example', 'resource', None, None)
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.headers['Retry-After'], '3')
        spawn.assert_not_called()
