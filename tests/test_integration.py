"""Real HTTP + desktop bridge + native authorization, without Windows input."""
from pathlib import Path
import tempfile
import threading
import unittest

from desktop.bridge import Api
from desktop.native import NativeTools
from server.http import make_server
from server.service import Service


class PassivePlatform:
    available = True
    error = None
    def start(self, callback, interested): pass
    def foreground(self): return False
    def game_running(self): return False
    def down(self, key): raise AssertionError('This integration test must not send input')
    def up(self, key): raise AssertionError('This integration test must not send input')
    def close(self): pass


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = Service(Path(self.tmp.name) / 'service.db', password_cost=1024)
        setup = self.service.bootstrap_owner('owner', 'Owner password 123!')
        status, self.owner = self.service.handle('POST', '/v1/auth/login', {'username':'owner','password':'Owner password 123!','device_id':'owner-device-test-12345','recovery_code':setup['recovery_codes'][0]})
        self.assertEqual(status, 200)
        status, licenses = self.service.handle('POST', '/v1/admin/licenses', {'tier':'Elite','duration_days':30,'count':1}, self.owner['token'])
        self.assertEqual(status, 200)
        self.key = licenses['keys'][0]
        self.server = make_server(self.service, port=0)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.native = NativeTools(Path(self.tmp.name) / 'native', platform=PassivePlatform())
        self.addCleanup(self.native.close)
        self.api = Api('member', self.tmp.name, f'http://127.0.0.1:{self.server.server_port}', self.native, device_id='member-device-test-12345', allow_http=True)

    def test_registration_macro_authorization_revocation_and_offline_restoration(self):
        result = self.api.request('POST', '/v1/auth/register', {'key':self.key,'username':'member','password':'Member password 123!'})
        self.assertTrue(result['ok'], result)
        self.assertNotIn('token', result['data'])
        self.assertEqual(len(result['data']['recovery_codes']), 10)
        configured = self.api.local('macro_configure', {'kind':'drag','config':{'edit':'G','select':'0','confirm':'G','emergency':'F8','confirm_mode':'manual'}})
        self.assertTrue(configured['ok'], configured)
        self.assertFalse(configured['data']['enabled'])
        self.assertTrue(self.api.local('macro_enable', {'enabled':True})['ok'])
        self.assertTrue(self.api.local('macro_status')['data']['enabled'])
        uid = result['data']['user']['id']
        status, details = self.service.handle('GET', f'/v1/admin/users/{uid}', token=self.owner['token'])
        self.assertEqual(status, 200)
        lid = details['license']['id']
        status, _ = self.service.handle('POST', f'/v1/admin/licenses/{lid}', {'action':'revoke'}, self.owner['token'])
        self.assertEqual(status, 200)
        denied = self.api.request('GET', '/v1/me')
        self.assertFalse(denied['ok'])
        self.assertFalse(self.api.local('macro_status')['data']['enabled'])
        self.assertTrue(self.api.local('backups')['ok'])
        self.assertFalse(self.api.local('macro_enable', {'enabled':True})['ok'])


if __name__ == '__main__':
    unittest.main()
