# Public Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Sacred Tweaks into a loadout-first, public, manually licensed Windows companion with reliable concurrent macro controls.

**Architecture:** Keep the Python desktop bridge, Windows input adapter, backend, and webview. Replace the singleton macro runtime with a coordinator of independent validated macro instances, and keep loadout application transactional. Retain existing settings and restore pages in the normal app. Manually issued monthly/lifetime licenses use the existing redemption backend, while the tier gates are removed in a dedicated backend migration.

**Tech Stack:** Python 3.12, pywebview, Windows native input APIs, SQLite/Postgres, vanilla JavaScript and CSS, unittest.

**Spec:** Decisions in this conversation, 2026-10-18; prior overlay constraints in `docs/STANDALONE-OVERLAY.md`.

**Source status:** The desktop engine, UI, owner-issued Sacred access, loadouts, and overlay controls are implemented. Python and source checks pass. Windows packaging, WebView2 visual smoke, and Fortnite input acceptance remain release gates.

## Global Constraints

- Windows 11 native functionality must be validated on Windows; Linux tests cannot prove Fortnite input acceptance.
- Never inject into Fortnite, bypass anti-cheat, or claim that macros are approved or ban-safe.
- Stop and release all synthetic input on focus loss, authorization loss, sign out, emergency stop, and loadout changes.
- A loadout includes macro configs, binds, and appearance; performance and Windows settings stay outside it.
- Warning appears on first Macros tab open per account on this Windows profile, with a persistent way to reread it.
- Monthly access starts on license redemption; license issuance remains a manual owner action.

## Review Focus

- Same output key held by two concurrent macros: reference count ownership; one stop must not release the other's input.
- Activation key is another macro's output: injected events must never trigger macros.
- Config change while active: stop target and release its inputs without corrupting other macro state.
- Loadout validation failure: keep old live setup and show an actionable error.
- Warning state on reinstall/account switch: acknowledgment keyed to account in protected local app data; a new PC asks again.

---

### Task 1: Macro engine and regression audit

**Files:** `desktop/macros.py`, `tests/test_native_macros.py`, `tests/test_extended_macros.py`, `tests/test_multi_macros.py`.

**Interfaces:** `MacroCoordinator.configure(kind, config)`, `enable(kind, enabled, now)`, `input(key, down, now, foreground, injected=False)`, `tick(now, foreground)`, `stop(reason)`, `status()`, `activation_keys()`. Preserve legacy `MacroEngine` behavior for existing tests until bridge migration.

- [ ] Write failing tests for two enabled macros, trigger conflicts, focus loss, and shared held input ownership; run `python -m unittest tests.test_multi_macros -v` and confirm failures.
- [ ] Implement coordinator with independent per-kind state, per-output ownership and serial conflict handling; test each existing macro sequence and cancellation path.
- [ ] Add `double_edit` and `gun_pullout` configurations with validation, timing and deterministic sequence tests; run macro tests.
- [ ] Commit engine changes.

### Task 2: Bridge and app macro controls

**Files:** `desktop/native.py`, `web/app.js`, `web/app.css`, `tests/test_native_tools.py`, `tests/ui-smoke.cjs`.

**Interfaces:** `macro_status` returns `macros: {kind: {config,enabled,active,reason}}` and `editing_conflicts`; `macro_configure` and `macro_enable` accept `kind`; `macro_preferences` edits conflict policy.

- [ ] Write failing bridge tests for per-kind configuration and enable, customizable toggle bindings, and newest-edit-wins policy; run focused tests.
- [ ] Migrate bridge to coordinator and persist per-account macro settings; run focused tests.
- [ ] Build Macro Studio catalog and Misc conflict settings, once-only warning on tab entry, and multi-enabled status; run UI smoke tests.
- [ ] Commit bridge and UI changes.

### Task 3: Loadouts and live controls

**Files:** `desktop/native.py`, `desktop/desktop_overlay.py`, `web/app.js`, `web/overlay.js`, `web/app.css`, `web/overlay.css`, `tests/test_desktop_overlay.py`, `tests/ui-smoke.cjs`.

**Interfaces:** `loadout_list`, `loadout_save`, `loadout_preview`, `loadout_apply`, `loadout_delete`; preview validates all macro configs and appearance, apply stops all macros, releases inputs, and atomically installs settings; macros start disabled until explicitly enabled.

- [ ] Write failing tests for preview and apply, malformed loadouts, focus loss and emergency stop; run focused tests.
- [ ] Add local loadout storage with account isolation; existing saved profiles remain available to load and save into a loadout; test.
- [ ] Make Home loadout-first and live controls accessible in app and wide overlay; retain deep tools in main app; run smoke tests.
- [ ] Commit loadout changes.

### Task 4: Public manual licenses and account UX

**Files:** `backend/*` (existing auth/license endpoints), `desktop/*` session adapter, `web/app.js`, `web/manager.js`, relevant auth/integration tests.

**Interfaces:** monthly or lifetime entitlements issued by owner, bound on redemption; remove customer-facing tiers and tier permissions while preserving historical license migration. Acknowledgment is per account and warning version.

- [ ] Write failing backend tests for monthly/lifetime redemption, migration, warning acknowledgment and suspended sessions; run focused tests.
- [ ] Migrate licensing and manager controls, keep authorization checks server-side and recovery paths intact; run integration tests.
- [ ] Update account, registration, and manager copy; run UI smoke tests.
- [ ] Commit entitlement migration.

### Task 5: Full verification and Windows acceptance

**Files:** `docs/WINDOWS-ACCEPTANCE.md`, `docs/MEMBER-GUIDE.md`, `docs/OWNER-GUIDE.md`, `build-windows.ps1` only if necessary.

- [ ] Run `python -m unittest discover -s tests -q`; expected zero errors and failures.
- [ ] Run JavaScript smoke tests and packaging gate in Windows environment; document unavailable platform checks honestly.
- [ ] Test each macro in Fortnite borderless/windowed mode manually, including edited bind conflicts, focus loss, fast toggles and emergency stop, before a public release claim.
- [ ] Update docs, audit diff, commit final documentation.
