# Required Windows release validation

These checks have not been performed in the Linux development environment. Do them before distributing the application for real use.

- [ ] Run `build-windows.ps1`; retain test and both WebView2 launch results.
- [ ] Launch both portable bundles on a second standard-user Windows 10/11 PC.
- [ ] Verify default/125%/150% display scaling, resize, reduced motion, and minimized effects.
- [ ] Redeem each tier and visually inspect welcome, dropdown, lock badge/blur and keyboard access.
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
