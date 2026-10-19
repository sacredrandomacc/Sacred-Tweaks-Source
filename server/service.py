"""Transactional API service. No client contains privileged credentials.

Passwords: scrypt N=2**17/r=8/p=1; all bearer, reset, license and recovery
secrets are random and stored as SHA-256 verification hashes. TOTP seeds must
remain recoverable, and are stored only in the server's permission-restricted DB.
"""
from __future__ import annotations

import base64
from collections import defaultdict, deque
from contextlib import closing
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import struct
import threading
import time
from urllib.parse import parse_qs, urlsplit
from .username_moderation import moderate_username

VERSION = '0.7.0'
FEATURES = ('single_edit', 'performance', 'measurements', 'themes', 'potato',
            'filter_keys', 'owner_presets', 'drag', 'advanced', 'profiles', 'beta')
TIERS = ('Core', 'Plus', 'Pro', 'Elite', 'Sacred')  # Historical tiers remain readable; new sales use Sacred.
EXTENDED_MACROS = ('prefire', 'pickup', 'wall_replace', 'auto_build', 'mantle', 'quick_reset', 'floor_cone',
                   'double_edit', 'gun_pullout')
FEATURES += EXTENDED_MACROS
LEASE_SECONDS = 25
HEARTBEAT_SECONDS = 10


REACTIONS = ('fire', 'heart', 'up', 'laugh', 'wow')

class APIError(Exception):
    def __init__(self, status, code, message, alert=None, commit=False):
        self.status, self.code, self.message, self.alert = status, code, message, alert
        self.commit = commit
        super().__init__(message)


def fail(status, code, message, alert=None, commit=False):
    raise APIError(status, code, message, alert, commit)


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        fail(400, 'invalid_input', 'Payload must contain finite JSON values.')


def _hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _text(value, name, minimum=1, maximum=256):
    if not isinstance(value, str) or not minimum <= len(value) <= maximum or '\x00' in value:
        fail(400, 'invalid_input', f'{name} must be {minimum}–{maximum} characters.')
    return value


