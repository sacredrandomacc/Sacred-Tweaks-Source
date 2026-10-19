# Sacred Username Moderation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce username policy on registration and rename with a clear, audited owner-review path.

**Architecture:** Add a versioned server moderation policy and per-user review state. Flagged registration creates a non-authorized account/review item and never issues a usable session. Owner actions use existing Manager admin service patterns and audit records.

**Tech Stack:** Python 3.12+, SQLite/PostgreSQL schema, hosted HTTP service, existing Manager HTML/JS/CSS, unittest and Playwright smoke coverage.

**Spec:** `docs/superpowers/specs/2026-10-17-overlay-account-quality-design.md`

## Global Constraints

- Enforce normalized username policy during registration and every supported rename.
- Flagged accounts receive no usable session until review; user messages do not reveal the prohibited lexicon.
- Moderation checks are imperfect and must include human review; never claim complete hate-speech detection.
- Owner review actions and exceptions are authorized and audited.
- Do not rescan existing users into automatic denial; future rescans create review records only.

## Review Focus

- Unicode/case/obfuscation variants cannot trivially bypass normalization; test representative forms and benign lookalikes.
- A flagged registration must not redeem an unusable license silently; test transaction state and clear pending instructions.
- Owner-approved exception requires documented reason and audit row; test missing/short reason rejection.
- Rejected/pending users cannot authenticate or renew sessions; test login and heartbeat.
- Rename collisions and attempted names flagged by policy leave the old username unchanged; test atomicity.

---

### Task 1: Versioned username policy and registration state

**Files:**
- Create: `server/username_moderation.py`
- Modify: `server/schema.sql`
- Modify: `server/schema-postgres.sql`
- Modify: `server/service.py`
- Test: `tests/test_username_moderation.py` (new)
- Test: `tests/test_server.py`

**Interfaces:**
- Produces: `moderate_username(value: str) -> ModerationResult` with normalized form, policy version, status `clear|pending`, and non-lexical rule category; registration returns ordinary session only for `clear`, otherwise `{moderation_status: "pending", review_message: ...}` without a token.

- [ ] **Step 1: Add failing tests** named `test_policy_normalizes_case_unicode_and_common_obfuscation`, `test_benign_names_remain_clear`, and `test_flagged_registration_creates_pending_review_without_session`.
- [ ] **Step 2: Run** `python -m unittest tests.test_username_moderation tests.test_server -v`; confirm missing policy/state failures.
- [ ] **Step 3: Implement a versioned, reviewable rule set** with Unicode NFKC and casefold normalization, conservative separator/leet folding, fixed public pending message, and additive moderation columns/table. Keep the actual lexicon out of API errors and public logs.
- [ ] **Step 4: Run** the same unittest command; expected: normalized policy and registration-state assertions pass.
- [ ] **Step 5: Commit** as `feat: moderate usernames during registration`.

### Task 2: Owner review queue and rename enforcement

**Files:**
- Modify: `server/service.py`
- Modify: `web/manager.js`
- Modify: `web/app.js` only if shared owner navigation or UI helpers are required
- Modify: `web/styles.css`
- Modify: `tests/ui-smoke.cjs`
- Test: `tests/test_server.py`

**Interfaces:**
- Produces: owner-only `GET /v1/admin/moderation` and `POST /v1/admin/moderation/{user_id}` with `{action: "approve"|"rename"|"reject", username?, reason?}`; all actions return sanitized status and write an audit entry.

- [ ] **Step 1: Add failing backend tests** named `test_moderation_queue_is_owner_only`, `test_rename_rechecks_policy_atomically`, `test_approval_exception_requires_audited_reason`, and `test_pending_and_rejected_user_cannot_login_or_heartbeat`.
- [ ] **Step 2: Run** `python -m unittest tests.test_server -v`; confirm route and access tests fail.
- [ ] **Step 3: Implement owner-only queue/actions** and apply moderation to existing admin rename. Only compliant rename or a reasoned exception can clear the hold; owner actions record policy version/category and audit metadata.
- [ ] **Step 4: Run** `python -m unittest tests.test_server -v`; expected: authorization, atomicity, and audit tests pass.
- [ ] **Step 5: Add Manager review UI** with username, submitted time, category, and approve/rename/reject controls; include confirmation for reject/exception.
- [ ] **Step 6: Run** `node tests/ui-smoke.cjs`; expected: review queue renders, actions submit correct payloads, no frontend errors.
- [ ] **Step 7: Commit** as `feat: add owner username review queue`.

### Task 3: Applicant messaging and recovery guide

**Files:**
- Modify: `web/app.js`
- Modify: `web/index.html` if registration response view requires shared auth markup
- Modify: `docs/MEMBER-GUIDE.md`
- Modify: `docs/OWNER-GUIDE.md`
- Modify: `tests/ui-smoke.cjs`

**Interfaces:**
- Consumes: registration result `moderation_status` and sanitized `review_message` from Task 1.
- Produces: clear pending/rejected auth states with contact/review guidance and no session-only pages rendered.

- [ ] **Step 1: Add failing UI assertions** named `test_flagged_registration_explains_owner_review` and `test_pending_review_does_not_enter_workspace`.
- [ ] **Step 2: Run** `node tests/ui-smoke.cjs`; confirm pending state is not handled.
- [ ] **Step 3: Implement the applicant state** and update concise owner/member guidance for review timing, renames, exceptions, and appeal/contact path.
- [ ] **Step 4: Run** `node tests/ui-smoke.cjs`; expected: pending account cannot enter workspace and sees actionable explanation.
- [ ] **Step 5: Commit** as `feat: explain username review and recovery`.
