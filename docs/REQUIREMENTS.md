# Requirements and release status

Status on 2026-10-15: source implementation ready for Windows acceptance. This is not a claim that the full release specification has been delivered: executable packages, live hosting and actual Windows/game validation remain outstanding.

| Specification area | Implemented and checked here | Remaining validation or limited scope |
|---|---|---|
| 1. Architecture | Separate member/Manager launchers, real HTTP/SQLite backend, server-enforced owner role, no privileged client secrets; local HTTP integration tested | Windows/WebView2 execution, hosted TLS deployment and signed distribution |
| 2. Visual design | Black/violet UI, glass panels, particles, perspective logo animation, bounded cursor parallax, toggles, menus, responsive layouts, loading/empty/error/access states, saved intensity/reduced-motion/lightweight preferences | Browser appearance inspected; actual Windows CPU/GPU cost and display scaling unmeasured |
| 3. Accounts/licenses | Atomic single redemption, server-time start, timed/permanent keys, username/password, one-time recovery display/export, device registration; concurrent claims tested | Actual Windows save dialog/clipboard and DPAPI require Windows acceptance |
| 4. Protection/recovery | One installation ID and active session; owner transfers, cooldowns, abuse limits, conflict alerts; scrypt passwords, hashed tokens/codes, expiring reset credentials, owner TOTP and recovery MFA | Installation ID is not a tamper-proof hardware identity; reinstall/profile loss may require owner transfer. Executable modification cannot be made impossible |
| 5. Sessions | 10-second heartbeat, maximum 25-second local authorization window, input shutdown on loss, fresh login to reconnect, no automatic macro resume, next-login permissions | Real network/Windows lifecycle timing must be measured; writes already authorized and begun may finish |
| 6. Tiers/overrides | Exact Core/Plus/Pro/Elite matrix, allow/deny/inherit, enforced values checked server/native, readable lock labels and blurred inert controls; exact lock message | Browser keyboard lock check and boundary tests passed; real packaged shortcut testing pending |
| 7. Welcome/account menu | Every-login welcome, bronze/silver/diamond/gold gradients, tier/per-license welcome text/effects/badge, top-right user dropdown, hidden duration when closed, outside-click close | Welcome presentations share brand composition with tier-specific colors; real animation smoothness not certified |
| 8. Macros/profiles | Single Edit tap/hold cycle, Drag auto/manual confirmation, customizable binds/timing/presets, conflict detection, injected-event ignore, foreground/watchdog release, emergency stop, explicit enable; Elite profile CRUD | State machine and fake-input boundaries tested. Real SendInput, hooks, Fortnite foreground matching and game acceptance remain unverified |
| 9. Performance/settings | CPU/GPU/RAM/OS/display discovery code, target FPS choices, maximum-FPS preset, balanced/potato, advanced allowlisted individual controls, versioned owner presets, explicit preview and selective backup/restore, Windows Settings shortcuts | Compatibility checks validate recognized keys already present in the installed config, not the game build number. No certified installed-version manifest is implemented. Owner preset editor selects a supported base preset and FPS. Actual hardware and installed game behavior require Windows acceptance |
| 10. Filter Keys/measurements | Supported Filter Keys API wrapper, presets/test area/backup restore; named before/after observations; actual CPU counter deltas and RAM readings where available; explicit missing metrics | FPS/frame time entered from external observations; GPU utilization and input latency unavailable. CPU/RAM are system-wide. Real Filter Keys execution unverified |
| 11. Manager | User search/details/rename, single/bulk keys, status/extension/replacement, overrides/enforcement, temporary/permanent bans/reasons, session termination, resets/transfers, recovery assistance, welcome preview, versioned presets/notices/releases, stable/beta filter, feedback with opt-in basic diagnostics, audit | Release updates use owner-published HTTPS links and manual package replacement, not an automatic updater. Diagnostics are basic structured hardware data, not arbitrary file attachments |
| 12. Verification/delivery | 83 automated Python tests, browser scenarios for all tiers/Manager, screenshot inspection, source/schema/config/build/deploy/owner docs | Both packaged Windows executables/installers are not produced here; public hosting not deployed; signing not performed; Windows acceptance checklist remains open |

## Release gates

- [x] Backend and desktop source, schema v1 and configuration templates.
- [x] API authorization, redemption, recovery, device and session behavior tests.
- [x] Native state-machine/settings tests and local HTTP integration.
- [x] UI fixture tests, primary-screen visual inspection and review fixes.
- [x] Build script, Windows CI workflow, deployment instructions and guides.
- [ ] Build both portable Windows bundles with their bundled dependencies.
- [ ] Run both bundles as a standard Windows user and on a second PC.
- [ ] Complete `WINDOWS-ACCEPTANCE.md`, including installed-version setting support.
- [ ] Deploy and verify the HTTPS backend with persistent storage and restored backups.
- [ ] Measure idle/minimized/game-running resource cost on target Windows hardware.
- [ ] Sign release binaries if a certificate is available, then distribute final checksums.

The initial schema is versioned with SQLite `user_version=1`; fresh creation and repeat startup are supported. There is no historical pre-v1 database migration because this is the first schema release. Future incompatible schemas need explicit migration code.
