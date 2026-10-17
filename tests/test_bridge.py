import tempfile
import threading
import unittest
from desktop.bridge import Api, ApiError, validate_api_url


class FakeNative:
    def __init__(self):
        self.permissions, self.deadline, self.stops = {}, 0, []
    def set_authorization(self, permissions, enforced, deadline):
        self.permissions, self.deadline = permissions, deadline
    def stop(self, reason):
        self.stops.append(reason)
    def call(self, action, payload):
        return {"action": action}
    def close(self):
        pass


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.native = FakeNative()
        self.now = 100
        self.session = {"token": "private-token", "user": {"id": 1, "username": "Tester", "role": "member"}, "tier": "Core", "permissions": {"single_edit": True}, "enforced": {}, "lease_seconds": 25}
        self.api = Api("member", self.tmp.name, "https://api.example.com", self.native, device_id="test-device", transport=self.transport, clock=lambda: self.now)
    def transport(self, method, path, data, token):
        if path == "/v1/auth/login":
            self.assertEqual(data["device_id"], "test-device")
            return self.session.copy()
        return {"lease_seconds": 25}
    def login(self):
        return self.api.request("POST", "/v1/auth/login", {"username": "Tester", "password": "secret"})
    def test_token_never_exposed_and_deadline_enforced(self):
        result = self.login()
        self.assertTrue(result["ok"])
        self.assertNotIn("token", result["data"])
        self.assertEqual(self.native.deadline, 125)
        self.now = 126
        self.assertFalse(self.api.local("macro_enable", {"enabled": True})["ok"])
        self.assertTrue(self.api.local("restore", {"backup_id": "a"})["ok"])
    def test_manager_rejects_member_and_logs_it_out(self):
        self.api._mode = "manager"
        result = self.login()
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "owner_required")
        self.assertIsNone(self.api._token)
    def test_heartbeat_retains_login_permission_snapshot(self):
        self.login()
        self.api._transport = lambda *args: {"permissions": {"single_edit": False}, "lease_seconds": 25}
        self.now = 110
        self.api._renew_once()
        self.assertTrue(self.native.permissions["single_edit"])
        self.assertEqual(self.native.deadline, 135)
    def test_logout_ignores_late_heartbeat_response(self):
        self.login()
        started, release = threading.Event(), threading.Event()
        def delayed(*args):
            started.set()
            release.wait(2)
            return {"lease_seconds": 25}
        self.api._transport = delayed
        worker = threading.Thread(target=self.api._renew_once)
        worker.start()
        self.assertTrue(started.wait(1))
        self.api._clear("Signed out")
        release.set()
        worker.join(2)
        self.assertEqual(self.native.deadline, 0)
        self.assertIsNone(self.api._token)
    def test_network_failure_stops_and_does_not_resume(self):
        self.login()
        def fail(*args):
            raise ApiError("offline", "disconnected")
        self.api._transport = fail
        self.api._renew_once()
        self.assertEqual(self.native.deadline, 0)
        self.assertFalse(self.api.local("macro_enable", {"enabled": True})["ok"])
    def test_alternate_auth_paths_are_rejected_before_transport(self):
        calls = []
        self.api._transport = lambda *args: calls.append(args)
        for route in ('login', 'register'):
            for suffix in ('/', '?', '?x=1', '#x', '%2f', '\t'):
                for mode in ('manager', 'member'):
                    self.api._mode = mode
                    result = self.api.request('POST', '/v1/auth/' + route + suffix, {})
                    self.assertFalse(result['ok'])
                    self.assertNotIn('private-token', str(result))
        self.assertFalse(self.api.request('GET', '/v1/auth/login')['ok'])
        self.assertEqual(calls, [])

    def test_encoded_member_search_query_remains_supported(self):
        self.login()
        result = self.api.request('GET', '/v1/admin/users?q=Example%20Name')
        self.assertTrue(result['ok'])

    def test_old_request_failure_cannot_clear_new_login(self):
        self.login()
        started, release = threading.Event(), threading.Event()
        def transport(method, path, data, token):
            if path == '/v1/me':
                started.set()
                release.wait(2)
                raise ApiError('Old session expired', 'session_expired', 401)
            return self.transport(method, path, data, token)
        self.api._transport = transport
        worker = threading.Thread(target=lambda: self.api.request('GET', '/v1/me'))
        worker.start()
        self.assertTrue(started.wait(1))
        self.api._clear('Signed out')
        self.assertTrue(self.login()['ok'])
        release.set()
        worker.join(2)
        self.assertEqual(self.api._token, 'private-token')
        self.assertEqual(self.native.deadline, 125)

    def test_conditional_clear_is_atomic_and_preserves_newer_session(self):
        self.login()
        generation = self.api._generation
        self.api._clear('Signed out')
        self.login()
        self.api._clear('Late heartbeat failure', generation)
        self.assertEqual(self.api._token, 'private-token')

    def test_bootstrap_reads_valid_persisted_appearance(self):
        import json
        from pathlib import Path
        theme = {'intensity': .25, 'accent': '#123abc', 'lightweight': True, 'reduced_motion': True}
        target = Path(self.tmp.name) / 'theme.json'
        target.write_text(json.dumps(theme))
        result = self.api.bootstrap()['data']
        self.assertEqual(result['theme']['intensity'], .25)
        self.assertTrue(result['reduced_motion'])
        target.write_text('{broken')
        self.assertNotIn('theme', self.api.bootstrap()['data'])

    def test_widget_pair_requires_session_and_is_revoked_on_logout(self):
        self.assertFalse(self.api.local('overlay_pair')['ok'])
        self.login()
        pair = self.api.local('overlay_pair')['data']
        self.addCleanup(self.api._overlay.close)
        self.assertNotIn('private-token', str(pair))
        self.assertEqual(self.api._overlay.token, pair['token'])
        self.api._clear('Signed out')
        self.assertNotEqual(self.api._overlay.token, pair['token'])
        self.assertFalse(self.api.local('macro_enable', {'enabled':True})['ok'])

    def test_urls_disallow_insecure_nonlocal_and_embedded_credentials(self):
        for url in ["http://example.com", "https://a:b@example.com", "https://example.com/path", "https://example.com#x"]:
            with self.assertRaises(ValueError):
                validate_api_url(url, True)
        self.assertEqual(validate_api_url("http://127.0.0.1:8765", True), "http://127.0.0.1:8765")


if __name__ == "__main__":
    unittest.main()
