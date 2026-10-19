# Verification record

Date: 2026-10-15. Environment: Linux, Python 3.12, Node 24, Chromium 133 headless through Playwright 1.62.1. Desktop source targets Windows; these results do not validate WinAPI/WebView2 execution.

## Automated checks

`python -m unittest discover -s tests -v`: **83 tests passed**.

Coverage includes concurrent license redemption and recovery use, timed/permanent licenses, next-login tier/override snapshots, ban/suspension/revocation/expiry, one active session/device, transfer/reset cooldowns, owner MFA/admin isolation, token/key/code privacy, content/profile scope, bounded HTTP parsing/rate limits, macro cancellation/focus/configuration/input release, selective backup restoration and conflicts, partial failures, and native permission/enforced-setting guards.

Bridge regressions cover canonical authentication routes (including trailing slash, empty/nonempty query and control characters), token exclusion from renderer responses, Manager member rejection, stale heartbeat and failed-request replies, offline safe actions and saved appearance. Settings-write regression checks a changed authorization snapshot during backup creation and verifies that a stalled write cannot delay emergency input release.

The real HTTP integration test runs a temporary SQLite service and the desktop bridge together: owner creates Elite invitation, member registers, configures/enables a macro through the native boundary, owner revokes the license, member access is cleared, and offline backup access remains available. Its input platform deliberately sends no Windows input.

A separate owner-bootstrap/login smoke check used the production default **scrypt N=131072, r=8, p=1** and passed (about 0.99 seconds total in this environment, including service initialization, bootstrap and login). Most functional tests deliberately use a cheaper constructor-only cost; the production CLI does not expose that override.

`node --check web/app.js` and `node --check web/manager.js`: passed.

## Browser checks

`tests/ui-smoke.cjs` serves the bundled frontend and injects an explicit test-only bridge. It does not ship in either executable. The passing scenarios cover 26 main-view visits across Core, Plus, Pro, Elite and Manager, plus login/welcome/dropdown flows, offline restore before login, blurred/inert controls and exact keyboard lock message, settings preview, Drag configuration, native stop-status update while preserving unsaved input, disconnected reauthentication, error handling, animation pause/resume, release details/publishing, and Manager account/license/generation/welcome dialogs. There were zero page JavaScript errors and no tested page-width overflow, including the 900px member layout.

Actual screenshots were inspected for member overview/performance/macros/filter/profiles/measurements/backups/appearance/account, both login forms, all four tier welcomes, user dropdown, settings preview, disconnection/error/offline restoration, all eight Manager pages, and key Manager dialogs. The inspection caught a stale connection label and guest-header alignment; these were corrected. Screenshot data is synthetic and test-only. Screenshots are not included in the source deliverable.

To reproduce browser checks in a Node-equipped checkout:

```sh
npm install --no-save playwright@1.62.1
npx playwright install chromium
node tests/ui-smoke.cjs
```

An existing compatible Chromium binary may be selected with `SACRED_CHROMIUM`; `SACRED_SCREENSHOTS` selects the output folder. The test environment used a separately extracted Chromium binary after the normal browser download failed. It is not a product dependency.

## Review and limits

Original spec and quality reviews are retained in `REVIEW-SPEC.md` and `REVIEW-QUALITY.md`, followed by implementer resolution notes. Important review findings were fixed and regression tested; a complete independent final re-review did not finish.

Not executed: Windows hooks/SendInput/Filter Keys/DPAPI, WebView2 renderer bridge startup, PowerShell/PyInstaller packaging, installer/portable bundle launches, real Fortnite settings and input, hosted HTTPS/Docker deployment, TLS renewals, hardware-specific CPU/GPU overhead, signing or antivirus reputation. No Windows executable, certified Fortnite version, FPS gain, input-latency gain, anti-ban guarantee or hosted service is claimed.

Complete `WINDOWS-ACCEPTANCE.md` before release. `REQUIREMENTS.md` distinguishes completed source from external gates and deliberately limited implementations.

## Windows build-log follow-up

The first user-supplied Windows build log ran all 83 tests and failed one watchdog test before packaging. Its activation wait was only 50 ms, equal to the worker's idle poll interval; a scheduling delay could fail setup before expiration was tested. The test now observes fake input activation with an event under a long setup lease, shortens authorization to 80 ms, then observes release without frontend calls. It still asserts input release, disabled state and no automatic resume. Production macro/watchdog behavior is unchanged. All 83 tests and 30 repeated runs of the corrected watchdog test passed locally. A Windows rerun is still required.
