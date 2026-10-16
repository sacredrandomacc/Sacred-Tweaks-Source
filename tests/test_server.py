import base64
import concurrent.futures
import hashlib
import hmac
import json
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path

from server.service import Service


def totp(secret, now):
    key = base64.b32decode(secret + '=' * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack('>Q', int(now) // 30), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return str((struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff) % 1000000).zfill(6)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'db.sqlite3'
        self.now = 1800000000.0
        self.svc = Service(self.path, clock=lambda: self.now, password_cost=1024)
        setup = self.svc.bootstrap_owner('owner', 'Owner-password-124!')
        self.owner_setup = setup
        self.owner = self.call('POST', '/v1/auth/login', {'username': 'owner', 'password': 'Owner-password-124!', 'device_id': 'owner-device-12345678', 'totp': totp(setup['totp_secret'], self.now)})['token']

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, method, path, data=None, token=None, status=200, ip='test'):
        code, body = self.svc.handle(method, path, data, token, ip)
        self.assertEqual(code, status, body)
        return body

    def key(self, tier='Core', days=1):
        return self.call('POST', '/v1/admin/licenses', {'tier': tier, 'duration_days': days, 'count': 1}, self.owner)['keys'][0]

    def register(self, tier='Core', days=1, username='member', key=None):
        return self.call('POST', '/v1/auth/register', {'key': key or self.key(tier, days), 'username': username, 'password': 'Member-password-123!', 'device_id': 'member-device-12345678'})

    def user_action(self, user, action, **extra):
        return self.call('POST', f'/v1/admin/users/{user}', {'action': action, **extra}, self.owner)

    def login(self, **extra):
        return self.call('POST', '/v1/auth/login', {'username': 'member', 'password': 'Member-password-123!', 'device_id': 'member-device-12345678', **extra})

    def test_redemption_starts_timer_and_only_one_concurrent_claim(self):
        key = self.key(days=2)
        self.now += 86400
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda n: self.svc.handle('POST', '/v1/auth/register', {'key': key, 'username': f'member{n}', 'password': 'Member-password-123!', 'device_id': f'member-device-{n:016}'}, ip=f'worker{n}'), range(8)))
        winners = [body for status, body in results if status == 200]
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0]['expires_at'], self.now + 2 * 86400)
        self.assertTrue(all(status in (200, 409) for status, _ in results))
        self.assertNotIn(key, self.path.read_bytes().decode('latin1'))

    def test_permission_overrides_wait_for_next_login_and_enforced_settings(self):
        s = self.register()
        license_id = self.call('GET', f"/v1/admin/users/{s['user']['id']}", token=self.owner)['license']['id']
        self.call('POST', f'/v1/admin/licenses/{license_id}', {'action': 'update', 'tier': 'Elite', 'overrides': {'drag': False, 'filter_keys': True}, 'enforced': {'single_edit': {'repeat_ms': 200}}}, self.owner)
        heart = self.call('POST', '/v1/session/heartbeat', {}, s['token'])
        self.assertEqual(heart['tier'], 'Core')
        self.assertFalse(heart['permissions']['filter_keys'])
        self.call('POST', '/v1/auth/logout', {}, s['token'])
        s = self.login()
        self.assertTrue(s['permissions']['filter_keys'])
        self.assertFalse(s['permissions']['drag'])
        self.assertEqual(self.call('POST', '/v1/tools/authorize', {'feature': 'single_edit', 'settings': {'repeat_ms': 1}}, s['token'])['settings']['repeat_ms'], 200)
        self.call('POST', '/v1/tools/authorize', {'feature': 'drag'}, s['token'], status=403)

    def test_every_tier_permissions(self):
        expected = {'Core': 4, 'Plus': 5, 'Pro': 7, 'Elite': 11}
        for tier, allowed in expected.items():
            with self.subTest(tier=tier):
                s = self.register(tier=tier, username=tier.lower())
                self.assertEqual(sum(s['permissions'].values()), allowed)

    def test_one_device_one_session_and_transfer_revocation(self):
        s = self.register()
        self.call('POST', '/v1/auth/login', {'username': 'member', 'password': 'Member-password-123!', 'device_id': 'member-device-12345678'}, status=409)
        self.call('POST', '/v1/device/request', {'username': 'member', 'password': 'Member-password-123!', 'device_id': 'new-device-123456789', 'reason': 'new computer'})
        transfer = self.call('GET', '/v1/admin/transfers', token=self.owner)['transfers'][0]
        self.call('POST', f"/v1/admin/transfers/{transfer['id']}", {'approve': True}, self.owner)
        self.call('GET', '/v1/me', token=s['token'], status=401)
        self.call('POST', '/v1/auth/login', {'username': 'member', 'password': 'Member-password-123!', 'device_id': 'member-device-12345678'}, status=403)
        new = self.login(device_id='new-device-123456789')
        self.assertEqual(new['expires_at'], s['expires_at'])
        self.assertTrue(self.call('GET', '/v1/admin/overview', token=self.owner)['alerts'])

    def test_recovery_is_single_use_revokes_sessions_and_does_not_extend_license(self):
        s = self.register()
        body = {'username': 'member', 'recovery_code': s['recovery_codes'][0], 'new_password': 'New-password-123!'}
        self.call('POST', '/v1/auth/recover', body)
        self.call('GET', '/v1/me', token=s['token'], status=401)
        self.call('POST', '/v1/auth/recover', body, status=401)
        new = self.login(password='New-password-123!')
        self.assertEqual(new['expires_at'], s['expires_at'])

    def test_owner_reset_single_use_and_expiry(self):
        s = self.register()
        result = self.user_action(s['user']['id'], 'reset_password')
        body = {'username': 'member', 'reset_token': result['reset_token'], 'new_password': 'Reset-password-123!'}
        self.call('POST', '/v1/auth/recover', body)
        self.call('POST', '/v1/auth/recover', body, status=401)
        self.assertNotIn(result['reset_token'], self.path.read_bytes().decode('latin1'))

    def test_recovery_regeneration_invalidates_old_set(self):
        s = self.register()
        replacement = self.call('POST', '/v1/auth/recovery-codes', {'password': 'Member-password-123!'}, s['token'])
        self.call('POST', '/v1/auth/recover', {'username': 'member', 'recovery_code': s['recovery_codes'][0], 'new_password': 'New-password-123!'}, status=401)
        self.call('POST', '/v1/auth/recover', {'username': 'member', 'recovery_code': replacement['recovery_codes'][0], 'new_password': 'New-password-123!'})

    def test_owner_mfa_and_admin_authorization(self):
        member = self.register()
        for path in ['/v1/admin/users', '/v1/admin/licenses', '/v1/admin/audit', '/v1/admin/overview', '/v1/admin/content', '/v1/admin/feedback', '/v1/admin/settings', '/v1/admin/transfers']:
            self.call('GET', path, token=member['token'], status=403)
            self.call('GET', path, status=401)
        self.call('POST', '/v1/admin/licenses', {'tier': 'Elite', 'count': 1}, member['token'], status=403)
        self.call('POST', '/v1/auth/logout', {}, self.owner)
        self.call('POST', '/v1/auth/login', {'username': 'owner', 'password': 'Owner-password-124!', 'device_id': 'owner-device-12345678'}, status=401)
        self.call('POST', '/v1/auth/login', {'username': 'owner', 'password': 'Owner-password-124!', 'device_id': 'owner-device-12345678', 'totp': totp(self.owner_setup['totp_secret'], self.now)}, status=401)
        result = self.call('POST', '/v1/auth/login', {'username': 'owner', 'password': 'Owner-password-124!', 'device_id': 'owner-device-12345678', 'recovery_code': self.owner_setup['recovery_codes'][0]})
        self.assertEqual(result['user']['role'], 'owner')

    def test_bans_revocation_suspension_and_expiry_override_snapshot(self):
        s = self.register()
        uid = s['user']['id']
        self.user_action(uid, 'ban', reason='policy')
        self.call('POST', '/v1/session/heartbeat', {}, s['token'], status=403)
        self.user_action(uid, 'unban')
        self.user_action(uid, 'terminate_sessions')
        s = self.login()
        lid = self.call('GET', f'/v1/admin/users/{uid}', token=self.owner)['license']['id']
        self.call('POST', f'/v1/admin/licenses/{lid}', {'action': 'suspend'}, self.owner)
        self.call('POST', '/v1/tools/authorize', {'feature': 'performance'}, s['token'], status=403)
        self.call('POST', f'/v1/admin/licenses/{lid}', {'action': 'resume'}, self.owner)
        self.call('POST', f'/v1/admin/licenses/{lid}', {'action': 'revoke'}, self.owner)
        self.call('GET', '/v1/me', token=s['token'], status=403)

    def test_lease_cannot_be_renewed_after_expiration(self):
        s = self.register()
        self.now += 24
        self.call('POST', '/v1/session/heartbeat', {}, s['token'])
        self.now += 26
        self.call('POST', '/v1/session/heartbeat', {}, s['token'], status=401)
        self.login()

    def test_profiles_content_feedback_and_history(self):
        core = self.register()
        elite = self.register(tier='Elite', username='elite')
        self.call('POST', '/v1/profiles', {'name': 'Forbidden', 'config': {}}, core['token'], status=403)
        profile = self.call('POST', '/v1/profiles', {'name': 'Custom', 'config': {'kind': 'single_edit'}}, elite['token'])
        self.assertEqual(len(self.call('GET', '/v1/profiles', token=elite['token'])['profiles']), 1)
        self.call('DELETE', f"/v1/profiles/{profile['id']}", token=core['token'], status=403)
        self.call('DELETE', f"/v1/profiles/{profile['id']}", token=elite['token'])
        for name in ['first', 'second']:
            self.call('POST', '/v1/admin/content', {'kind': 'preset', 'name': 'Fast', 'body': {'description': name}, 'channel': 'stable'}, self.owner)
        self.assertEqual(len(self.call('GET', '/v1/admin/content', token=self.owner)['presets']), 2)
        self.assertEqual(self.call('GET', '/v1/content', token=core['token'])['presets'], [])
        self.assertEqual(len(self.call('GET', '/v1/content', token=elite['token'])['presets']), 1)
        self.call('POST', '/v1/feedback', {'message': 'Works', 'diagnostics': {'windows': '11'}}, core['token'])
        self.assertEqual(len(self.call('GET', '/v1/admin/feedback', token=self.owner)['feedback']), 1)

    def test_invalid_input_and_abuse_are_rejected(self):
        self.call('POST', '/v1/auth/register', {'key': self.key(), 'username': "x'--", 'password': 'short', 'device_id': 'dev'}, status=400)
        self.call('POST', '/v1/admin/licenses', {'tier': 'Fake', 'count': 1}, self.owner, status=400)
        self.call('POST', '/v1/admin/licenses', {'tier': 'Core', 'count': 1001}, self.owner, status=400)
        self.call('POST', '/v1/admin/settings', {'transfer_cooldown_hours': -1}, self.owner, status=400)
        self.call('POST', '/v1/admin/content', {'kind': 'nonsense', 'name': 'a', 'body': {}}, self.owner, status=400)
        statuses = [self.svc.handle('POST', '/v1/auth/login', {'username': 'missing', 'password': 'wrong', 'device_id': 'some-device-1234567'}, ip='attacker')[0] for _ in range(12)]
        self.assertIn(429, statuses)

    def test_no_secret_disclosure_in_admin_or_audit(self):
        s = self.register()
        responses = [self.call('GET', path, token=self.owner) for path in ['/v1/admin/audit', '/v1/admin/users', '/v1/admin/licenses', f"/v1/admin/users/{s['user']['id']}"]]
        combined = json.dumps(responses)
        for secret in ['Member-password-123!', 'Owner-password-124!', s['token'], s['recovery_codes'][0], self.owner_setup['totp_secret']]:
            self.assertNotIn(secret, combined)
        self.assertNotIn('password_hash', combined)

    def test_enforced_values_reject_unsupported_or_invalid_settings_atomically(self):
        s = self.register()
        lid = self.call('GET', f"/v1/admin/users/{s['user']['id']}", token=self.owner)['license']['id']
        for enforced in [{'single_edit': {'repeat_ms': 0}}, {'performance': {'hidden_setting': True}}, {'filter_keys': {'enabled': 'yes'}}, {'themes': {'accent': 'javascript:evil'}}, {'single_edit': {'select': 'INVALID'}}]:
            with self.subTest(enforced=enforced):
                self.call('POST', f'/v1/admin/licenses/{lid}', {'action': 'update', 'tier': 'Elite', 'enforced': enforced}, self.owner, status=400)
                self.assertEqual(self.call('GET', f"/v1/admin/users/{s['user']['id']}", token=self.owner)['license']['tier'], 'Core')

    def test_content_urls_are_https_and_welcome_snapshots_include_owner_overrides(self):
        self.call('POST', '/v1/admin/content', {'kind': 'release', 'name': 'Unsafe', 'body': {'download_url': 'http://unsafe.example/app.exe'}}, self.owner, status=400)
        self.call('POST', '/v1/admin/content', {'kind': 'release', 'name': 'Safe', 'body': {'download_url': 'https://example.com/app.exe'}}, self.owner)
        s = self.register()
        self.assertEqual(s['overrides'], {})

    def test_expiration_and_permanent_license(self):
        timed = self.register(days=0.0001)
        permanent = self.register(username='forever', days=None)
        self.now += 10
        self.call('GET', '/v1/me', token=timed['token'], status=403)
        self.assertIsNone(self.call('GET', '/v1/me', token=permanent['token'])['expires_at'])

    def test_concurrent_recovery_has_one_winner(self):
        s = self.register()
        payload = {'username': 'member', 'recovery_code': s['recovery_codes'][0], 'new_password': 'Changed-password-123!'}
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda n: self.svc.handle('POST', '/v1/auth/recover', payload, ip=f'recovery{n}'), range(6)))
        self.assertEqual(sum(code == 200 for code, _ in results), 1)
        self.assertEqual(sum(code == 401 for code, _ in results), 5)

    def test_reset_expiry_rename_and_transfer_cooldown(self):
        s = self.register()
        uid = s['user']['id']
        self.user_action(uid, 'rename', username='renamed')
        self.assertEqual(self.call('GET', '/v1/me', token=s['token'])['user']['username'], 'renamed')
        reset = self.user_action(uid, 'reset_password')
        self.call('POST', f'/v1/admin/users/{uid}', {'action': 'reset_password'}, self.owner, status=409)
        self.user_action(uid, 'reset_device')
        self.call('POST', f'/v1/admin/users/{uid}', {'action': 'reset_device'}, self.owner, status=409)
        self.now += 901
        self.call('POST', '/v1/auth/recover', {'username': 'renamed', 'reset_token': reset['reset_token'], 'new_password': 'New-password-123!'}, status=401)

    def test_license_replacement_and_extension_preserve_history(self):
        s = self.register()
        uid = s['user']['id']
        lid = self.call('GET', f'/v1/admin/users/{uid}', token=self.owner)['license']['id']
        extended = self.call('POST', f'/v1/admin/licenses/{lid}', {'action': 'extend', 'days': 2}, self.owner)['license']
        self.assertEqual(extended['expires_at'], s['expires_at'] + 172800)
        replacement = self.call('POST', f'/v1/admin/licenses/{lid}', {'action': 'replace'}, self.owner)
        self.assertEqual(replacement['license']['expires_at'], extended['expires_at'])
        self.assertEqual(self.call('GET', f'/v1/admin/users/{uid}', token=self.owner)['user']['id'], uid)
        self.call('POST', '/v1/license/validate', {'key': replacement['key']}, status=409)
        self.call('POST', f'/v1/admin/licenses/{lid}', {'action': 'replace'}, self.owner, status=409)

    def test_failed_registration_does_not_consume_key(self):
        self.register()
        key = self.key()
        self.register(key=key, username='other')
        untouched = self.key()
        self.call('POST', '/v1/auth/register', {'key': untouched, 'username': 'member', 'password': 'Member-password-123!', 'device_id': 'member-device-12345678'}, status=409)
        self.assertEqual(self.call('POST', '/v1/license/validate', {'key': untouched})['tier'], 'Core')

    def test_profiles_edit_is_atomic_and_scoped_to_account(self):
        first = self.register(tier='Elite', username='first')
        second = self.register(tier='Elite', username='second')
        profile = self.call('POST', '/v1/profiles', {'name': 'Original', 'config': {}}, first['token'])
        body = {'id': profile['id'], 'name': 'Renamed', 'config': {'kind': 'drag'}}
        self.call('POST', '/v1/profiles', body, second['token'], status=404)
        edited = self.call('POST', '/v1/profiles', body, first['token'])
        self.assertEqual(edited['id'], profile['id'])
        listed = self.call('GET', '/v1/profiles', token=first['token'])['profiles']
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]['name'], 'Renamed')
        self.assertEqual(listed[0]['config']['kind'], 'drag')

    def test_advanced_policy_allowlist_and_alternate_tool_permission_guards(self):
        s = self.register()
        self.call('POST', '/v1/tools/authorize', {'feature': 'performance', 'settings': {'preset': 'potato'}}, s['token'], status=403)
        self.call('POST', '/v1/tools/authorize', {'feature': 'performance', 'settings': {'advanced': {'bUseVSync': False}}}, s['token'], status=403)
        lid = self.call('GET', f"/v1/admin/users/{s['user']['id']}", token=self.owner)['license']['id']
        self.call('POST', f'/v1/admin/licenses/{lid}', {'action': 'update', 'enforced': {'advanced': {'preset': 'custom', 'advanced': {'FrameRateLimit': 240, 'bUseVSync': False, 'sg.TextureQuality': 0}}}}, self.owner)
        self.call('POST', f'/v1/admin/licenses/{lid}', {'action': 'update', 'enforced': {'advanced': {'advanced': {'r.HiddenUnsupported': 0}}}}, self.owner, status=400)


if __name__ == '__main__':
    unittest.main()
