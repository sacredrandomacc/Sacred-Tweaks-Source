# Required Windows release validation

These checks have not been performed in the Linux development environment. Do them before distributing the application for real use.

- [ ] Run `build-windows.ps1`; retain test and both WebView2 launch results.
- [ ] Launch both portable bundles on a second standard-user Windows 10/11 PC.
- [ ] In the companion, visit Home, Macros, Windows, and Appearance; verify Performance, Measurements, and Backups & Restore remain available in the normal app.
- [ ] Verify saved macro profile editing is permission-gated, saves names/bindings/timing, never activates a macro, and retains the full studio in the main app.
- [ ] Verify Wide is the only overlay size, old size settings migrate to Wide, and position, opacity, hotkey, accent, and reset work at 100%, 125%, and 150% scaling and after resolution changes.
- [ ] While hidden, verify mouse/keyboard input passes to Fortnite; while open, verify controls accept input and closing restores game focus.
- [ ] Test Windowed Fullscreen, Alt-Tab away/back, and Fortnite close/restart; confirm the overlay hides/reappears as documented.
- [ ] Verify default/125%/150% display scaling, resize, reduced motion, and minimized effects.
- [ ] Redeem 30-day and lifetime Sacred keys. Confirm 30-day time starts at redemption, and explicit owner locks display clearly.
- [ ] Apply a loadout while Fortnite is running; confirm preview, release of old inputs, disabled macros, and restored appearance. Confirm performance and Windows settings are unaffected.
- [ ] Enable two unrelated macros together, test per-macro toggle binds, and test both editing conflict policies. Verify simultaneous conflicting outputs skip safely.
- [ ] Test Double Edit's placement order, configurable mouse paths, tap and hold modes at multiple sensitivities; test weapon pullout only after a completed edit sequence.
- [ ] Test a failed or rejected input, a partial press, and emergency release. Verify no synthetic input remains held.
- [ ] Test remembered sign-in opt-in, DPAPI CurrentUser encryption, app restart, 30-day expiry, sign-out, password recovery, and account switching between Windows users.
- [ ] Test pending username review on registration and owner rename/approve/reject flows; verify pending and rejected accounts cannot sign in and the audit history records the decision.
- [ ] Test profile import/export with cancel, duplicate names, oversized/invalid files, multi-profile import, and verify imported profiles remain disabled.
- [ ] Review an explicitly exported diagnostics file and confirm it contains no session, refresh, password, recovery, username, or arbitrary user content.
- [ ] Visually inspect the recommended palette, color controls, reset, animation toggle, and expandable keyboard-accessible feature instructions at supported window sizes.
- [ ] Verify SendInput bindings in a harmless local input test first, including injected-event recursion protection and emergency stop.
- [ ] Verify real foreground executable detection and focus loss while an input is held.
- [ ] Verify tap/hold/cancel, both Drag confirmation modes, configuration switching and shutdown release.
- [ ] Disconnect networking, stop the backend, revoke/expire/ban a test member; verify tools cease within the documented authorization window and remain disabled on reconnection.
- [ ] Compare detected CPU/GPU/RAM/resolution/refresh rate against Windows display/system settings.
- [ ] On the installed Fortnite build, verify every exposed configuration key is still supported, check the proposed values and confirm the game accepts them after restart. If support is uncertain, leave that key unchanged.
- [ ] Create a real settings backup, modify one setting externally, restore, and verify unrelated/external changes survive.
- [ ] Exercise Filter Keys apply/test/restore and review accessibility recovery behavior.
- [ ] Check GPU/CPU utilization of decorative effects with the app idle, minimized, and Fortnite running. Do not claim a performance budget until measured.
- [ ] Use your production HTTPS host; test recovery, MFA, transfers, one-session conflicts and the owner workflow.
- [ ] Verify code signature only after you actually sign the binaries, and publish checksums of final bundles.

Game input acceptance is not guaranteed. There is no anti-cheat bypass or injection, and gameplay automation is not tournament-approved.
