"""PostgreSQL storage for the existing licensing service.

The small SQL adapter covers only this service's queries. Transaction-scoped
advisory locking preserves SQLite's single-writer semantics across instances.
This favors correctness for a small installation over high write throughput.
"""
from contextlib import closing
import hashlib
from pathlib import Path
import re
import secrets
import sqlite3
import time

import psycopg
from psycopg.conninfo import conninfo_to_dict

from .service import Service, _json, fail

SERVICE_LOCK = 73910401
RATE_LOCK = 73910402
SCHEMA_LOCK = 73910403
ID_TABLES = frozenset(('licenses', 'users', 'sessions', 'recovery_codes',
                      'refresh_sessions', 'reset_credentials', 'devices', 'transfers', 'profiles',
                      'content', 'feedback', 'audit', 'alerts'))


EXTRA_SCHEMA = ['CREATE TABLE IF NOT EXISTS poll_votes (content_id BIGINT NOT NULL REFERENCES content(id), user_id BIGINT NOT NULL REFERENCES users(id), option INTEGER NOT NULL, created_at DOUBLE PRECISION NOT NULL, PRIMARY KEY(content_id, user_id))', 'CREATE TABLE IF NOT EXISTS feedback_replies (feedback_id BIGINT PRIMARY KEY REFERENCES feedback(id), message TEXT NOT NULL, author_id BIGINT NOT NULL REFERENCES users(id), created_at DOUBLE PRECISION NOT NULL)', 'INSERT INTO settings VALUES (\'maintenance\', \'{"enabled": false, "message": ""}\') ON CONFLICT DO NOTHING']
REACTIONS_TABLE = 'CREATE TABLE IF NOT EXISTS reactions (content_id BIGINT NOT NULL REFERENCES content(id), user_id BIGINT NOT NULL REFERENCES users(id), reaction TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL, PRIMARY KEY(content_id, user_id))'


class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def row_factory(cursor):
    names = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: Row(zip(names, values))


class Result:
    def __init__(self, cursor, inserted=False):
        self.cursor = cursor
        self.rowcount = cursor.rowcount
        self.lastrowid = cursor.fetchone()['id'] if inserted else None

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def __iter__(self):
        return iter(self.cursor)


