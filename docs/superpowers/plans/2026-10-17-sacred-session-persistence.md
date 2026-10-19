# Sacred Remembered Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in secure sign-in persistence using rotating, revocable refresh credentials.

**Architecture:** Preserve the existing short access lease and watchdog. Add a hashed refresh-token family on the server, rotate on resume, revoke on logout/replay, and protect the client credential with Windows DPAPI through an injectable vault.

**Tech Stack:** Python 3.12+, SQLite and PostgreSQL schemas, stdlib cryptography APIs (Windows DPAPI), unittest, hosted HTTP API.

**Spec:** `docs/superpowers/specs/2026-10-17-overlay-account-quality-design.md`

## Global Constraints

- Store no access token or refresh secret as plaintext on disk, in frontend JavaScript, or in logs.
- Keep authorization lease and native watchdog behavior unchanged.
- Remember-session is opt-in; DPAPI failure falls back to ordinary sign-in with a clear message, never plaintext.
- Refresh credentials are hashed server-side, expiring, rotating, replay-detecting, and revocable.

## Review Focus

- Refresh replay after rotation revokes that credential family; test the previous token cannot mint a session.
- Session expiry, user ban, license suspension, and revocation are rechecked before issuing access; test each condition.
- Sign-out and password recovery invalidate remembered credentials; test both endpoints.
- Local DPAPI corruption or profile change falls back to sign-in and deletes/unlocks no credential; test through a fake protector.
- Simultaneous resume requests cannot mint two valid sessions; test concurrent service calls.

---

### Task 1: Server refresh credential contract and schema

**Files:**
- Modify: `server/schema.sql`
- Modify: `server/schema-postgres.sql`
- Modify: `server/service.py`
- Modify: `docs/CONTRACT.md`
- Test: `tests/test_server.py`
- Test: `tests/test_postgres.py`

**Interfaces:**
- Produces: `POST /v1/auth/refresh` with `{refresh_token}` returning a new access session and rotated `refresh_token`; `POST /v1/auth/logout` revokes active access and refresh family; no refresh secret is returned by admin/read APIs.

- [ ] **Step 1: Add failing service tests** named `test_refresh_rotates_and_replay_revokes_family`, `test_refresh_checks_user_and_license_access`, `test_logout_revokes_refresh_family`, and `test_concurrent_refresh_has_one_winner`.
- [ ] **Step 2: Run** `python -m unittest tests.test_server tests.test_postgres -v`; confirm missing endpoint/schema failures.
- [ ] **Step 3: Add a versioned refresh-session table** with token hash, family/user IDs, created/expiry/used/revoked timestamps; implement atomic rotation, replay revocation, and existing `_check_access` validation. Apply additive PostgreSQL migration through the current hosted schema path.
- [ ] **Step 4: Run** `python -m unittest tests.test_server tests.test_postgres -v`; expected: rotation, replay, expiry, revocation, and concurrent-use tests pass.
- [ ] **Step 5: Commit** as `feat: add rotating remembered sessions`.

### Task 2: DPAPI vault and bridge resume flow

**Files:**
- Create: `desktop/session_vault.py`
- Modify: `desktop/bridge.py`
- Modify: `desktop/launcher.py`
- Modify: `desktop/storage.py` only if sharing its DPAPI helper reduces duplication without changing device identity behavior
- Test: `tests/test_session_vault.py` (new)
- Test: `tests/test_bridge.py`

**Interfaces:**
- Produces: `SessionVault.save(refresh_token: str) -> None`, `SessionVault.load() -> str | None`, `SessionVault.clear() -> None`; bridge resume invokes `/v1/auth/refresh` and stores the rotated token only when Remember me was selected.

- [ ] **Step 1: Add failing fake-protector tests** named `test_vault_persists_only_protected_bytes`, `test_corrupt_vault_fails_closed`, and bridge tests `test_remembered_session_resumes_and_rotates` and `test_logout_clears_remembered_session`.
- [ ] **Step 2: Run** `python -m unittest tests.test_session_vault tests.test_bridge -v`; confirm tests fail.
- [ ] **Step 3: Implement the vault** with atomic file replacement, Windows DPAPI CurrentUser protection, injectable fake protector for CI, and startup resume before rendering the signed-in workspace. Never surface secrets to JavaScript.
- [ ] **Step 4: Run** `python -m unittest tests.test_session_vault tests.test_bridge -v`; expected: protected storage and resume lifecycle tests pass.
- [ ] **Step 5: Commit** as `feat: securely resume remembered desktop sessions`.

### Task 3: Remember-me UI and end-to-end verification

**Files:**
- Modify: `web/app.js`
- Modify: `web/index.html` if shared sign-in markup requires it
- Modify: `tests/ui-smoke.cjs`
- Modify: `docs/MEMBER-GUIDE.md`
- Test: `tests/test_integration.py`

**Interfaces:**
- Consumes: bridge bootstrap status `remembered_session` and existing opaque API result format.
- Produces: unchecked-by-default “Remember me on this PC” checkbox with short DPAPI explanation; clear resume error state and normal sign-in fallback.

- [ ] **Step 1: Add failing UI/integration tests** named `test_remember_me_is_opt_in_and_explained` and `test_refresh_survives_desktop_restart_without_exposing_secret`.
- [ ] **Step 2: Run** `node tests/ui-smoke.cjs` and `python -m unittest tests.test_integration -v`; confirm new assertions fail.
- [ ] **Step 3: Wire remember-me selection** into bridge credential storage and add concise user guidance for sign-out, expiry, profile migration, and DPAPI failure.
- [ ] **Step 4: Run** `node tests/ui-smoke.cjs && python -m unittest tests.test_integration -v`; expected: UI and API lifecycle pass without tokens in page state/logs.
- [ ] **Step 5: Commit** as `feat: add opt-in remember me experience`.
