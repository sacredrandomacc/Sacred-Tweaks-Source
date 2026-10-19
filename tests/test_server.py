import base64
import concurrent.futures
from contextlib import closing
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
        self.svc = self.make_service()
        setup = self.svc.bootstrap_owner('owner', 'Owner-password-124!')
        self.owner_setup = setup
        self.owner = self.call('POST', '/v1/auth/login', {'username': 'owner', 'password': 'Owner-password-124!', 'device_id': 'owner-device-12345678', 'totp': totp(setup['totp_secret'], self.now)})['token']

    def make_service(self):
        return Service(self.path, clock=lambda: self.now, password_cost=1024)

    def database_text(self):
        return self.path.read_bytes().decode("latin1")

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
        self.assertNotIn(key, self.database_text())

    def test_schema_v1_upgrade_preserves_users_and_adds_session_moderation_fields(self):
        old_path=Path(self.tmp.name)/'legacy.sqlite3'
        old=Service(old_path,clock=lambda:self.now,password_cost=1024)
        old.bootstrap_owner('legacyowner','Owner-password-124!')
        with closing(old.connect()) as db:
            db.execute('DROP TABLE refresh_sessions')
            for column in ('moderation_policy_version','moderation_category','moderation_status'):
                db.execute(f'ALTER TABLE users DROP COLUMN {column}')
            db.execute('PRAGMA user_version=1')
        migrated=Service(old_path,clock=lambda:self.now,password_cost=1024)
        with closing(migrated.connect()) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)
            self.assertTrue({'moderation_status','moderation_category','moderation_policy_version'} <= {r['name'] for r in db.execute('PRAGMA table_info(users)')})
            self.assertEqual(db.execute("SELECT username FROM users WHERE role='owner'").fetchone()['username'],'legacyowner')
            self.assertIsNotNone(db.execute("SELECT name FROM sqlite_master WHERE name='refresh_sessions'").fetchone())

    def test_flagged_registration_creates_pending_review_without_session(self):
        result = self.register(username='n1gger')
        self.assertEqual(result['moderation_status'], 'pending')
        self.assertNotIn('token', result)
        self.assertIn('owner', result['review_message'])
        self.call('POST', '/v1/auth/login', {'username': 'n1gger', 'password': 'Member-password-123!',
            'device_id': 'member-device-12345678'}, status=403)
        self.assertEqual(self.call('GET', '/v1/admin/moderation', token=self.owner)['queue'][0]['username'], 'n1gger')

    def test_owner_review_can_rename_or_reasoned_approve(self):
        flagged = self.register(username='n1gger')
        uid = flagged['user_id'] if 'user_id' in flagged else self.call('GET', '/v1/admin/users?q=n1gger', token=self.owner)['users'][0]['id']
        self.call('POST', f'/v1/admin/moderation/{uid}', {'action': 'approve'}, self.owner, status=400)
        self.call('POST', f'/v1/admin/moderation/{uid}', {'action': 'approve', 'reason': 'Reviewed by the owner.'}, self.owner)
        renamed = self.call('POST', f'/v1/admin/users/{uid}', {'action': 'rename', 'username': 'clean_name'}, self.owner)
        self.assertEqual(renamed['message'], 'Account updated.')

    def test_rename_rechecks_policy_and_revokes_existing_access(self):
        member = self.register(username='regular')
        uid = member['user']['id']
        self.call('POST', f'/v1/admin/users/{uid}', {'action': 'rename', 'username': 'n1gger'}, self.owner)
        self.call('GET', '/v1/me', token=member['token'], status=401)
        self.call('POST', '/v1/auth/login', {'username': 'n1gger', 'password': 'Member-password-123!',
            'device_id': 'member-device-12345678'}, status=403)

    def test_remembered_session_rotates_refresh_secret_and_detects_replay(self):
        member = self.register()
        self.call('POST', '/v1/auth/logout', {}, member['token'])
        first = self.call('POST', '/v1/auth/login', {'username': 'member', 'password': 'Member-password-123!',
            'device_id': 'member-device-12345678', 'remember_me': True})
        original = first['refresh_token']
        self.assertNotIn(original, self.database_text())
        second = self.call('POST', '/v1/auth/refresh', {'refresh_token': original})
        self.assertNotEqual(second['refresh_token'], original)
        self.call('POST', '/v1/auth/refresh', {'refresh_token': original}, status=401)
        self.call('GET', '/v1/me', token=second['token'], status=401)

    def test_recovery_revokes_remembered_refresh_credentials(self):
        registration = self.register()
        # Member registration can opt in to remembered sessions.
        self.call('POST', '/v1/auth/logout', {}, registration['token'])
        saved = self.call('POST', '/v1/auth/login', {'username': 'member', 'password': 'Member-password-123!',
            'device_id': 'member-device-12345678', 'remember_me': True})
        self.call('POST', '/v1/auth/recover', {'username': 'member', 'recovery_code': registration['recovery_codes'][0],
            'new_password': 'New-password-123!'})
        self.call('POST', '/v1/auth/refresh', {'refresh_token': saved['refresh_token']}, status=401)

    def test_permission_overrides_wait_for_next_login_and_enforced_settings(self):
        s = self.register()
        license_id = self.call('GET', f"/v1/admin/users/{s['user']['id']}", token=self.owner)['license']['id']
        self.call('POST', f'/v1/admin/licenses/{license_id}', {'action': 'update', 'tier': 'Elite', 'overrides': {'drag': False, 'filter_keys': True}, 'enforced': {'single_edit': {'repeat_ms': 200}}}, self.owner)
        heart = self.call('POST', '/v1/session/heartbeat', {}, s['token'])
        self.assertEqual(heart['tier'], 'Sacred')
        self.assertTrue(heart['permissions']['drag'])
        self.call('POST', '/v1/auth/logout', {}, s['token'])
        s = self.login()
        self.assertTrue(s['permissions']['filter_keys'])
        self.assertFalse(s['permissions']['drag'])
        self.assertEqual(self.call('POST', '/v1/tools/authorize', {'feature': 'single_edit', 'settings': {'repeat_ms': 1}}, s['token'])['settings']['repeat_ms'], 200)
        self.call('POST', '/v1/tools/authorize', {'feature': 'drag'}, s['token'], status=403)

    def test_manual_sacred_license_includes_every_feature(self):
        s = self.register(tier='Sacred', days=30, username='publicmember')
        self.assertEqual(s['tier'], 'Sacred')
        self.assertTrue(all(s['permissions'].values()))
        self.assertIn('double_edit', s['permissions'])
        self.assertIn('gun_pullout', s['permissions'])

    def test_existing_tier_licenses_get_public_feature_set(self):
        s = self.register(tier='Core', username='legacyuser')
        self.assertEqual(s['tier'], 'Sacred')
        self.assertTrue(all(s['permissions'].values()))

    def test_public_manual_access_is_thirty_days_or_lifetime(self):
        self.call('POST', '/v1/admin/licenses', {'tier': 'Sacred', 'duration_days': 7}, self.owner, status=400)
        key = self.key(tier='Sacred', days=None)
        s = self.register(tier='Sacred', key=key, username='lifetimeuser')
        self.assertIsNone(s['expires_at'])

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
        self.assertNotIn(result['reset_token'], self.database_text())

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

    def test_owner_appoints_admins_with_limited_powers(self):
        admin = self.register(username='helper')
        member = self.register(username='member2', key=self.key())
        uid, other = admin['user']['id'], member['user']['id']
        self.call('POST', f'/v1/admin/users/{uid}', {'action': 'set_role', 'role': 'owner'}, self.owner, status=400)
        self.user_action(uid, 'set_role', role='admin')
        # Promotion revokes the old session; the next login carries the admin role.
        self.call('GET', '/v1/me', token=admin['token'], status=401)
        token = self.call('POST', '/v1/auth/login', {'username': 'helper', 'password': 'Member-password-123!', 'device_id': 'member-device-12345678'})['token']
        for path in ['/v1/admin/users', '/v1/admin/licenses', '/v1/admin/overview', '/v1/admin/settings']:
            self.call('GET', path, token=token)
        self.call('POST', '/v1/admin/licenses', {'tier': 'Core', 'duration_days': 1, 'count': 1}, token)
        self.call('POST', f'/v1/admin/users/{other}', {'action': 'terminate_sessions'}, token)
        # Owner-only: settings, role changes, and acting on staff accounts.
        self.call('POST', '/v1/admin/settings', {'transfer_cooldown_hours': 1}, token, status=403)
        self.call('POST', f'/v1/admin/users/{other}', {'action': 'set_role', 'role': 'admin'}, token, status=403)
        owner_id = self.call('GET', '/v1/me', token=self.owner)['user']['id']
        self.call('POST', f'/v1/admin/users/{owner_id}', {'action': 'terminate_sessions'}, token, status=403)
        self.call('POST', f'/v1/admin/users/{owner_id}', {'action': 'set_role', 'role': 'member'}, self.owner, status=403)
        actions = [row['action'] for row in self.call('GET', '/v1/admin/audit', token=self.owner)['audit']]
        self.assertIn('role_changed', actions)
        self.user_action(uid, 'set_role', role='member')
        self.call('GET', '/v1/admin/users', token=token, status=401)

    def test_announcement_reactions_and_audit_actor_names(self):
        member = self.register()
        post = self.call('POST', '/v1/admin/content', {'kind': 'announcement', 'name': 'Patch day', 'body': {'message': 'New themes'}}, self.owner)
        cid = post['id'] if 'id' in post else self.call('GET', '/v1/content', token=member['token'])['announcements'][0]['id']
        self.assertEqual(self.call('POST', f'/v1/content/{cid}/react', {'reaction': 'fire'}, member['token'])['counts'], {'fire': 1})
        self.call('POST', f'/v1/content/{cid}/react', {'reaction': 'heart'}, member['token'])
        mine = self.call('GET', '/v1/content', token=member['token'])['announcements'][0]['reactions']
        self.assertEqual((mine['counts'], mine['mine']), ({'heart': 1}, 'heart'))
        self.call('POST', f'/v1/content/{cid}/react', {'reaction': '<b>'}, member['token'], status=400)
        self.call('POST', '/v1/content/999999/react', {'reaction': 'fire'}, member['token'], status=404)
        self.call('POST', f'/v1/content/{cid}/react', {'reaction': None}, member['token'])
        admin_view = self.call('GET', '/v1/admin/content', token=self.owner)['announcements'][0]['reactions']
        self.assertEqual(admin_view['counts'], {})
        audit = self.call('GET', '/v1/admin/audit', token=self.owner)['audit']
        self.assertTrue(any(row.get('actor_username') == 'owner' for row in audit))

    def test_public_update_manifest_offers_only_hashed_member_releases(self):
        self.call('GET', '/v1/updates/latest', status=404)
        digest = 'a' * 64
        publish = lambda **body: self.call('POST', '/v1/admin/content', {'kind': 'release', 'name': 'Sacred Tweaks', 'channel': body.pop('channel', 'stable'), 'body': body}, self.owner)
        publish(notes='Member', version='0.6.0', url='https://downloads.example.com/member.zip', sha256=digest)
        publish(notes='No hash', version='0.7.0', url='https://downloads.example.com/x.zip')
        publish(notes='Manager', version='0.9.0', url='https://downloads.example.com/manager.zip', sha256=digest, app='manager')
        publish(notes='Beta', version='1.0.0', url='https://downloads.example.com/beta.zip', sha256=digest, channel='beta')
        latest = self.call('GET', '/v1/updates/latest')
        self.assertEqual((latest['version'], latest['url']), ('0.6.0', 'https://downloads.example.com/member.zip'))

    def test_polls_feedback_replies_maintenance_and_beta_feed(self):
        member = self.register()
        post = self.call('POST', '/v1/admin/content', {'kind': 'announcement', 'name': 'Vote', 'body': {'message': 'Next theme?', 'poll': {'question': 'Pick one', 'options': ['Ice', 'Fire']}}}, self.owner)
        self.call('POST', '/v1/admin/content', {'kind': 'announcement', 'name': 'Bad', 'body': {'poll': {'question': 'x', 'options': ['only']}}}, self.owner, status=400)
        cid = post['id']
        self.assertEqual(self.call('POST', f'/v1/content/{cid}/vote', {'option': 1}, member['token']), {'counts': [0, 1], 'mine': 1})
        self.call('POST', f'/v1/content/{cid}/vote', {'option': 5}, member['token'], status=400)
        self.assertEqual(self.call('GET', '/v1/content', token=member['token'])['announcements'][0]['poll_results']['counts'], [0, 1])
        self.call('POST', '/v1/feedback', {'message': 'Love the overlay'}, member['token'])
        fid = self.call('GET', '/v1/admin/feedback', token=self.owner)['feedback'][0]['id']
        self.call('POST', f'/v1/admin/feedback/{fid}/reply', {'message': 'Thanks!'}, self.owner)
        self.assertEqual(self.call('GET', '/v1/feedback', token=member['token'])['feedback'][0]['reply'], 'Thanks!')
        self.call('POST', f'/v1/admin/feedback/{fid}/reply', {'message': 'x'}, member['token'], status=403)
        self.assertFalse(self.call('GET', '/v1/status')['maintenance']['enabled'])
        self.call('POST', '/v1/admin/settings', {'maintenance': {'enabled': True, 'message': 'Back at 6pm'}}, self.owner)
        self.assertEqual(self.call('GET', '/v1/status')['maintenance'], {'enabled': True, 'message': 'Back at 6pm'})
        self.call('POST', '/v1/admin/settings', {'maintenance': {'enabled': 'yes'}}, self.owner, status=400)
        digest = 'c' * 64
        for version, channel in (('0.6.0', 'stable'), ('0.7.0', 'beta')):
            self.call('POST', '/v1/admin/content', {'kind': 'release', 'name': 'Sacred Tweaks', 'channel': channel, 'body': {'notes': 'n', 'version': version, 'url': 'https://d.example.com/a.zip', 'sha256': digest}}, self.owner)
        self.assertEqual(self.call('GET', '/v1/updates/beta')['version'], '0.7.0')
        self.assertEqual(self.call('GET', '/v1/updates/latest')['version'], '0.6.0')

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
        own = self.call('POST', '/v1/profiles', {'name': 'First setup', 'config': {}}, core['token'])
        profile = self.call('POST', '/v1/profiles', {'name': 'Custom', 'config': {'kind': 'single_edit'}}, elite['token'])
        self.assertEqual(len(self.call('GET', '/v1/profiles', token=elite['token'])['profiles']), 1)
        self.call('DELETE', f"/v1/profiles/{profile['id']}", token=core['token'], status=404)
        self.call('DELETE', f"/v1/profiles/{own['id']}", token=core['token'])
        self.call('DELETE', f"/v1/profiles/{profile['id']}", token=elite['token'])
        for name in ['first', 'second']:
            self.call('POST', '/v1/admin/content', {'kind': 'preset', 'name': 'Fast', 'body': {'description': name}, 'channel': 'stable'}, self.owner)
        self.assertEqual(len(self.call('GET', '/v1/admin/content', token=self.owner)['presets']), 2)
        self.assertEqual(len(self.call('GET', '/v1/content', token=core['token'])['presets']), 1)
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

    def test_profile_import_saves_only_validated_bundle_atomically(self):
        member = self.register(tier='Elite')
        profile={'name':'Build','config':{'kind':'single_edit','config':{'edit':'E'}}}
        result=self.call('POST','/v1/profiles/import',{'profiles':[profile]},member['token'])
        self.assertEqual(len(result['profiles']),1)
        self.call('POST','/v1/profiles/import',{'profiles':[{'name':'Later','config':profile['config']},profile]},member['token'],status=409)
        self.assertEqual([p['name'] for p in self.call('GET','/v1/profiles',token=member['token'])['profiles']],['Build'])
        self.call('POST','/v1/profiles/import',{'profiles':[{'name':'Bad','config':{'kind':'single_edit','config':{},'script':'no'}}]},member['token'],status=400)

    def test_advanced_policy_allowlist_and_alternate_tool_permission_guards(self):
        s = self.register()
        self.call('POST', '/v1/tools/authorize', {'feature': 'performance', 'settings': {'preset': 'potato'}}, s['token'])
        self.call('POST', '/v1/tools/authorize', {'feature': 'performance', 'settings': {'advanced': {'bUseVSync': False}}}, s['token'])
        lid = self.call('GET', f"/v1/admin/users/{s['user']['id']}", token=self.owner)['license']['id']
        self.call('POST', f'/v1/admin/licenses/{lid}', {'action': 'update', 'enforced': {'advanced': {'preset': 'custom', 'advanced': {'FrameRateLimit': 240, 'bUseVSync': False, 'sg.TextureQuality': 0}}}}, self.owner)
        self.call('POST', f'/v1/admin/licenses/{lid}', {'action': 'update', 'enforced': {'advanced': {'advanced': {'r.HiddenUnsupported': 0}}}}, self.owner, status=400)


if __name__ == '__main__':
    unittest.main()
