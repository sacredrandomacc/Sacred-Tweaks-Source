# Owner guide

1. Bootstrap the owner on the server, enroll the TOTP secret, and store recovery codes offline. Open Sacred Tweaks Manager and sign in with password plus authenticator code. Possession of the executable does not grant owner rights.
2. After confirming a purchase through your own payment channel, issue Sacred 30-day access or lifetime access in Licenses. Copy generated keys immediately. Thirty-day time begins only on redemption, and renewal is manual. Share keys privately yourself; the application does not collect payment, send keys, or email customers.
3. Members validate a key, choose a username/password, and save their recovery codes. Their device is registered at redemption. A username rename, password reset, or device transfer does not create new license time.
4. Search Users to inspect a member. Rename is owner-only. Session termination, bans, license suspension/revocation, recovery assistance and device resets use confirmation dialogs and record an audit event.
5. Use Username review for accounts flagged by the versioned username screen. The screen only exposes a review category, not the lexicon. Rename to a compliant username to restore access, approve an exception only with a documented rationale, or reject with a review note. Flagged accounts cannot sign in while pending/rejected. Automated checks can be wrong; review the name in context. Decisions are recorded in the audit history.
6. Standard Sacred access includes all features. Set individual overrides to inherit, allow, or deny. Enforced settings use feature IDs and field names in `CONTRACT.md`. Ordinary overrides take effect at the member's next login. Revocations, bans and expiration are checked during authorization renewals.
7. Review device-transfer requests. Approve the requested device only after confirming the member's identity through your existing private-group channel. Device transfer/reset and password-assistance cooldowns are owner configurable. IP changes alone do not ban an account.
8. Password assistance generates an expiring single-use reset credential. Give it privately to the member, who enters it with a new password in account recovery. You cannot view their existing password. Password resets revoke remembered sessions too.
9. Publish named presets, announcements, welcome presentation settings, and stable/beta release entries. Published preset versions remain in history. Verify that download URLs are HTTPS and point to your release files. Members are told when measurements or settings are unavailable.
10. Check feedback and audit history. Optional diagnostics should be reviewed before sharing externally. Application bans affect Sacred Tweaks only.

See `REQUIREMENTS.md` for any incomplete feature depth. Use descriptive preset names; professional-player names require a verifiable source and date. Never advertise macros as unbannable or tournament-approved.

## Auto-updates for members

Members install once with **Sacred Tweaks Updater.exe** (one file). Each time they open it, it
checks your server, installs any newer member build, and launches Sacred Tweaks. The Manager is
never auto-updated; download and replace it yourself.

To publish an update:

1. Run `build-windows.ps1`. It prints the member package SHA-256 and saves it to
   `dist/Sacred-Tweaks-Windows-x64.sha256.txt`.
2. Upload `dist/Sacred-Tweaks-Windows-x64.zip` to an HTTPS location you control.
3. In the Manager, open Content studio → Releases. Enter the version (for example `0.6.1`), the
   HTTPS link, the SHA-256, choose **App: Sacred Tweaks**, channel **Stable**, and publish.

The updater only installs stable member releases whose download matches the SHA-256 exactly,
keeps each member's `client-config.json`, and rolls back if the swap fails. Builds are unsigned,
so Windows SmartScreen may warn the first time the updater runs.
