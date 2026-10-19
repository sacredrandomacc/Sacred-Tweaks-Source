# Sacred Companion Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a customizable four-page companion overlay with a safe, read-only macro profile view.

**Architecture:** Keep the existing pywebview companion window and JS bridge. Add only validated preferences and read-only profile data; keep performance, measurements, backups, and gameplay-input controls in the main app.

**Tech Stack:** Python 3.12+, pywebview/WebView2, HTML/CSS/JavaScript, unittest, Playwright UI smoke tests.

**Spec:** `docs/superpowers/specs/2026-10-17-overlay-account-quality-design.md`

## Global Constraints

- No game injection, memory reads, rendering hooks, modified Fortnite files, or anti-cheat bypasses.
- Windowed Fullscreen is the supported display mode; ordinary topmost windows cannot reliably display over exclusive fullscreen.
- The overlay may show macro profiles and summaries but must not edit bindings/timing, enable/disable macros, or send gameplay input.
- All hidden-window state must hide the full window; opening takes focus and closing restores Fortnite focus.

## Review Focus

- Profiles unavailable to a tier must not leak profile names or configs; test signed-out and permission-denied snapshots.
- Invalid/custom overlay sizes and coordinates must be clamped to usable display bounds; test minimum, maximum, and malformed values.
- Fortnite closing/restarting, Alt-Tab, DPI/scaling, and resolution changes must not strand a visible or interactive overlay; controller tests cover lifecycle and Windows acceptance documents platform checks.
- A hotkey that conflicts with a Fortnite bind is user-configurable and not swallowed while hidden; test preference update and document Windows input pass-through acceptance.
- Mouse or keyboard use while hidden must not target the overlay; test complete hide calls and verify manually on Windows.

---

### Task 1: Limit overlay navigation and add profile summary

**Files:**
- Modify: `desktop/desktop_overlay.py`
- Modify: `web/overlay.html`
- Modify: `web/overlay.js`
- Modify: `web/overlay.css`
- Test: `tests/test_desktop_overlay.py`
- Test: `tests/overlay-smoke.cjs` (new; standalone overlay fixture)

**Interfaces:**
- Consumes: `Api.request(method, path, payload)` returning `{ok, data, error}` and current private session snapshot.
- Produces: `OverlayBridge.macro_profiles() -> dict` returning `{profiles: [{id, name, kind, saved_at}]}` or a safe empty/locked state, with no macro activation API exposed.

- [ ] **Step 1: Write failing tests** named `test_macro_profiles_are_read_only_and_permission_gated` and `test_overlay_pages_exclude_main_app_only_tools`; assert the bridge exposes only names/kind/date, and pages contain Home, Macros, Windows, Appearance but no Performance, Measurements, or Backups.
- [ ] **Step 2: Run the targeted tests and confirm they fail.** Run: `python -m unittest tests.test_desktop_overlay -v` and `node tests/overlay-smoke.cjs`.
- [ ] **Step 3: Implement the safe profile summary bridge and four-page navigation.** Do not add bridge methods for macro configuration, enablement, or input.
- [ ] **Step 4: Run targeted tests and confirm they pass.** Run the same commands; expected: all assertions pass and no browser errors.
- [ ] **Step 5: Commit** as `feat: add safe macro profile view to companion`.

### Task 2: Persist and apply overlay appearance geometry

**Files:**
- Modify: `desktop/desktop_overlay.py`
- Modify: `web/overlay.js`
- Modify: `web/overlay.css`
- Test: `tests/test_desktop_overlay.py`

**Interfaces:**
- Consumes: existing `valid_preferences(values)` and `OverlayBridge.save_preferences(values)`.
- Produces: validated `size` (`compact|standard|wide`) and normalized `position` (`center|left|right`) preferences; controller positions the complete window within current game bounds.

- [ ] **Step 1: Add failing tests** named `test_preferences_validate_size_and_position` and `test_controller_places_overlay_inside_game_bounds_after_display_change`; assert invalid values reject and resized geometry is recalculated.
- [ ] **Step 2: Run** `python -m unittest tests.test_desktop_overlay -v`; confirm the new tests fail.
- [ ] **Step 3: Add size, position, and reset controls** alongside existing hotkey, opacity, accent, and reduced-motion controls; validate all persisted values and clamp geometry to the game window's client bounds.
- [ ] **Step 4: Run** `python -m unittest tests.test_desktop_overlay -v`; expected: all controller and preference tests pass.
- [ ] **Step 5: Commit** as `feat: customize companion size and position`.

### Task 3: Overlay visual and platform acceptance

**Files:**
- Modify: `docs/STANDALONE-OVERLAY.md`
- Modify: `docs/WINDOWS-ACCEPTANCE.md`
- Test: `tests/overlay-smoke.cjs`

**Interfaces:**
- Consumes: four-page overlay and preference behavior from Tasks 1–2.
- Produces: updated setup and Windows acceptance steps, including a usable Windowed Fullscreen explanation and checks for focus, Alt-Tab, scaling, resolution, and restart.

- [ ] **Step 1: Add UI assertions** for all four destinations, profile summary, account/license header, and each appearance field.
- [ ] **Step 2: Run** `node tests/overlay-smoke.cjs`; expected: every destination and preference control renders without page errors.
- [ ] **Step 3: Update overlay and Windows acceptance documentation** to list Windows-only checks without claiming they passed in Linux CI.
- [ ] **Step 4: Run** `python -m unittest tests.test_desktop_overlay -v && node tests/overlay-smoke.cjs`; expected: all checks pass.
- [ ] **Step 5: Commit** as `docs: document companion overlay acceptance`.
