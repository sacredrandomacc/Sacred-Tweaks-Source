"""Hosted adapter checks; PostgreSQL behavior is exercised in CI separately."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.service import Service


@unittest.skipUnless(importlib.util.find_spec('flask'), 'Install requirements.txt for hosted tests')
class HostedTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('server.hosted'), 'Hosted entry point is missing')
        from server.hosted import create_app
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = Service(Path(self.tmp.name) / 'test.db', password_cost=1024)
        self.app = create_app(lambda: self.service)
        self.client = self.app.test_client()

    def test_health_and_no_static_source_exposure(self):
        response = self.client.get('/v1/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.get('/server/service.py').status_code, 404)
        self.assertEqual(self.client.post('/v1/admin/bootstrap', json={}).status_code, 401)

    def test_input_and_method_limits(self):
        for value in ['{"a":1,"a":2}', '{"a":NaN}', '[]']:
            self.assertEqual(self.client.post('/v1/auth/login', data=value, content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post('/v1/auth/login', data='{}', content_type='text/plain').status_code, 415)
        self.assertEqual(self.client.post('/v1/auth/login', data='x'*65537, content_type='application/json').status_code, 413)
        self.assertEqual(self.client.put('/v1/health').status_code, 405)

    def test_database_failure_is_json_and_does_not_disclose_secret(self):
        from server.hosted import create_app
        def unavailable():
            raise RuntimeError('postgres://user:secret@host/db')
        response = create_app(unavailable).test_client().get('/v1/health')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json['code'], 'unavailable')
        self.assertNotIn('secret', response.get_data(as_text=True))

    def test_missing_database_url_fails_closed(self):
        from server.hosted import create_app
        with patch.dict(os.environ, {}, clear=True):
            response = create_app().test_client().get('/v1/health')
        self.assertEqual(response.status_code, 503)

    def test_bearer_auth_and_proxy_identity(self):
        setup = self.service.bootstrap_owner('owner', 'Owner-password-124!')
        login = self.client.post('/v1/auth/login', json={'username':'owner', 'password':'Owner-password-124!', 'device_id':'owner-device-12345678', 'recovery_code':setup['recovery_codes'][0]})
        self.assertEqual(login.status_code, 200)
        token = login.json['token']
        self.assertEqual(self.client.get('/v1/admin/overview', headers={'Authorization':'Bearer '+token}).status_code, 200)
        self.assertEqual(self.client.get('/v1/admin/overview').status_code, 401)
        self.client.get('/v1/health', headers={'X-Forwarded-For':'spoofed'})
        self.assertNotIn(('all','spoofed'), self.service.rates)
        with patch.dict(os.environ, {'VERCEL':'1'}):
            self.client.get('/v1/health', headers={'X-Vercel-Forwarded-For':'203.0.113.5', 'X-Forwarded-For':'spoofed'})
        self.assertIn(('all','203.0.113.5'), self.service.rates)
