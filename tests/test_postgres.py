"""Run against a disposable PostgreSQL database named sacred_test only."""
import importlib.util
import os
import unittest
from urllib.parse import urlsplit
import test_server as existing

URL = os.environ.get('TEST_DATABASE_URL', '')

@unittest.skipUnless(URL, 'Set TEST_DATABASE_URL to a disposable sacred_test PostgreSQL database')
class PostgresTests(existing.ServiceTests):
    def make_service(self):
        self.assertEqual(urlsplit(URL).path, '/sacred_test', 'Refusing to reset a non-test database')
        self.assertIsNotNone(importlib.util.find_spec('server.postgres'), 'PostgreSQL service is missing')
        from server.postgres import PostgresService
        service = PostgresService(URL, clock=lambda: self.now, password_cost=1024)
        service.initialize_schema()
        with service.connect() as db:
            db.execute('TRUNCATE licenses, users, sessions, refresh_sessions, recovery_codes, reset_credentials, devices, transfers, profiles, content, feedback, audit, alerts, rate_limits RESTART IDENTITY CASCADE')
        return service

    def database_text(self):
        with self.svc.connect() as db:
            return repr([list(db.execute('SELECT * FROM '+table)) for table in ('users','licenses','sessions','recovery_codes','reset_credentials','audit')])

    def test_case_insensitive_username_uniqueness_and_login(self):
        member = self.register(username='MixedCase')
        self.call('POST','/v1/auth/logout',{},member['token'])
        self.assertEqual(self.login(username='mixedcase')['user']['username'], 'MixedCase')
        key = self.key()
        self.call('POST','/v1/auth/register',{'key':key,'username':'MIXEDCASE','password':'Member-password-123!','device_id':'other-device-12345678'},status=409)
        self.call('POST','/v1/license/validate',{'key':key})
        self.assertEqual(len(self.call('GET','/v1/admin/users?q=mixed',token=self.owner)['users']),1)

    def test_limits_shared_across_instances_and_survive_restart(self):
        from server.postgres import PostgresService
        from server.service import APIError
        second = PostgresService(URL,clock=lambda:self.now,password_cost=1024)
        for service in (self.svc,second):
            service._limit(('shared','test'),2,60)
        with self.assertRaises(APIError) as error:
            PostgresService(URL,clock=lambda:self.now,password_cost=1024)._limit(('shared','test'),2,60)
        self.assertEqual(error.exception.status,429)
        self.now += 61
        second._limit(('shared','test'),2,60)

    def test_schema_reinitialization_preserves_accounts(self):
        self.svc.initialize_schema()
        self.assertEqual(self.call('GET','/v1/me',token=self.owner)['user']['username'],'owner')
        with self.assertRaises(RuntimeError):
            self.svc.bootstrap_owner('another','Another-password-123!')
