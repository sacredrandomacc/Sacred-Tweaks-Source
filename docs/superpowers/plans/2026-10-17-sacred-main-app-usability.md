# Sacred Main App Usability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve app appearance, contextual instructions, and safe quality-of-life tools without removing existing features.

**Architecture:** Extend the current local HTML/CSS/JS settings and helper patterns. Store appearance in the existing local settings mechanism, use existing profile APIs for import/export, and generate diagnostics only from an allowlisted local snapshot.

**Tech Stack:** Python 3.12+, pywebview bridge, HTML/CSS/JavaScript, JSON, unittest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-17-overlay-account-quality-design.md`

## Global Constraints

- Preserve Performance, Measurements, Backups & Restore, macro studio, and profile views in the main app.
- Replace animation intensity with a boolean On/Off setting; keep Windows reduced-motion behavior.
- Default palette is charcoal (#111318, #191D25), warm white (#F2F0EA), cool-gray supporting text, and violet (#9A82F7); allow adjustment and reset.
- Feature summaries show by default, with detailed steps accessible by pointer and keyboard.
- No silent telemetry; diagnostics are explicitly selected by the user and exclude credentials.
- Profile import validates structure and limits, accepts no executable content, and never enables a macro as a side effect.

## Review Focus

- Old saved settings containing `intensity` migrate to boolean animation without breaking launch; test legacy theme load.
- User-selected colors retain accessible text/focus contrast and can be reset; test contrast boundaries and invalid values.
- Imported profile JSON with oversized, unknown, nested executable-like, or unsupported fields is rejected without partial save; test limits and atomicity.
- Diagnostic export never contains auth token, refresh token, password, recovery code, or arbitrary file contents; test sentinel-secret filtering.
- Help controls work with keyboard and reduced motion; test expand/collapse accessibility and saved behavior.

---

### Task 1: Replace animation intensity with On/Off and palette controls

**Files:**
- Modify: `desktop/native.py`
- Modify: `desktop/bridge.py`
- Modify: `web/app.js`
- Modify: `web/styles.css`
- Modify: `tests/test_native_tools.py`
- Modify: `tests/ui-smoke.cjs`

**Interfaces:**
- Produces: theme payload `{animations_enabled: bool, lightweight: bool, reduced_motion: bool, accent: "#RRGGBB", surface: "#RRGGBB"}`; legacy `intensity` settings migrate to `animations_enabled = intensity > 0`.

- [ ] **Step 1: Add failing tests** named `test_legacy_theme_intensity_migrates_to_boolean` and UI `test_appearance_uses_toggle_palette_and_reset`.
- [ ] **Step 2: Run** `python -m unittest tests.test_native_tools -v && node tests/ui-smoke.cjs`; confirm new assertions fail.
- [ ] **Step 3: Add theme validation/migration and replace the range slider** with an On/Off switch; add adjustable accent/surface colors and recommended reset values.
- [ ] **Step 4: Run** the same commands; expected: migrated preferences and UI controls pass.
- [ ] **Step 5: Commit** as `feat: simplify motion and expand app palette`.

### Task 2: Shared feature instructions

**Files:**
- Create: `web/help.js`
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/styles.css`
- Modify: `tests/ui-smoke.cjs`

**Interfaces:**
- Produces: `featureHelp(featureId) -> {summary: string, details: string}` and accessible `<details>` blocks with summary visible and complete instructions expandable.

- [ ] **Step 1: Add failing UI tests** named `test_feature_summaries_are_visible` and `test_feature_details_expand_with_keyboard` for performance, macros, Filter Keys, profiles, measurements, and restore.
- [ ] **Step 2: Run** `node tests/ui-smoke.cjs`; confirm help blocks are absent.
- [ ] **Step 3: Add shared help content** covering prerequisites, steps, risks, and restore/recovery for each feature; insert only the relevant help component per view.
- [ ] **Step 4: Run** `node tests/ui-smoke.cjs`; expected: summary visibility, keyboard expansion, responsive layout, and no page errors.
- [ ] **Step 5: Commit** as `feat: add expandable feature instructions`.