class Connection:
    def __init__(self, url):
        try:
            self.raw = psycopg.connect(url, autocommit=True, row_factory=row_factory,
                                       connect_timeout=5, prepare_threshold=None)
            # SET in a transaction also works through a transaction pooler.
        except psycopg.OperationalError:
            raise sqlite3.OperationalError('Database unavailable') from None

    def execute(self, sql, params=()):
        try:
            if sql == 'BEGIN IMMEDIATE':
                self.raw.execute('BEGIN')
                self.raw.execute("SET LOCAL lock_timeout = '3s'")
                self.raw.execute("SET LOCAL statement_timeout = '8s'")
                return Result(self.raw.execute('SELECT pg_advisory_xact_lock(%s)', (SERVICE_LOCK,)))
            # All SQL templates are internal constants; values stay bound parameters.
            sql = sql.replace('%', '%%').replace('?', '%s')
            sql = sql.replace('WHERE username=%s', 'WHERE lower(username)=lower(%s)')
            sql = sql.replace('username LIKE ', 'username ILIKE ')
            sql = sql.replace('tier IS %s', 'tier IS NOT DISTINCT FROM %s')
            match = re.match(r'INSERT INTO (\w+)\b', sql)
            inserted = bool(match and match.group(1) in ID_TABLES)
            if inserted:
                sql += ' RETURNING id'
            return Result(self.raw.execute(sql, params or None), inserted)
        except psycopg.IntegrityError:
            raise sqlite3.IntegrityError('Database constraint conflict') from None
        except (psycopg.OperationalError, psycopg.errors.QueryCanceled):
            raise sqlite3.OperationalError('Database unavailable') from None

    def executemany(self, sql, rows):
        for row in rows:
            self.execute(sql, row)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class PostgresService(Service):
    def __init__(self, url, *, clock=time.time, password_cost=2**17):
        info = conninfo_to_dict(url)
        if info.get('host') not in ('localhost', '127.0.0.1', '::1') and info.get('sslmode') not in ('require', 'verify-ca', 'verify-full'):
            raise ValueError('Remote DATABASE_URL must require TLS')
        if not isinstance(password_cost, int) or password_cost < 1024 or password_cost & (password_cost - 1):
            raise ValueError('Invalid scrypt cost')
        self.url = url
        self.clock, self.password_cost = clock, password_cost
        self.dummy_password = self._password_hash(secrets.token_urlsafe(24))

    def connect(self):
        return Connection(self.url)

    def initialize_schema(self):
        # Explicit operator command; requests never create or migrate tables.
        with closing(self.connect()) as db:
            with db.raw.transaction():
                db.raw.execute('SELECT pg_advisory_xact_lock(%s)', (SCHEMA_LOCK,))
                db.raw.execute('CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)')
                versions = db.raw.execute('SELECT version FROM schema_version').fetchall()
                if versions:
                    if [row['version'] for row in versions] in ([1], [2]):
                        version = versions[0]['version']
                        if version == 1:
                            db.raw.execute('''CREATE TABLE IF NOT EXISTS refresh_sessions (
                                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                                token_hash TEXT NOT NULL UNIQUE,
                                user_id BIGINT NOT NULL REFERENCES users(id),
                                created_at DOUBLE PRECISION NOT NULL,
                                expires_at DOUBLE PRECISION NOT NULL,
                                used_at DOUBLE PRECISION,
                                revoked INTEGER NOT NULL DEFAULT 0)''')
                        db.raw.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS moderation_status TEXT NOT NULL DEFAULT 'clear'")
                        db.raw.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS moderation_category TEXT')
                        db.raw.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS moderation_policy_version INTEGER NOT NULL DEFAULT 1')
                        db.raw.execute('UPDATE schema_version SET version=3 WHERE version=%s', (version,))
                        db.raw.execute(REACTIONS_TABLE)
                        for statement in EXTRA_SCHEMA:
                            db.raw.execute(statement)
                        return
                    if [row['version'] for row in versions] != [3]:
                        raise RuntimeError('Unsupported PostgreSQL schema version')
                    db.raw.execute(REACTIONS_TABLE)  # Added after schema v3; idempotent.
                    for statement in EXTRA_SCHEMA:
                        db.raw.execute(statement)
                    return
                schema = Path(__file__).with_name('schema-postgres.sql').read_text()
                db.raw.execute(schema)
                db.raw.execute('INSERT INTO schema_version VALUES (3)')

    def _limit(self, key, count, window):
        # Commit attempts separately: failed logins must still consume their quota.
        digest = hashlib.sha256(_json(key).encode()).hexdigest()
        now = self.clock()
        denied = False
        try:
            with closing(self.connect()) as db:
                with db.raw.transaction():
                    db.raw.execute("SET LOCAL lock_timeout = '3s'")
                    db.raw.execute("SET LOCAL statement_timeout = '8s'")
                    db.raw.execute('SELECT pg_advisory_xact_lock(%s)', (RATE_LOCK,))
                    db.raw.execute('DELETE FROM rate_limits WHERE expires_at<=%s', (now,))
                    row = db.raw.execute('SELECT events FROM rate_limits WHERE key=%s', (digest,)).fetchone()
                    events = [event for event in row['events'] if event > now-window] if row else []
                    if len(events) >= count:
                        denied = True
                    elif not row and db.raw.execute('SELECT count(*) AS n FROM rate_limits').fetchone()['n'] >= 10000:
                        denied = True
                    else:
                        events.append(now)
                        db.raw.execute('INSERT INTO rate_limits(key,events,expires_at) VALUES (%s,%s,%s) ON CONFLICT(key) DO UPDATE SET events=EXCLUDED.events,expires_at=EXCLUDED.expires_at', (digest,events,now+window))
        except (psycopg.OperationalError, psycopg.errors.QueryCanceled):
            raise sqlite3.OperationalError('Rate limit store unavailable') from None
        if denied:
            fail(429,'rate_limited','Too many requests. Please try later.')