def _number(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not minimum <= value <= maximum:
        fail(400, 'invalid_input', f'{name} is outside the allowed range.')
    return value


def _object(value, name, max_bytes=32768):
    if not isinstance(value, dict) or len(_json(value).encode()) > max_bytes:
        fail(400, 'invalid_input', f'{name} must be an object of at most {max_bytes} bytes.')
    return value


def _username(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,32}', value):
        fail(400, 'invalid_username', 'Username needs 3–32 letters, digits, dots, underscores or hyphens.')
    return value


def _password(value):
    return _text(value, 'Password', 12, 128)


def _validate_enforced(feature, values):
    """Validate partial policy values; complete combinations are checked natively."""
    _object(values, feature, 4096)
    bindings = {'activation', 'edit', 'select', 'confirm', 'emergency'}
    allowed = {
        'single_edit': bindings | {'step_delay_ms', 'repeat_ms', 'confirm_mode', 'game_auto_confirm'},
        'drag': bindings | {'step_delay_ms', 'repeat_ms', 'confirm_mode', 'game_auto_confirm'},
        'performance': {'preset', 'target_fps'}, 'potato': {'preset', 'target_fps'},
        'advanced': {'preset', 'target_fps', 'advanced'},
        'filter_keys': {'enabled', 'wait_ms', 'delay_ms', 'repeat_ms', 'bounce_ms'},
        'themes': {'intensity', 'lightweight', 'accent'},
    }.get(feature, set())
    if set(values) - allowed:
        fail(400, 'invalid_enforced', f'Unsupported enforced setting for {feature}.')
    for key, value in values.items():
        if feature in ('single_edit', 'drag') and key in bindings:
            names = {'SPACE', 'TAB', 'ENTER', 'ESC', 'SHIFT', 'CTRL', 'ALT', 'LEFT', 'UP', 'RIGHT', 'DOWN', 'INSERT', 'DELETE', 'HOME', 'END', 'PAGEUP', 'PAGEDOWN', 'BACKSPACE'}
            if not isinstance(value, str) or not (re.fullmatch(r'[A-Z0-9]|F(?:[1-9]|1\d|2[0-4])|MOUSE[1-5]', value) or value in names):
                fail(400, 'invalid_enforced', 'Enforced key binding is not supported.')
        elif key in ('enabled', 'lightweight', 'game_auto_confirm'):
            if not isinstance(value, bool):
                fail(400, 'invalid_enforced', f'{key} must be true or false.')
        elif key == 'confirm_mode':
            if value not in ('auto', 'manual'):
                fail(400, 'invalid_enforced', 'Confirmation mode must be auto or manual.')
        elif key == 'preset':
            if value not in ('performance', 'max_fps', 'balanced', 'potato', 'custom'):
                fail(400, 'invalid_enforced', 'Unsupported performance preset.')
            if feature == 'performance' and value == 'potato':
                fail(400, 'invalid_enforced', 'Potato presets require their separate permission.')
            if value == 'custom' and feature != 'advanced':
                fail(400, 'invalid_enforced', 'Custom presets require advanced permissions.')
        elif key == 'advanced':
            _object(value, 'Advanced settings', 4096)
            quality_keys = {'sg.ViewDistanceQuality', 'sg.AntiAliasingQuality', 'sg.ShadowQuality', 'sg.PostProcessQuality', 'sg.TextureQuality', 'sg.EffectsQuality', 'sg.FoliageQuality', 'sg.ShadingQuality'}
            for setting, selected in value.items():
                if setting == 'FrameRateLimit':
                    _number(selected, setting, 30, 1000)
                    if 'target_fps' in values and selected != values['target_fps']:
                        fail(400, 'invalid_enforced', 'FrameRateLimit must match target_fps.')
                elif setting == 'bUseVSync':
                    if not isinstance(selected, bool):
                        fail(400, 'invalid_enforced', 'VSync must be true or false.')
                elif setting == 'sg.ResolutionQuality':
                    _number(selected, setting, 25, 100)
                elif setting in quality_keys:
                    _number(selected, setting, 0, 4)
                    if not isinstance(selected, int):
                        fail(400, 'invalid_enforced', 'Quality levels must be integers.')
                else:
                    fail(400, 'invalid_enforced', 'Unsupported advanced setting.')
        elif key == 'accent':
            if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
                fail(400, 'invalid_enforced', 'Accent must be a six-digit hex color.')
        elif key == 'target_fps':
            _number(value, key, 30, 1000)
        elif key == 'intensity':
            _number(value, key, 0, 1)
        elif feature == 'filter_keys':
            _number(value, key, 0, 20000)
            if not isinstance(value, int):
                fail(400, 'invalid_enforced', 'Filter Keys timing values must be integers.')
        elif key == 'step_delay_ms':
            _number(value, key, 5, 1000)
        elif key == 'repeat_ms':
            _number(value, key, 30, 10000)
    if feature in ('single_edit', 'drag'):
        if 'repeat_ms' in values and 'step_delay_ms' in values and values['repeat_ms'] < 2 * values['step_delay_ms'] + 10:
            fail(400, 'invalid_enforced', 'Repeat interval must accommodate the edit cycle.')
        if 'emergency' in values and any(values.get(key) == values['emergency'] for key in bindings - {'emergency'}):
            fail(400, 'invalid_enforced', 'Emergency shortcut conflicts with a macro binding.')
        if 'select' in values and any(values.get(key) == values['select'] for key in ('edit', 'confirm', 'activation')):
            fail(400, 'invalid_enforced', 'Select conflicts with another macro binding.')
        if feature == 'drag' and 'activation' in values and values.get('edit') != values['activation']:
            fail(400, 'invalid_enforced', 'Drag activation must equal its enforced edit binding.')
        if values.get('game_auto_confirm') and (feature == 'single_edit' or values.get('confirm_mode') == 'auto'):
            fail(400, 'invalid_enforced', 'Explicit confirmation conflicts with game auto-confirm.')
    if feature == 'filter_keys' and values.get('bounce_ms') and any(values.get(key) for key in ('wait_ms', 'delay_ms', 'repeat_ms')):
        fail(400, 'invalid_enforced', 'Bounce Keys cannot be combined with repeat/filter timing.')
    if values.get('preset') == 'custom' and not values.get('advanced'):
        fail(400, 'invalid_enforced', 'Custom preset requires a nonempty advanced settings map.')


def _validate_content_urls(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in ('url', 'href') or key.lower().endswith('_url'):
                if not isinstance(child, str):
                    fail(400, 'invalid_url', 'Content URLs must be HTTPS strings.')
                parsed = urlsplit(child)
                if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or any(c in child for c in '\r\n\\'):
                    fail(400, 'invalid_url', 'Content URLs must use HTTPS without embedded credentials.')
            _validate_content_urls(child)
    elif isinstance(value, list):
        for child in value:
            _validate_content_urls(child)


class Service:
    def __init__(self, db_path, *, clock=time.time, password_cost=2**17):
        self.path = Path(db_path).resolve()
        if not self.path.parent.exists():
            self.path.parent.mkdir(parents=True, mode=0o700)
        if not isinstance(password_cost, int) or password_cost < 1024 or password_cost & (password_cost - 1):
            raise ValueError('scrypt cost must be a power of two at least 1024')
        self.clock, self.password_cost = clock, password_cost
        self.rate_lock = threading.Lock()
        self.rates = defaultdict(deque)
        # A missing account also performs the configured password work.
        self.dummy_password = self._password_hash(secrets.token_urlsafe(24))
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            self.path.chmod(0o600)
        else:
            os.close(fd)
        with closing(self.connect()) as db:
            db.execute('PRAGMA journal_mode=WAL')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 3:
                raise RuntimeError('Database schema is newer than this service')
            db.executescript(Path(__file__).with_name('schema.sql').read_text())
            columns = {row['name'] for row in db.execute('PRAGMA table_info(users)')}
            for name, declaration in (('moderation_status', "TEXT NOT NULL DEFAULT 'clear'"),
                                       ('moderation_category', 'TEXT'),
                                       ('moderation_policy_version', 'INTEGER NOT NULL DEFAULT 1')):
                if name not in columns:
                    db.execute(f'ALTER TABLE users ADD COLUMN {name} {declaration}')
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=30000')
        return db

    def _password_hash(self, password):
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=self.password_cost, r=8, p=1, maxmem=256 * 1024 * 1024)
        return f'scrypt${self.password_cost}$8$1${salt.hex()}${digest.hex()}'

    @staticmethod
    def _password_verify(password, encoded):
        if not isinstance(password, str) or len(password) > 128:
            return False
        try:
            algorithm, n, r, p, salt, expected = encoded.split('$')
            if algorithm != 'scrypt':
                return False
            actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), maxmem=256 * 1024 * 1024)
            return hmac.compare_digest(actual, bytes.fromhex(expected))
        except (ValueError, TypeError):
            return False

    def _limit(self, key, count, window):
        now = self.clock()
        with self.rate_lock:
            # Bound memory even when an attacker supplies arbitrary names/IPs.
            if len(self.rates) > 10000:
                for old in list(self.rates):
                    if not self.rates[old] or self.rates[old][-1] < now - 900:
                        del self.rates[old]
                if len(self.rates) > 10000 and key not in self.rates:
                    fail(429, 'rate_limited', 'Too many requests. Please try later.')
            events = self.rates[key]
            while events and events[0] <= now - window:
                events.popleft()
            if len(events) >= count:
                fail(429, 'rate_limited', 'Too many requests. Please try later.')
            events.append(now)

    def _recovery_codes(self, db, uid):
        db.execute('DELETE FROM recovery_codes WHERE user_id=?', (uid,))
        codes = ['-'.join(secrets.token_hex(12).upper()[i:i + 6] for i in range(0, 24, 6)) for _ in range(10)]
        db.executemany('INSERT INTO recovery_codes(user_id,code_hash) VALUES (?,?)', [(uid, _hash(c)) for c in codes])
        return codes

    def bootstrap_owner(self, username, password):
        username, password = _username(username), _password(password)
        secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
        with closing(self.connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if db.execute("SELECT id FROM users WHERE role='owner'").fetchone():
                    raise RuntimeError('Owner already exists; use authenticator or recovery codes')
                uid = db.execute('INSERT INTO users(username,password_hash,role,created_at,totp_secret) VALUES (?,?,?,?,?)',
                                 (username, self._password_hash(password), 'owner', self.clock(), secret)).lastrowid
                codes = self._recovery_codes(db, uid)
                self._audit(db, uid, 'owner_bootstrap', 'user', uid)
                db.commit()
            except BaseException:
                db.rollback()
                raise
        return {'totp_secret': secret, 'recovery_codes': codes}

    def handle(self, method, path, data=None, token=None, ip='local'):
        try:
            if not isinstance(method, str) or not isinstance(path, str) or len(path) > 2048:
                fail(400, 'invalid_request', 'Invalid request.')
            data = {} if data is None else _object(data, 'Payload', 65536)
            parsed = urlsplit(path)
            path, query = parsed.path.rstrip('/'), parse_qs(parsed.query)
            method = method.upper()
            self._limit(('all', str(ip)), 240, 60)
            if path in ('/v1/auth/login', '/v1/auth/recover', '/v1/device/request'):
                name = str(data.get('username', ''))[:128].casefold()
                self._limit(('auth_ip', str(ip)), 30, 60)
                self._limit(('auth_user', _hash(name)), 10, 900)
            elif path == '/v1/auth/refresh':
                refresh_hint = str(data.get('refresh_token', ''))[:256]
                self._limit(('refresh_ip', str(ip)), 30, 60)
                self._limit(('refresh_token', _hash(refresh_hint)), 10, 900)
            elif path in ('/v1/auth/register', '/v1/license/validate'):
                self._limit(('redeem', str(ip)), 30, 60)
            with closing(self.connect()) as db:
                db.execute('BEGIN IMMEDIATE')
                try:
                    body = self._dispatch(db, method, path, query, data, token)
                    db.commit()
                    return 200, body
                except APIError as error:
                    db.commit() if error.commit else db.rollback()
                    if error.alert:
                        uid, kind, message = error.alert
                        db.execute('INSERT INTO alerts(user_id,kind,message,created_at) VALUES (?,?,?,?)', (uid, kind, message, self.clock()))
                    raise
                except sqlite3.IntegrityError:
                    db.rollback()
                    fail(409, 'conflict', 'The requested name, key, session or record is already in use.')
                except BaseException:
                    db.rollback()
                    raise
        except APIError as error:
            return error.status, {'error': error.message, 'code': error.code}
        except sqlite3.OperationalError:
            return 503, {'error': 'Service temporarily unavailable.', 'code': 'unavailable'}
        except (UnicodeError, ValueError, OverflowError, RecursionError):
            return 400, {'error': 'Invalid request value.', 'code': 'invalid_input'}

    def _audit(self, db, actor, action, target_type, target_id=None, **details):
        db.execute('INSERT INTO audit(actor_id,action,target_type,target_id,details,created_at) VALUES (?,?,?,?,?,?)',
                   (actor, action, target_type, target_id, _json(details), self.clock()))

    def _check_access(self, db, user):
        now = self.clock()
        if user['banned'] and (user['ban_until'] is None or user['ban_until'] > now):
            fail(403, 'banned', 'Sacred Tweaks account suspended: ' + (user['ban_reason'] or 'Contact the owner.'))
        if user['role'] == 'owner':
            return None
        license = db.execute('SELECT * FROM licenses WHERE id=?', (user['license_id'],)).fetchone()
        if not license or license['status'] != 'active':
            fail(403, 'license_inactive', 'Your license is suspended or revoked. Contact the owner.')
        if license['expires_at'] is not None and license['expires_at'] <= now:
            fail(403, 'license_expired', 'Your license has expired. Restoration remains available.')
        return license

    def _authorize(self, db, token, owner=False):
        if not isinstance(token, str) or not 20 <= len(token) <= 256:
            fail(401, 'unauthorized', 'Sign in to continue.')
        session = db.execute('SELECT * FROM sessions WHERE token_hash=? AND revoked=0', (_hash(token),)).fetchone()
        if not session or session['lease_until'] <= self.clock() or session['absolute_until'] <= self.clock():
            fail(401, 'session_expired', 'Session expired. Sign in again.')
        user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
        self._check_access(db, user)
        # Staff routes: the owner and owner-appointed admins. Owner-only operations
        # are re-checked inside _admin/_admin_user.
        if owner and user['role'] not in ('owner', 'admin'):
            fail(403, 'owner_required', 'Owner authorization is required.')
        return user, session

    def _public_user(self, row):
        return {key: row[key] for key in ('id', 'username', 'role', 'license_id', 'created_at', 'banned', 'ban_until', 'ban_reason', 'last_transfer_at', 'last_reset_at')}

    def _license(self, row):
        if not row:
            return None
        result = {key: row[key] for key in ('id', 'key_hint', 'tier', 'duration_days', 'created_at', 'redeemed_at', 'expires_at', 'status', 'replaced_by')}
        result.update({key: json.loads(row[key]) for key in ('overrides', 'enforced', 'welcome')})
        result['permanent'] = row['duration_days'] is None
        return result

    def _snapshot(self, db, user):
        license = self._check_access(db, user)
        if user['role'] == 'owner':
            return {'tier': 'Sacred', 'permissions': {feature: True for feature in FEATURES}, 'overrides': {}, 'enforced': {}, 'welcome': {}}
        tier = license['tier']
        permissions = {feature: True for feature in FEATURES}
        for feature, value in json.loads(license['overrides']).items():
            if value is not None:
                permissions[feature] = value
        welcome = db.execute("SELECT body FROM content WHERE kind='welcome' AND tier=? ORDER BY id DESC LIMIT 1", (tier,)).fetchone()
        welcome = json.loads(welcome['body']) if welcome else {}
        welcome.update(json.loads(license['welcome']))
        return {'tier': 'Sacred', 'permissions': permissions, 'overrides': json.loads(license['overrides']), 'enforced': json.loads(license['enforced']), 'welcome': welcome}

    def _metadata(self, db, user, session):
        license = self._check_access(db, user)
        return {'user': {key: user[key] for key in ('id', 'username', 'role')}, **json.loads(session['snapshot']),
                'expires_at': license['expires_at'] if license else None, 'lease_seconds': LEASE_SECONDS, 'heartbeat_seconds': HEARTBEAT_SECONDS}

    def _session(self, db, user, remember=False):
        now = self.clock()
        db.execute('UPDATE sessions SET revoked=1 WHERE user_id=? AND (lease_until<=? OR absolute_until<=?)', (user['id'], now, now))
        if db.execute('SELECT id FROM sessions WHERE user_id=? AND revoked=0', (user['id'],)).fetchone():
            fail(409, 'session_conflict', 'An authorized session is already active. Sign out there or contact the owner.',
                 (user['id'], 'session_conflict', 'A second session was rejected.'))
        db.execute('UPDATE refresh_sessions SET revoked=1 WHERE user_id=? AND revoked=0', (user['id'],))
        token = secrets.token_urlsafe(32)
        sid = db.execute('INSERT INTO sessions(token_hash,user_id,created_at,renewed_at,lease_until,absolute_until,snapshot) VALUES (?,?,?,?,?,?,?)',
                         (_hash(token), user['id'], now, now, now + LEASE_SECONDS, now + 12 * 3600, _json(self._snapshot(db, user)))).lastrowid
        session = db.execute('SELECT * FROM sessions WHERE id=?', (sid,)).fetchone()
        result = {'token': token, **self._metadata(db, user, session)}
        if remember:
            refresh = secrets.token_urlsafe(48)
            db.execute('INSERT INTO refresh_sessions(token_hash,user_id,created_at,expires_at) VALUES (?,?,?,?)',
                       (_hash(refresh), user['id'], now, now + 30 * 86400))
            result['refresh_token'] = refresh
        return result

    def _credentials(self, db, data):
        username = _text(data.get('username'), 'Username', 1, 128)
        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        if not self._password_verify(data.get('password'), user['password_hash'] if user else self.dummy_password) or not user:
            fail(401, 'invalid_credentials', 'Username or authentication credential is incorrect.')
        if user['moderation_status'] == 'pending':
            fail(403, 'username_review_pending', 'Access is paused while the owner reviews your username. Contact the owner for a status update.')
        if user['moderation_status'] == 'rejected':
            fail(403, 'username_review_rejected', 'Access is paused. Contact the owner to request a compliant username and account review.')
        return user

    def _consume_recovery(self, db, user, value):
        if not isinstance(value, str) or not 10 <= len(value) <= 128:
            return False
        return bool(db.execute('UPDATE recovery_codes SET used_at=? WHERE user_id=? AND code_hash=? AND used_at IS NULL',
                               (self.clock(), user['id'], _hash(value.strip().upper()))).rowcount)

    def _mfa(self, db, user, data):
        if data.get('recovery_code') and self._consume_recovery(db, user, data['recovery_code']):
            return
        code = data.get('totp')
        if isinstance(code, str) and re.fullmatch(r'\d{6}', code):
            key = base64.b32decode(user['totp_secret'] + '=' * (-len(user['totp_secret']) % 8))
            for step in range(int(self.clock()) // 30 - 1, int(self.clock()) // 30 + 2):
                digest = hmac.new(key, struct.pack('>Q', step), hashlib.sha1).digest()
                offset = digest[-1] & 15
                expected = str((struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff) % 1000000).zfill(6)
                if hmac.compare_digest(code, expected) and step > user['totp_last_step']:
                    db.execute('UPDATE users SET totp_last_step=? WHERE id=?', (step, user['id']))
                    return
        fail(401, 'mfa_required', 'Enter an unused authenticator code or recovery code.')

    def _device(self, data):
        return _hash(_text(data.get('device_id'), 'Device identifier', 16, 256))

    def _set_device(self, db, uid, device_hash):
        now = self.clock()
        db.execute('UPDATE devices SET removed_at=? WHERE user_id=? AND removed_at IS NULL', (now, uid))
        db.execute('UPDATE users SET device_hash=? WHERE id=?', (device_hash, uid))
        if device_hash:
            db.execute('INSERT INTO devices(user_id,device_hash,created_at) VALUES (?,?,?)', (uid, device_hash, now))

    def _public(self, db, method, path, data):
        now = self.clock()
        if method == 'GET' and path == '/v1/health':
            return {'status': 'ok', 'version': VERSION}
        if method == 'GET' and path == '/v1/status':
            row = db.execute("SELECT value FROM settings WHERE key='maintenance'").fetchone()
            return {'maintenance': json.loads(row['value']) if row else {'enabled': False, 'message': ''}}
        if method == 'GET' and path == '/v1/updates/beta':
            best = None
            for row in db.execute("SELECT body,created_at FROM content WHERE kind='release' ORDER BY id DESC LIMIT 200"):
                body = json.loads(row['body'])
                url, digest, version = body.get('url'), body.get('sha256'), body.get('version')
                if (body.get('app', 'member') == 'member' and isinstance(url, str) and url.startswith('https://')
                        and isinstance(digest, str) and re.fullmatch(r'[0-9a-fA-F]{64}', digest)
                        and isinstance(version, str) and re.fullmatch(r'\d+(\.\d+){0,3}', version)):
                    key = tuple(int(p) for p in version.split('.'))
                    if best is None or key > best[0]:
                        best = (key, {'version': version, 'url': url, 'sha256': digest.lower(), 'notes': str(body.get('notes', ''))[:2000], 'published_at': row['created_at']})
            if best:
                return best[1]
            fail(404, 'no_update', 'No published update is available.')
        if method == 'GET' and path == '/v1/updates/latest':
            # Public: the auto-updater runs before sign-in. Only stable member-app releases
            # with an HTTPS package and a SHA-256 are offered; Manager builds never are.
            for row in db.execute("SELECT body,created_at FROM content WHERE kind='release' AND channel='stable' ORDER BY id DESC LIMIT 200"):
                body = json.loads(row['body'])
                url, digest, version = body.get('url'), body.get('sha256'), body.get('version')
                if (body.get('app', 'member') == 'member' and isinstance(url, str) and url.startswith('https://')
                        and isinstance(digest, str) and re.fullmatch(r'[0-9a-fA-F]{64}', digest)
                        and isinstance(version, str) and re.fullmatch(r'\d+(\.\d+){0,3}', version)):
                    return {'version': version, 'url': url, 'sha256': digest.lower(), 'notes': str(body.get('notes', ''))[:2000],
                            'published_at': row['created_at']}
            fail(404, 'no_update', 'No published update is available.')
        if method == 'POST' and path == '/v1/license/validate':
            license = db.execute("SELECT * FROM licenses WHERE key_hash=? AND status='active'", (_hash(_text(data.get('key'), 'License key', 16, 128)),)).fetchone()
            if not license or license['redeemed_at'] is not None:
                fail(409, 'invalid_license', 'License is invalid, unavailable, or already redeemed.')
            return {'tier': license['tier'], 'duration_days': license['duration_days'], 'permanent': license['duration_days'] is None}
        if method == 'POST' and path == '/v1/auth/register':
            username, password = _username(data.get('username')), _password(data.get('password'))
            moderation = moderate_username(username)
            device = self._device(data)
            license = db.execute('SELECT * FROM licenses WHERE key_hash=?', (_hash(_text(data.get('key'), 'License key', 16, 128)),)).fetchone()
            if not license or license['redeemed_at'] is not None or license['status'] != 'active':
                fail(409, 'invalid_license', 'License is invalid, unavailable, or already redeemed.')
            expires = now + license['duration_days'] * 86400 if license['duration_days'] is not None else None
            db.execute('UPDATE licenses SET redeemed_at=?,expires_at=? WHERE id=? AND redeemed_at IS NULL', (now, expires, license['id']))
            uid = db.execute('''INSERT INTO users(username,password_hash,license_id,created_at,moderation_status,
                             moderation_category,moderation_policy_version) VALUES (?,?,?,?,?,?,?)''',
                             (username, self._password_hash(password), license['id'], now, moderation.status,
                              moderation.category, moderation.policy_version)).lastrowid
            self._set_device(db, uid, device)
            codes = self._recovery_codes(db, uid)
            user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
            if moderation.status == 'pending':
                self._audit(db, uid, 'username_review_requested', 'user', uid,
                            policy_version=moderation.policy_version, category=moderation.category)
                return {'moderation_status': 'pending',
                        'review_message': 'Your account is paused while the owner reviews this username. Contact the owner for updates or a compliant rename.'}
            self._audit(db, uid, 'register', 'user', uid)
            return {**self._session(db, user, data.get('remember_me') is True), 'recovery_codes': codes}
        if method == 'POST' and path == '/v1/auth/login':
            user = self._credentials(db, data)
            self._check_access(db, user)
            if user['role'] == 'owner':
                self._mfa(db, user, data)
            device = self._device(data)
            if user['device_hash'] and not hmac.compare_digest(device, user['device_hash']):
                fail(403, 'device_mismatch', 'This account is registered to another PC. Request a device transfer.',
                     (user['id'], 'device_mismatch', 'Login from an unregistered installation was rejected.'))
            if not user['device_hash']:
                self._set_device(db, user['id'], device)
            result = self._session(db, user, data.get('remember_me') is True)
            self._audit(db, user['id'], 'login', 'user', user['id'])
            return result
        if method == 'POST' and path == '/v1/auth/refresh':
            refresh = _text(data.get('refresh_token'), 'Refresh token', 32, 256)
            row = db.execute('SELECT * FROM refresh_sessions WHERE token_hash=?', (_hash(refresh),)).fetchone()
            if not row:
                fail(401, 'refresh_invalid', 'Saved sign-in expired. Sign in again.')
            if row['revoked'] or row['used_at'] is not None:
                db.execute('UPDATE refresh_sessions SET revoked=1 WHERE user_id=?', (row['user_id'],))
                db.execute('UPDATE sessions SET revoked=1 WHERE user_id=?', (row['user_id'],))
                fail(401, 'refresh_replay', 'Saved sign-in was used more than once. Sign in again.', commit=True)
            if row['expires_at'] <= now:
                db.execute('UPDATE refresh_sessions SET revoked=1 WHERE id=?', (row['id'],))
                fail(401, 'refresh_expired', 'Saved sign-in expired. Sign in again.')
            user = db.execute('SELECT * FROM users WHERE id=?', (row['user_id'],)).fetchone()
            self._check_access(db, user)
            db.execute('UPDATE refresh_sessions SET used_at=?,revoked=1 WHERE id=?', (now, row['id']))
            db.execute('UPDATE sessions SET revoked=1 WHERE user_id=? AND revoked=0', (user['id'],))
            result = self._session(db, user, True)
            self._audit(db, user['id'], 'session_refresh', 'user', user['id'])
            return result
        if method == 'POST' and path == '/v1/auth/recover':
            username, password = _text(data.get('username'), 'Username', 1, 128), _password(data.get('new_password'))
            user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
            valid = False
            if user:
                if data.get('recovery_code'):
                    valid = self._consume_recovery(db, user, data['recovery_code'])
                elif isinstance(data.get('reset_token'), str) and len(data['reset_token']) <= 256:
                    valid = bool(db.execute('UPDATE reset_credentials SET used_at=? WHERE user_id=? AND token_hash=? AND used_at IS NULL AND expires_at>?',
                                            (now, user['id'], _hash(data['reset_token']), now)).rowcount)
            if not valid:
                fail(401, 'invalid_credentials', 'Username or recovery credential is incorrect or expired.')
            db.execute('UPDATE users SET password_hash=? WHERE id=?', (self._password_hash(password), user['id']))
            db.execute('UPDATE sessions SET revoked=1 WHERE user_id=?', (user['id'],))
            db.execute('UPDATE refresh_sessions SET revoked=1 WHERE user_id=?', (user['id'],))
            db.execute('UPDATE reset_credentials SET used_at=? WHERE user_id=? AND used_at IS NULL', (now, user['id']))
            self._audit(db, user['id'], 'password_recovered', 'user', user['id'])
            return {'message': 'Password changed. Sign in again on your registered PC.'}
        if method == 'POST' and path == '/v1/device/request':
            user = self._credentials(db, data)
            self._check_access(db, user)
            device = self._device(data)
            reason = _text(data.get('reason'), 'Reason', 3, 1000)
            if user['role'] == 'owner':
                fail(403, 'owner_device', 'Owner device reset requires server operator assistance.')
            if device == user['device_hash']:
                fail(400, 'same_device', 'This PC is already registered.')
            self._cooldown(db, user, 'transfer')
            db.execute('INSERT INTO transfers(user_id,device_hash,reason,created_at) VALUES (?,?,?,?)', (user['id'], device, reason, now))
            count = db.execute('SELECT count(*) FROM transfers WHERE user_id=? AND created_at>?', (user['id'], now - 30 * 86400)).fetchone()[0]
            if count >= 3:
                db.execute('INSERT INTO alerts(user_id,kind,message,created_at) VALUES (?,?,?,?)', (user['id'], 'repeated_device_changes', 'Repeated device-transfer requests in the last 30 days.', now))
            return {'message': 'Device transfer requested. The owner must approve it.'}
        return None

    def _require_feature(self, session, feature):
        if feature not in FEATURES:
            fail(400, 'invalid_feature', 'Unknown feature.')
        if not json.loads(session['snapshot'])['permissions'].get(feature, False):
            fail(403, 'feature_locked', 'contact the owner for upgrading')

    def _dispatch(self, db, method, path, query, data, token):
        public = self._public(db, method, path, data)
        if public is not None:
            return public
        user, session = self._authorize(db, token, owner=path.startswith('/v1/admin/'))
        if path.startswith('/v1/admin/'):
            return self._admin(db, user, method, path, query, data)
        uid, now = user['id'], self.clock()
        if (method, path) in (('POST', '/v1/session/heartbeat'), ('GET', '/v1/me')):
            if method == 'POST':
                db.execute('UPDATE sessions SET renewed_at=?,lease_until=? WHERE id=?', (now, min(now + LEASE_SECONDS, session['absolute_until']), session['id']))
            return self._metadata(db, user, session)
        if method == 'POST' and path == '/v1/auth/logout':
            db.execute('UPDATE sessions SET revoked=1 WHERE id=?', (session['id'],))
            db.execute('UPDATE refresh_sessions SET revoked=1 WHERE user_id=?', (user['id'],))
            return {'message': 'Signed out.'}
        if method == 'POST' and path == '/v1/auth/recovery-codes':
            self._limit(('regenerate_recovery', uid), 10, 900)
            if not self._password_verify(data.get('password'), user['password_hash']):
                fail(401, 'invalid_credentials', 'Password is incorrect.')
            self._audit(db, uid, 'recovery_codes_replaced', 'user', uid)
            return {'recovery_codes': self._recovery_codes(db, uid)}
        vote = re.fullmatch(r'/v1/content/(\d+)/vote', path)
        if method == 'POST' and vote:
            cid, option = int(vote[1]), data.get('option')
            row = db.execute("SELECT body FROM content WHERE id=? AND kind='announcement'", (cid,)).fetchone()
            poll = json.loads(row['body']).get('poll') if row else None
            if not isinstance(poll, dict):
                fail(404, 'not_found', 'Poll not found.')
            if type(option) is not int or not 0 <= option < len(poll.get('options', [])):
                fail(400, 'invalid_option', 'Choose one of the poll options.')
            db.execute('INSERT INTO poll_votes(content_id,user_id,option,created_at) VALUES (?,?,?,?) '
                       'ON CONFLICT(content_id,user_id) DO UPDATE SET option=excluded.option,created_at=excluded.created_at', (cid, uid, option, now))
            item = {'id': cid, 'body': json.loads(row['body'])}
            self._polls(db, [item], uid)
            return item['poll_results']
        if method == 'GET' and path == '/v1/feedback':
            rows = db.execute('SELECT f.id,f.message,f.created_at,r.message AS reply,r.created_at AS replied_at FROM feedback f '
                              'LEFT JOIN feedback_replies r ON r.feedback_id=f.id WHERE f.user_id=? ORDER BY f.id DESC LIMIT 50', (uid,))
            return {'feedback': [dict(r) for r in rows]}
        react = re.fullmatch(r'/v1/content/(\d+)/react', path)
        if method == 'POST' and react:
            cid, reaction = int(react[1]), data.get('reaction')
            row = db.execute("SELECT id FROM content WHERE id=? AND kind='announcement'", (cid,)).fetchone()
            if not row:
                fail(404, 'not_found', 'Announcement not found.')
            if reaction is None:
                db.execute('DELETE FROM reactions WHERE content_id=? AND user_id=?', (cid, uid))
            elif reaction in REACTIONS:
                db.execute('INSERT INTO reactions(content_id,user_id,reaction,created_at) VALUES (?,?,?,?) '
                           'ON CONFLICT(content_id,user_id) DO UPDATE SET reaction=excluded.reaction,created_at=excluded.created_at',
                           (cid, uid, reaction, now))
            else:
                fail(400, 'invalid_reaction', 'Choose a listed reaction.')
            return self._reactions(db, [cid], uid)[cid]
        if method == 'GET' and path == '/v1/content':
            content = self._content(db, history=False)
            counts = self._reactions(db, [a['id'] for a in content['announcements']], uid)
            for item in content['announcements']:
                item['reactions'] = counts.get(item['id'], {'counts': {}, 'mine': None})
            self._polls(db, content['announcements'], uid)
            snapshot = json.loads(session['snapshot'])
            if not snapshot['permissions']['owner_presets']:
                content['presets'] = []
            if not snapshot['permissions']['beta']:
                content['presets'] = [x for x in content['presets'] if x['channel'] != 'beta']
                content['releases'] = [x for x in content['releases'] if x['channel'] != 'beta']
            content.pop('welcomes')
            content['welcome'] = snapshot['welcome']
            return content
        if method == 'POST' and path == '/v1/tools/authorize':
            feature = data.get('feature')
            self._require_feature(session, feature)
            settings = _object(data.get('settings', {}), 'Settings').copy()
            settings.update(json.loads(session['snapshot'])['enforced'].get(feature, {}))
            if feature in ('performance', 'potato', 'advanced'):
                if settings.get('preset') == 'potato':
                    self._require_feature(session, 'potato')
                if settings.get('advanced') or settings.get('preset') == 'custom':
                    self._require_feature(session, 'advanced')
            return {'settings': settings}
        if path in ('/v1/profiles', '/v1/profiles/import') or re.fullmatch(r'/v1/profiles/\d+', path):
            self._require_feature(session, 'profiles')
            if method == 'POST' and path == '/v1/profiles/import':
                profiles = data.get('profiles')
                if not isinstance(profiles, list) or not 1 <= len(profiles) <= 100:
                    fail(400, 'invalid_profiles', 'Import must contain between 1 and 100 profiles.')
                prepared, names = [], set()
                for item in profiles:
                    if not isinstance(item, dict) or set(item) != {'name', 'config'}:
                        fail(400, 'invalid_profiles', 'Imported profile contains unsupported fields.')
                    name = _text(item.get('name'), 'Profile name', 1, 80)
                    config = _object(item.get('config'), 'Profile configuration', 16384)
                    if set(config) != {'kind', 'config'} or config.get('kind') not in ('single_edit', 'drag', *EXTENDED_MACROS) or not isinstance(config.get('config'), dict):
                        fail(400, 'invalid_profiles', 'Imported macro profile is unsupported.')
                    if name.casefold() in names:
                        fail(400, 'invalid_profiles', 'Imported profile names must be unique.')
                    names.add(name.casefold())
                    prepared.append((name, config))
                for name, _ in prepared:
                    if db.execute('SELECT 1 FROM profiles WHERE user_id=? AND lower(name)=lower(?)', (uid, name)).fetchone():
                        fail(409, 'profile_conflict', 'A profile with an imported name already exists. Rename it before importing.')
                created=[]
                for name, config in prepared:
                    pid=db.execute('INSERT INTO profiles(user_id,name,config,created_at) VALUES (?,?,?,?)', (uid,name,_json(config),now)).lastrowid
                    created.append({'id':pid,'name':name,'config':config,'created_at':now})
                return {'profiles':created}
            if method == 'GET' and path == '/v1/profiles':
                return {'profiles': [{'id': r['id'], 'name': r['name'], 'config': json.loads(r['config']), 'created_at': r['created_at']} for r in db.execute('SELECT * FROM profiles WHERE user_id=? ORDER BY id', (uid,))]}
            if method == 'POST' and path == '/v1/profiles':
                name, config = _text(data.get('name'), 'Profile name', 1, 80), _object(data.get('config'), 'Configuration')
                if 'id' in data:
                    pid = _number(data['id'], 'Profile identifier', 1, 2**63 - 1)
                    if not isinstance(pid, int):
                        fail(400, 'invalid_input', 'Profile identifier must be an integer.')
                    if not db.execute('UPDATE profiles SET name=?,config=? WHERE id=? AND user_id=?', (name, _json(config), pid, uid)).rowcount:
                        fail(404, 'not_found', 'Profile not found.')
                    created = db.execute('SELECT created_at FROM profiles WHERE id=?', (pid,)).fetchone()[0]
                    return {'id': pid, 'name': name, 'config': config, 'created_at': created}
                if db.execute('SELECT count(*) FROM profiles WHERE user_id=?', (uid,)).fetchone()[0] >= 100:
                    fail(409, 'profile_limit', 'Maximum of 100 profiles reached.')
                pid = db.execute('INSERT INTO profiles(user_id,name,config,created_at) VALUES (?,?,?,?)', (uid, name, _json(config), now)).lastrowid
                return {'id': pid, 'name': name, 'config': config, 'created_at': now}
            if method == 'DELETE' and path != '/v1/profiles':
                if not db.execute('DELETE FROM profiles WHERE id=? AND user_id=?', (int(path.rsplit('/', 1)[1]), uid)).rowcount:
                    fail(404, 'not_found', 'Profile not found.')
                return {'message': 'Profile deleted.'}
        if method == 'POST' and path == '/v1/feedback':
            self._limit(('feedback', uid), 5, 3600)
            message = _text(data.get('message'), 'Feedback', 1, 4000)
            diagnostics = _object(data['diagnostics'], 'Diagnostics', 16384) if 'diagnostics' in data else None
            fid = db.execute('INSERT INTO feedback(user_id,message,diagnostics,created_at) VALUES (?,?,?,?)', (uid, message, _json(diagnostics) if diagnostics else None, now)).lastrowid
            return {'id': fid, 'message': 'Feedback sent.'}
        fail(404, 'not_found', 'Route not found.')

    def _cooldown(self, db, user, kind):
        hours = json.loads(db.execute('SELECT value FROM settings WHERE key=?', (kind + '_cooldown_hours',)).fetchone()[0])
        last = user['last_' + kind + '_at']
        if last is not None and last + hours * 3600 > self.clock():
            fail(409, 'cooldown', f'{kind.capitalize()} cooldown has not elapsed.')

    def _user_details(self, db, uid):
        user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        if not user:
            fail(404, 'not_found', 'User not found.')
        return {'user': self._public_user(user), 'license': self._license(db.execute('SELECT * FROM licenses WHERE id=?', (user['license_id'],)).fetchone()),
                'sessions': [dict(r) for r in db.execute('SELECT id,created_at,renewed_at,lease_until,revoked FROM sessions WHERE user_id=? ORDER BY id DESC LIMIT 100', (uid,))],
                'devices': [dict(r) for r in db.execute('SELECT id,created_at,removed_at FROM devices WHERE user_id=? ORDER BY id DESC LIMIT 100', (uid,))]}

    def _new_license(self, db, tier, days, **fields):
        key = 'ST-' + secrets.token_urlsafe(24)
        lid = db.execute('INSERT INTO licenses(key_hash,key_hint,tier,duration_days,created_at,redeemed_at,expires_at,overrides,enforced,welcome) VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (_hash(key), key[-6:], tier, days, self.clock(), fields.get('redeemed_at'), fields.get('expires_at'), fields.get('overrides', '{}'), fields.get('enforced', '{}'), fields.get('welcome', '{}'))).lastrowid
        return key, self._license(db.execute('SELECT * FROM licenses WHERE id=?', (lid,)).fetchone())

    def _polls(self, db, items, uid=None):
        for item in items:
            poll = item['body'].get('poll') if isinstance(item.get('body'), dict) else None
            if not isinstance(poll, dict):
                continue
            counts = [0] * len(poll.get('options', []))
            for row in db.execute('SELECT option,COUNT(*) AS n FROM poll_votes WHERE content_id=? GROUP BY option', (item['id'],)):
                if 0 <= row['option'] < len(counts):
                    counts[row['option']] = row['n']
            mine = db.execute('SELECT option FROM poll_votes WHERE content_id=? AND user_id=?', (item['id'], uid)).fetchone() if uid else None
            item['poll_results'] = {'counts': counts, 'mine': mine['option'] if mine else None}

    def _reactions(self, db, ids, uid=None):
        result = {cid: {'counts': {}, 'mine': None} for cid in ids}
        if not ids:
            return result
        marks = ','.join('?' * len(ids))
        for row in db.execute(f'SELECT content_id,reaction,COUNT(*) AS n FROM reactions WHERE content_id IN ({marks}) GROUP BY content_id,reaction', ids):
            result[row['content_id']]['counts'][row['reaction']] = row['n']
        if uid is not None:
            for row in db.execute(f'SELECT content_id,reaction FROM reactions WHERE user_id=? AND content_id IN ({marks})', [uid, *ids]):
                result[row['content_id']]['mine'] = row['reaction']
        return result

    def _content(self, db, history):
        result = {'presets': [], 'announcements': [], 'releases': [], 'welcomes': []}
        seen = set()
        for row in db.execute('SELECT * FROM content ORDER BY id DESC LIMIT 2000'):
            identity = (row['kind'], row['name'], row['channel'], row['tier'])
            if not history and identity in seen:
                continue
            seen.add(identity)
            item = dict(row)
            item['body'] = json.loads(item['body'])
            result[{'preset': 'presets', 'announcement': 'announcements', 'release': 'releases', 'welcome': 'welcomes'}[row['kind']]].append(item)
        return result

    def _admin(self, db, owner, method, path, query, data):
        now, actor = self.clock(), owner['id']
        if method == 'GET' and path == '/v1/admin/moderation':
            queue = [dict(r) for r in db.execute("SELECT id,username,created_at,moderation_category,moderation_policy_version,moderation_status FROM users WHERE moderation_status='pending' ORDER BY created_at")]
            return {'queue': queue}
        moderation_match = re.fullmatch(r'/v1/admin/moderation/(\d+)', path)
        if method == 'POST' and moderation_match:
            uid = int(moderation_match[1])
            target = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
            if not target or target['moderation_status'] not in ('pending', 'rejected'):
                fail(409, 'moderation_unavailable', 'This account does not need username review.')
            action = data.get('action')
            if action == 'reject':
                reason = _text(data.get('reason'), 'Review reason', 3, 500)
                db.execute("UPDATE users SET moderation_status='rejected' WHERE id=?", (uid,))
                db.execute('UPDATE sessions SET revoked=1 WHERE user_id=?', (uid,))
                db.execute('UPDATE refresh_sessions SET revoked=1 WHERE user_id=?', (uid,))
                self._audit(db, actor, 'username_review_rejected', 'user', uid, reason=reason)
                return {'moderation_status': 'rejected', 'message': 'Account remains paused. The user may contact the owner to request a compliant rename.'}
            if action == 'rename':
                username = _username(data.get('username'))
                moderation = moderate_username(username)
                if moderation.status != 'clear':
                    fail(400, 'username_policy', 'Choose a username that follows the community rules.')
                db.execute("UPDATE users SET username=?,moderation_status='clear',moderation_category=NULL,moderation_policy_version=? WHERE id=?",
                           (username, moderation.policy_version, uid))
                self._audit(db, actor, 'username_review_renamed', 'user', uid,
                            old_username=target['username'], new_username=username, policy_version=moderation.policy_version)
                return {'moderation_status': 'clear', 'message': 'Username updated and account access restored.'}
            if action == 'approve':
                reason = _text(data.get('reason'), 'Review reason', 3, 500)
                db.execute("UPDATE users SET moderation_status='clear' WHERE id=?", (uid,))
                self._audit(db, actor, 'username_review_exception_approved', 'user', uid,
                            reason=reason, policy_version=target['moderation_policy_version'], category=target['moderation_category'])
                return {'moderation_status': 'clear', 'message': 'Owner-reviewed exception approved. Account access restored.'}
            fail(400, 'invalid_action', 'Choose approve, rename, or reject.')
        if method == 'GET' and path == '/v1/admin/overview':
            return {'users': db.execute('SELECT count(*) FROM users').fetchone()[0], 'licenses': db.execute('SELECT count(*) FROM licenses').fetchone()[0],
                    'active_sessions': db.execute('SELECT count(*) FROM sessions WHERE revoked=0 AND lease_until>? AND absolute_until>?', (now, now)).fetchone()[0],
                    'alerts': [dict(r) for r in db.execute('SELECT * FROM alerts ORDER BY id DESC LIMIT 100')]}
        if method == 'GET' and path == '/v1/admin/users':
            q = query.get('q', [''])[0][:100].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            return {'users': [self._public_user(r) for r in db.execute("SELECT * FROM users WHERE username LIKE ? ESCAPE '\\' ORDER BY username LIMIT 500", ('%' + q + '%',))]}
        match = re.fullmatch(r'/v1/admin/users/(\d+)', path)
        if match:
            uid = int(match[1])
            if method == 'GET':
                return self._user_details(db, uid)
            if method == 'POST':
                return self._admin_user(db, actor, uid, data, owner['role'])
        if method == 'GET' and path == '/v1/admin/licenses':
            return {'licenses': [self._license(r) for r in db.execute('SELECT * FROM licenses ORDER BY id DESC LIMIT 2000')]}
        if method == 'POST' and path == '/v1/admin/licenses':
            tier = data.get('tier')
            if tier not in TIERS:
                fail(400, 'invalid_tier', 'Unknown tier.')
            days = data.get('duration_days')
            if tier == 'Sacred' and days not in (None, 30):
                fail(400, 'invalid_duration', 'Sacred access is 30 days or lifetime.')
            if days is not None:
                _number(days, 'Duration', 0.00001, 36500)
            count = _number(data.get('count', 1), 'Count', 1, 100)
            if not isinstance(count, int):
                fail(400, 'invalid_input', 'Count must be an integer.')
            generated = [self._new_license(db, tier, days) for _ in range(count)]
            self._audit(db, actor, 'licenses_created', 'license', count=count, tier=tier, duration_days=days)
            return {'keys': [g[0] for g in generated], 'licenses': [g[1] for g in generated]}
        match = re.fullmatch(r'/v1/admin/licenses/(\d+)', path)
        if method == 'POST' and match:
            return self._admin_license(db, actor, int(match[1]), data)
        if method == 'GET' and path == '/v1/admin/transfers':
            return {'transfers': [dict(r) for r in db.execute('SELECT t.id,t.user_id,u.username,t.reason,t.created_at,t.status,t.resolved_at FROM transfers t JOIN users u ON t.user_id=u.id ORDER BY t.id DESC LIMIT 500')]}
        match = re.fullmatch(r'/v1/admin/transfers/(\d+)', path)
        if method == 'POST' and match:
            transfer = db.execute('SELECT * FROM transfers WHERE id=?', (int(match[1]),)).fetchone()
            if not transfer or transfer['status'] != 'pending':
                fail(409, 'transfer_unavailable', 'Transfer is unavailable or already resolved.')
            if not isinstance(data.get('approve'), bool):
                fail(400, 'invalid_input', 'Approve must be true or false.')
            user = db.execute('SELECT * FROM users WHERE id=?', (transfer['user_id'],)).fetchone()
            if data['approve']:
                self._cooldown(db, user, 'transfer')
                self._set_device(db, user['id'], transfer['device_hash'])
                db.execute('UPDATE users SET last_transfer_at=? WHERE id=?', (now, user['id']))
                db.execute('UPDATE sessions SET revoked=1 WHERE user_id=?', (user['id'],))
                db.execute('UPDATE refresh_sessions SET revoked=1 WHERE user_id=?', (user['id'],))
            db.execute('UPDATE transfers SET status=?,resolved_at=?,resolved_by=? WHERE id=?', ('approved' if data['approve'] else 'rejected', now, actor, transfer['id']))
            self._audit(db, actor, 'transfer_approved' if data['approve'] else 'transfer_rejected', 'transfer', transfer['id'], user_id=user['id'])
            return {'message': 'Transfer approved.' if data['approve'] else 'Transfer rejected.'}
        if method == 'GET' and path == '/v1/admin/audit':
            return {'audit': [{**dict(r), 'details': json.loads(r['details'])} for r in db.execute('SELECT a.*,u.username AS actor_username,u.role AS actor_role FROM audit a LEFT JOIN users u ON a.actor_id=u.id ORDER BY a.id DESC LIMIT 1000')]}
        if method == 'GET' and path == '/v1/admin/content':
            content = self._content(db, history=True)
            counts = self._reactions(db, [a['id'] for a in content['announcements']])
            for item in content['announcements']:
                item['reactions'] = counts[item['id']]
            self._polls(db, content['announcements'])
            return content
        if method == 'POST' and path == '/v1/admin/content':
            kind, channel, tier = data.get('kind'), data.get('channel', 'stable'), data.get('tier')
            if kind not in ('preset', 'announcement', 'release', 'welcome') or channel not in ('stable', 'beta') or (tier is not None and tier not in TIERS) or (kind == 'welcome' and tier not in TIERS):
                fail(400, 'invalid_input', 'Invalid content kind, channel or tier.')
            name, body = _text(data.get('name'), 'Name', 1, 120), _object(data.get('body'), 'Content body')
            if 'poll' in body:
                poll = body['poll']
                if (kind != 'announcement' or not isinstance(poll, dict) or not isinstance(poll.get('options'), list)
                        or not 2 <= len(poll['options']) <= 6):
                    fail(400, 'invalid_poll', 'Polls need a question and 2-6 options on an announcement.')
                body['poll'] = {'question': _text(poll.get('question'), 'Poll question', 1, 120),
                                'options': [_text(o, 'Poll option', 1, 60) for o in poll['options']]}
            _validate_content_urls(body)
            version = db.execute('SELECT coalesce(max(version),0)+1 FROM content WHERE kind=? AND name=? AND channel=? AND tier IS ?', (kind, name, channel, tier)).fetchone()[0]
            cid = db.execute('INSERT INTO content(kind,name,body,channel,tier,version,created_at,author_id) VALUES (?,?,?,?,?,?,?,?)', (kind, name, _json(body), channel, tier, version, now, actor)).lastrowid
            self._audit(db, actor, 'content_published', 'content', cid, kind=kind, version=version)
            return {'id': cid, 'kind': kind, 'name': name, 'body': body, 'channel': channel, 'tier': tier, 'version': version, 'created_at': now}
        if method == 'GET' and path == '/v1/admin/feedback':
            return {'feedback': [{**dict(r), 'diagnostics': json.loads(r['diagnostics']) if r['diagnostics'] else None} for r in db.execute('SELECT f.*,u.username,r.message AS reply,r.created_at AS replied_at FROM feedback f JOIN users u ON f.user_id=u.id LEFT JOIN feedback_replies r ON r.feedback_id=f.id ORDER BY f.id DESC LIMIT 1000')]}
        reply = re.fullmatch(r'/v1/admin/feedback/(\d+)/reply', path)
        if method == 'POST' and reply:
            fid, message = int(reply[1]), _text(data.get('message'), 'Reply', 1, 2000)
            if not db.execute('SELECT id FROM feedback WHERE id=?', (fid,)).fetchone():
                fail(404, 'not_found', 'Feedback not found.')
            db.execute('INSERT INTO feedback_replies(feedback_id,message,author_id,created_at) VALUES (?,?,?,?) '
                       'ON CONFLICT(feedback_id) DO UPDATE SET message=excluded.message,author_id=excluded.author_id,created_at=excluded.created_at', (fid, message, actor, now))
            self._audit(db, actor, 'feedback_replied', 'feedback', fid)
            return {'replied': True}
        if path == '/v1/admin/settings' and method == 'POST' and owner['role'] != 'owner':
            fail(403, 'owner_required', 'Only the owner can change owner settings.')
        if path == '/v1/admin/settings' and method in ('GET', 'POST'):
            if method == 'POST':
                if not data or any(k not in ('transfer_cooldown_hours', 'reset_cooldown_hours', 'maintenance') for k in data):
                    fail(400, 'invalid_input', 'Unknown or missing setting.')
                if 'maintenance' in data:
                    m = data.pop('maintenance')
                    if not isinstance(m, dict) or type(m.get('enabled')) is not bool:
                        fail(400, 'invalid_input', 'Maintenance needs enabled true/false and a message.')
                    value = {'enabled': m['enabled'], 'message': _text(m.get('message') or 'Scheduled maintenance.', 'Maintenance message', 1, 200)}
                    db.execute("INSERT INTO settings(key,value) VALUES ('maintenance',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (_json(value),))
                    self._audit(db, actor, 'maintenance_updated', 'settings', **value)
                for key, value in data.items():
                    _number(value, key, 0, 8760)
                    db.execute('UPDATE settings SET value=? WHERE key=?', (_json(value), key))
                self._audit(db, actor, 'settings_updated', 'settings', **data)
            return {r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM settings')}
        fail(404, 'not_found', 'Route not found.')

    def _admin_user(self, db, actor, uid, data, actor_role='owner'):
        now = self.clock()
        user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        if not user:
            fail(404, 'not_found', 'User not found.')
        action = data.get('action')
        if action not in ('rename', 'ban', 'unban', 'terminate_sessions', 'reset_device', 'reset_password', 'set_role'):
            fail(400, 'invalid_action', 'Unknown account action.')
        if actor_role != 'owner' and (user['role'] in ('owner', 'admin') or action == 'set_role'):
            fail(403, 'owner_required', 'Only the owner can manage admin accounts.')
        if user['role'] == 'owner' and action in ('ban', 'reset_device', 'reset_password'):
            fail(403, 'owner_protected', 'This operation cannot target the owner account.')
        result = {'message': 'Account updated.'}
        details = {}
        if action == 'rename':
            username = _username(data.get('username'))
            moderation = moderate_username(username)
            db.execute('UPDATE users SET username=?,moderation_status=?,moderation_category=?,moderation_policy_version=? WHERE id=?',
                       (username, moderation.status, moderation.category, moderation.policy_version, uid))
            if moderation.status != 'clear':
                db.execute('UPDATE sessions SET revoked=1 WHERE user_id=?', (uid,))
                db.execute('UPDATE refresh_sessions SET revoked=1 WHERE user_id=?', (uid,))
            details = {'old_username': user['username'], 'new_username': username,
                       'moderation_status': moderation.status, 'policy_version': moderation.policy_version}
        elif action == 'ban':
            reason = _text(data.get('reason'), 'Reason', 1, 500)
            until = data.get('until')
            if until is not None:
                _number(until, 'Ban expiration', now + 1, now + 36500 * 86400)
            db.execute('UPDATE users SET banned=1,ban_until=?,ban_reason=? WHERE id=?', (until, reason, uid))
            details = {'reason': reason, 'until': until}
        elif action == 'unban':
            db.execute('UPDATE users SET banned=0,ban_until=NULL,ban_reason=NULL WHERE id=?', (uid,))
        elif action == 'set_role':
            role = data.get('role')
            if role not in ('admin', 'member'):
                fail(400, 'invalid_role', 'Choose admin or member.')
            if user['role'] == 'owner':
                fail(403, 'owner_protected', 'The owner role cannot be changed.')
            db.execute('UPDATE users SET role=? WHERE id=?', (role, uid))
            # Sign the account out so the new role applies on the next login.
            db.execute('UPDATE sessions SET revoked=1 WHERE user_id=?', (uid,))
            db.execute('UPDATE refresh_sessions SET revoked=1 WHERE user_id=?', (uid,))
            details = {'old_role': user['role'], 'new_role': role}
            action = 'role_changed'
        elif action == 'terminate_sessions':
            db.execute('UPDATE sessions SET revoked=1 WHERE user_id=?', (uid,))
            db.execute('UPDATE refresh_sessions SET revoked=1 WHERE user_id=?', (uid,))
        elif action == 'reset_device':
            self._cooldown(db, user, 'transfer')
            device = self._device(data) if data.get('device_id') else None
            self._set_device(db, uid, device)
            db.execute('UPDATE users SET last_transfer_at=? WHERE id=?', (now, uid))
            db.execute('UPDATE sessions SET revoked=1 WHERE user_id=?', (uid,))
            db.execute('UPDATE refresh_sessions SET revoked=1 WHERE user_id=?', (uid,))
            db.execute("UPDATE transfers SET status='cancelled',resolved_at=?,resolved_by=? WHERE user_id=? AND status='pending'", (now, actor, uid))
        elif action == 'reset_password':
            self._cooldown(db, user, 'reset')
            token = secrets.token_urlsafe(32)
            db.execute('UPDATE reset_credentials SET used_at=? WHERE user_id=? AND used_at IS NULL', (now, uid))
            db.execute('INSERT INTO reset_credentials(user_id,token_hash,expires_at) VALUES (?,?,?)', (uid, _hash(token), now + 900))
            db.execute('UPDATE sessions SET revoked=1 WHERE user_id=?', (uid,))
            db.execute('UPDATE refresh_sessions SET revoked=1 WHERE user_id=?', (uid,))
            db.execute('UPDATE users SET last_reset_at=? WHERE id=?', (now, uid))
            result.update(reset_token=token, expires_at=now + 900)
        self._audit(db, actor, action, 'user', uid, **details)
        return result

    def _admin_license(self, db, actor, lid, data):
        license = db.execute('SELECT * FROM licenses WHERE id=?', (lid,)).fetchone()
        if not license:
            fail(404, 'not_found', 'License not found.')
        action = data.get('action')
        if action not in ('update', 'extend', 'suspend', 'resume', 'revoke', 'replace'):
            fail(400, 'invalid_action', 'Unknown license action.')
        details = {}
        if action == 'update':
            if 'tier' in data:
                if data['tier'] not in TIERS:
                    fail(400, 'invalid_tier', 'Unknown tier.')
                db.execute('UPDATE licenses SET tier=? WHERE id=?', (data['tier'], lid))
                details['tier'] = data['tier']
            if 'days' in data:
                if license['redeemed_at'] is not None:
                    fail(409, 'already_redeemed', 'Use extend to change a redeemed license duration.')
                days = data['days']
                if days is not None:
                    _number(days, 'Duration', 0.00001, 36500)
                db.execute('UPDATE licenses SET duration_days=? WHERE id=?', (days, lid))
                details['duration_days'] = days
            for field in ('overrides', 'enforced', 'welcome'):
                if field in data:
                    value = _object(data[field], field, 8192)
                    if field in ('overrides', 'enforced') and any(f not in FEATURES for f in value):
                        fail(400, 'invalid_feature', 'Unknown permission feature.')
                    if field == 'overrides' and any(v is not None and not isinstance(v, bool) for v in value.values()):
                        fail(400, 'invalid_input', 'Overrides must be true, false or null (inherit).')
                    if field == 'enforced':
                        for feature, settings in value.items():
                            _validate_enforced(feature, settings)
                    if field == 'welcome':
                        _validate_content_urls(value)
                    db.execute(f'UPDATE licenses SET {field}=? WHERE id=?', (_json(value), lid))
                    details[field] = value
        elif action == 'extend':
            days = _number(data.get('days'), 'Extension days', 0.00001, 36500)
            if license['duration_days'] is None:
                fail(409, 'permanent_license', 'Permanent licenses do not need extensions.')
            expires = (license['expires_at'] + days * 86400) if license['redeemed_at'] is not None else None
            db.execute('UPDATE licenses SET duration_days=duration_days+?,expires_at=? WHERE id=?', (days, expires, lid))
            details['days'] = days
        elif action in ('suspend', 'resume', 'revoke'):
            if action == 'resume' and license['status'] == 'revoked':
                fail(409, 'license_revoked', 'Revoked licenses cannot be resumed. Use replacement.')
            db.execute('UPDATE licenses SET status=? WHERE id=?', ({'suspend': 'suspended', 'resume': 'active', 'revoke': 'revoked'}[action], lid))
        else:
            if license['replaced_by'] is not None:
                fail(409, 'already_replaced', 'This license has already been replaced.')
            key, replacement = self._new_license(db, license['tier'], license['duration_days'], **{f: license[f] for f in ('redeemed_at', 'expires_at', 'overrides', 'enforced', 'welcome')})
            db.execute('UPDATE licenses SET status=?,replaced_by=? WHERE id=?', ('revoked', replacement['id'], lid))
            db.execute('UPDATE users SET license_id=? WHERE license_id=?', (replacement['id'], lid))
            self._audit(db, actor, 'license_replaced', 'license', lid, replacement_id=replacement['id'])
            return {'key': key, 'license': replacement}
        self._audit(db, actor, 'license_' + action, 'license', lid, **details)
        return {'license': self._license(db.execute('SELECT * FROM licenses WHERE id=?', (lid,)).fetchone())}