### Task 3: Validated saved-profile import/export

**Files:**
- Create: `desktop/profile_transfer.py`
- Modify: `desktop/bridge.py`
- Modify: `web/app.js`
- Modify: `web/styles.css`
- Test: `tests/test_profile_transfer.py` (new)
- Modify: `tests/ui-smoke.cjs`

**Interfaces:**
- Produces: `validate_profile_bundle(data: bytes) -> list[dict]` and bridge actions `profile_export` / `profile_import_preview`; import commits only after explicit user confirmation through existing `POST /v1/profiles`, and does not load/enable the imported configuration.

- [ ] **Step 1: Add failing transfer tests** named `test_export_round_trip`, `test_rejects_oversize_unknown_or_invalid_profile`, and `test_import_never_enables_configuration`.
- [ ] **Step 2: Run** `python -m unittest tests.test_profile_transfer -v`; confirm missing module/action failures.
- [ ] **Step 3: Implement a bounded versioned JSON format** with an explicit maximum file size and profile count, supported macro fields only, safe filenames, and all-or-nothing validation.
- [ ] **Step 4: Run** `python -m unittest tests.test_profile_transfer -v`; expected: round-trip and rejection cases pass.
- [ ] **Step 5: Add profile page import/export actions** with preview/count and confirmation before saving; never auto-load or enable imported profiles.
- [ ] **Step 6: Run** `node tests/ui-smoke.cjs`; expected: import/export controls submit safely and profile views stay responsive.
- [ ] **Step 7: Commit** as `feat: import and export validated profiles`.

### Task 4: User-initiated privacy-safe diagnostics export

**Files:**
- Modify: `desktop/bridge.py`
- Modify: `web/app.js`
- Modify: `docs/MEMBER-GUIDE.md`
- Test: `tests/test_bridge.py`
- Modify: `tests/ui-smoke.cjs`

**Interfaces:**
- Produces: `Api.export_diagnostics() -> {cancelled: bool, saved?: bool}` that writes an allowlisted summary of startup/app state and non-sensitive error details only via a user-selected save dialog.

- [ ] **Step 1: Add failing tests** named `test_diagnostics_allowlist_excludes_credentials_and_user_content` and UI `test_diagnostics_export_requires_user_action`.
- [ ] **Step 2: Run** `python -m unittest tests.test_bridge -v && node tests/ui-smoke.cjs`; confirm missing action/assertion failures.
- [ ] **Step 3: Implement export allowlist and save dialog**; explicitly exclude tokens, passwords, recovery codes, refresh credentials, request bodies, and arbitrary file contents.
- [ ] **Step 4: Run** the same commands; expected: sentinel secrets are absent and export is user-initiated.
- [ ] **Step 5: Commit** as `feat: add privacy-safe diagnostics export`.

### Task 5: Full app regression and Windows acceptance

**Files:**
- Modify: `docs/WINDOWS-ACCEPTANCE.md`
- Modify: `docs/MEMBER-GUIDE.md`
- Test: `tests/ui-smoke.cjs`
- Test: all relevant Python tests

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: a verified acceptance record listing what CI covered and what requires Windows/WebView2 testing.

- [ ] **Step 1: Run** `python -m unittest discover -s tests -v` and `node tests/ui-smoke.cjs`; expected: all automated tests pass.
- [ ] **Step 2: Check every main navigation view** for preserved Performance, Measurements, Backups & Restore, macro studio, profiles, and appearance controls using the smoke test.
- [ ] **Step 3: Record Windows-only checks** for display scaling, overlay focus, app restart, DPAPI, and exported save dialogs without marking unperformed tests as passed.
- [ ] **Step 4: Commit** as `docs: record Sacred app acceptance checks`.
