CREATE TABLE IF NOT EXISTS licenses (
 id INTEGER PRIMARY KEY, key_hash TEXT NOT NULL UNIQUE, key_hint TEXT NOT NULL,
 tier TEXT NOT NULL, duration_days REAL, created_at REAL NOT NULL,
 redeemed_at REAL, expires_at REAL, status TEXT NOT NULL DEFAULT 'active',
 overrides TEXT NOT NULL DEFAULT '{}', enforced TEXT NOT NULL DEFAULT '{}',
 welcome TEXT NOT NULL DEFAULT '{}', replaced_by INTEGER REFERENCES licenses(id)
);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
 password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member',
 license_id INTEGER UNIQUE REFERENCES licenses(id), created_at REAL NOT NULL,
 device_hash TEXT, banned INTEGER NOT NULL DEFAULT 0, ban_until REAL, ban_reason TEXT,
 totp_secret TEXT, totp_last_step INTEGER NOT NULL DEFAULT -1,
 last_transfer_at REAL, last_reset_at REAL,
 moderation_status TEXT NOT NULL DEFAULT 'clear', moderation_category TEXT,
 moderation_policy_version INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS sole_owner ON users(role) WHERE role='owner';
CREATE TABLE IF NOT EXISTS sessions (
 id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
 user_id INTEGER NOT NULL REFERENCES users(id), created_at REAL NOT NULL,
 renewed_at REAL NOT NULL, lease_until REAL NOT NULL, absolute_until REAL NOT NULL,
 revoked INTEGER NOT NULL DEFAULT 0, snapshot TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS refresh_sessions (
 id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
 user_id INTEGER NOT NULL REFERENCES users(id), created_at REAL NOT NULL,
 expires_at REAL NOT NULL, used_at REAL, revoked INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_session ON sessions(user_id) WHERE revoked=0;
CREATE TABLE IF NOT EXISTS recovery_codes (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 code_hash TEXT NOT NULL UNIQUE, used_at REAL
);
CREATE TABLE IF NOT EXISTS reset_credentials (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 token_hash TEXT NOT NULL UNIQUE, expires_at REAL NOT NULL, used_at REAL
);
CREATE TABLE IF NOT EXISTS devices (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 device_hash TEXT NOT NULL, created_at REAL NOT NULL, removed_at REAL
);
CREATE TABLE IF NOT EXISTS transfers (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 device_hash TEXT NOT NULL, reason TEXT NOT NULL, created_at REAL NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', resolved_at REAL, resolved_by INTEGER REFERENCES users(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS pending_transfer ON transfers(user_id) WHERE status='pending';
CREATE TABLE IF NOT EXISTS profiles (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 name TEXT NOT NULL, config TEXT NOT NULL, created_at REAL NOT NULL,
 UNIQUE(user_id,name)
);
CREATE TABLE IF NOT EXISTS content (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
 body TEXT NOT NULL, channel TEXT NOT NULL, tier TEXT, version INTEGER NOT NULL,
 created_at REAL NOT NULL, author_id INTEGER NOT NULL REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS feedback (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 message TEXT NOT NULL, diagnostics TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id),
 action TEXT NOT NULL, target_type TEXT NOT NULL, target_id INTEGER,
 details TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
 id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id),
 kind TEXT NOT NULL, message TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reactions (
 content_id INTEGER NOT NULL REFERENCES content(id), user_id INTEGER NOT NULL REFERENCES users(id),
 reaction TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(content_id, user_id)
);
CREATE TABLE IF NOT EXISTS poll_votes (
 content_id INTEGER NOT NULL REFERENCES content(id), user_id INTEGER NOT NULL REFERENCES users(id),
 option INTEGER NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(content_id, user_id)
);
CREATE TABLE IF NOT EXISTS feedback_replies (
 feedback_id INTEGER PRIMARY KEY REFERENCES feedback(id), message TEXT NOT NULL,
 author_id INTEGER NOT NULL REFERENCES users(id), created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO settings VALUES ('transfer_cooldown_hours', '168');
INSERT OR IGNORE INTO settings VALUES ('reset_cooldown_hours', '24');
PRAGMA user_version=3;
INSERT OR IGNORE INTO settings VALUES ('maintenance', '{"enabled": false, "message": ""}');
