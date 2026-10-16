# Backend implementation and verification

Implemented candidate version: **0.1.0**. Python 3.12 standard library only. The backend has not been deployed to a live host in this environment.

## Delivered

- `server/service.py`: the complete `/v1` service contract, account registration/login/recovery, license generation and management, owner-only administrative actions, session renewal, permissions/enforced values, devices/transfers, profiles, feedback, and published content/version history.
- `server/schema.sql`: schema migration 1, identified by SQLite `PRAGMA user_version`. Newer unknown versions are rejected. SQLite foreign keys, unique constraints, and immediate write transactions protect license claims, one-active-session enforcement, recovery credential consumption, and profile edits.
- `server/http.py`: real HTTP adapter with eight concurrent request slots, a 64 KiB body limit, request timeouts, duplicate JSON/framing rejection, no-store responses, and no request/credential logging. The service defaults to loopback and requires a TLS reverse proxy for deployment.
- `server/__main__.py`: server, interactive owner bootstrap, and server-operator owner-device recovery commands.
- `tests/test_server.py` and `tests/test_server_http.py`: 26 backend tests, including real socket-level requests.

## Commands and observed results

Executed from the source root on 2026-10-15:

```bash
python -m unittest discover -s tests -p 'test_server*.py' -v
# Ran 26 tests; OK.

python -m unittest discover -s tests -v
# Ran 74 tests; OK at the time of this component report.

python -m server --help
# Exit 0; CLI options match deployment commands below.
```

The backend tests exercise eight concurrent redemption attempts (one winner), six concurrent recovery attempts (one winner), rollback after failed account creation or invalid license changes, tier inheritance and per-license overrides, permission snapshots until next login, enforced settings, admin authorization, MFA and TOTP replay rejection, member recovery replay, reset expiration/cooldowns, renewal expiration, bans, suspension/revocation, timed/permanent expiration, one-PC/session policy, transfer approval/revocation, profile ownership/edits, license replacement/extension, content gating/history, secret nondisclosure, rate limits, unsafe URLs, and HTTP parser abuse.

Tests use constructor-only `password_cost=1024` to keep the suite fast. Production `Service` defaults to **scrypt N=131072, r=8, p=1**, random 16-byte salts and a 64-byte derived key. No CLI/environment option lowers that cost. The deployment/integration owner should also run a production-cost smoke test on the actual host to confirm its memory and latency budget.

## Exact deployment and setup commands

```bash
# Run once interactively on the server. Password is prompted without echo.
python -m server --db /data/sacred.db --bootstrap-owner OWNER_USERNAME

# Direct Caddy container at the fixed IP configured by compose.yaml:
python -m server --host 0.0.0.0 --port 8765 --db /data/sacred.db --trusted-proxy 172.30.90.3/32

# Local development only:
python -m server --host 127.0.0.1 --port 8765 --db data/sacred.db

# Server operator recovery after losing the owner's registered installation:
python -m server --db /data/sacred.db --reset-owner-device
```

Owner bootstrap prints the authenticator seed, an `otpauth://` URI, and ten recovery codes once. Store them privately. Subsequent bootstrap attempts fail. Owner login requires the password plus an unused TOTP value (30-second steps, one-step tolerance) or an unused recovery code. A TOTP step successfully used for login cannot be replayed. Owner device recovery clears only the registration and sessions; password and MFA are still required. Its interactive confirmation is `RESET OWNER DEVICE`.

`--trusted-proxy` is repeatable. Forwarded addresses are ignored unless the network peer is explicitly trusted; the rightmost untrusted forwarded address is used. The supplied topology assumes clients connect directly to Caddy, with no CDN or extra upstream proxy. Without a trusted-proxy argument, requests through Caddy share its IP rate budget. Do not trust `0.0.0.0/0`, an entire public network, or a client-controlled proxy address.

## Security and operational behavior

Session/license/reset/recovery credentials are high-entropy random values stored only as SHA-256 hashes; full license keys, session tokens, reset credentials and recovery codes are excluded from administrative responses and audit records. Device registration stores a hash of the DPAPI-protected random installation identity. It does not fingerprint hardware or use IP addresses as a ban criterion.

The TOTP seed must remain recoverable for verification. It is stored only in the server database, protected by mode 0600; newly created data directories use mode 0700 and the CLI sets umask 077. The container volume and backups must be access-controlled. There is no claim that this is application-layer encryption or that it protects against a compromised host/operator. SQLite backup handling must preserve those restrictions, including journal/WAL files.

Heartbeats run every ten seconds and renew a 25-second authorization lease. An expired lease cannot be revived; the user signs in again. Sessions have a twelve-hour absolute lifetime. Permission/tier/welcome/override snapshots remain fixed until login, while account bans, license suspension/revocation and server-time expiry are checked on every authorized API call. Revocation is bounded by client polling/lease expiry, not instantaneous. Ordinary permission updates never silently mutate an active snapshot.

A second active session is rejected and creates an alert. Device mismatches also create alerts. Three transfer requests within thirty days create a repeated-device-change alert. Default transfer cooldown is 168 hours; assisted reset cooldown is 24 hours. Owners can change both. Issuing an assisted reset credential immediately revokes existing sessions; the credential expires after fifteen minutes and is single use. Replacing recovery codes invalidates the old set. A password reset never changes device registration or license dates.

Key creation does not start the timer. Successful redemption atomically starts its duration with server time. A license replacement preserves the account, redemption timestamp, expiration and policy settings. A replacement of an already-redeemed license remains redeemed and cannot create another account. Extension adds days to the existing expiration, including when it has already elapsed; it does not silently restart from today's date.

Content URL/href fields require HTTPS with no embedded credentials. Native-enforceable policy values use a supported-key/type/range allowlist, including advanced Fortnite settings. Inapplicable feature settings are rejected instead of silently ignored. Native tools must still validate complete configurations, permissions and policy values at execution time.

## Additive contract details

- Session metadata includes `overrides:{feature:boolean|null}` so the renderer can distinguish “Locked by owner” from a tier lock.
- `POST /v1/profiles` accepts optional `id` to update an existing profile belonging to the caller atomically. Omit `id` to create; copying is creation with a different name.
- License/account denial codes include `license_inactive`, `license_expired`, `banned`, `session_expired`, and `unauthorized`. The bridge must stop tools on these authorization failures.
- Content publishing appends versions; member content returns the newest version per kind/name/channel/tier, and admin content includes history. Beta releases/presets require the snapshot beta permission. Owner presets require the owner_presets permission.

## Remaining deployment limits

This is a single-process, small-private-group service using a persistent local SQLite volume. It is not a distributed service. In-memory rate counters reset when the process restarts; upstream connection limits and routine host monitoring are still needed. List responses intentionally bound record counts (users/transfers 500, audit/feedback 1000, license/content 2000, per-user session/device history 100). The underlying history remains in SQLite, but large-history pagination/export is not implemented in this candidate.

Diagnostic attachments are JSON objects up to 16 KiB, not arbitrary binary uploads. Automated email/SMS notifications, hardware/person identity proofs, and a third-party authentication provider are not dependencies. Owner TOTP enrollment is an operator CLI flow, not a hosted QR enrollment page.

Live HTTPS, production-host backup/restore drills, public-load/security testing, and Windows application installation require the deployment/Windows environment. No live hosting, code signing or Windows package execution was performed by this backend component task.
