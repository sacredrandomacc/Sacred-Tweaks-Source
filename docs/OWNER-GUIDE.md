# Owner guide

1. Bootstrap the owner on the server, enroll the TOTP secret, and store recovery codes offline. Open Sacred Tweaks Manager and sign in with password plus authenticator code. Possession of the executable does not grant owner rights.
2. In Licenses choose Core, Plus, Pro, or Elite, a duration or permanent, and a quantity. Copy generated keys immediately. Their timers begin only on redemption. Share them privately yourself; the application does not send invitations or email.
3. Members validate a key, choose a username/password, and save their recovery codes. Their device is registered at redemption. A username rename, password reset, or device transfer does not create new license time.
4. Search Users to inspect a member. Rename is owner-only. Session termination, bans, license suspension/revocation, recovery assistance and device resets use confirmation dialogs and record an audit event.
5. Set license overrides to inherit, allow, or deny each feature. Enforced settings use the feature IDs and field names in `CONTRACT.md`. Tier and normal overrides take effect at the member's next login. Revocations, bans and expiration are checked during authorization renewals.
6. Review device-transfer requests. Approve the requested device only after confirming the member's identity through your existing private-group channel. Device transfer/reset and password-assistance cooldowns are owner configurable. IP changes alone do not ban an account.
7. Password assistance generates an expiring single-use reset credential. Give it privately to the member, who enters it with a new password in account recovery. You cannot view their existing password. Password resets revoke sessions.
8. Publish named presets, announcements, welcome presentation settings, and stable/beta release entries. Published preset versions remain in history. Verify that download URLs are HTTPS and point to your release files. Members are told when measurements or settings are unavailable.
9. Check feedback and audit history. Optional diagnostics should be reviewed before sharing externally. Application bans affect Sacred Tweaks only.

See `REQUIREMENTS.md` for any incomplete feature depth. Use descriptive preset names; professional-player names require a verifiable source and date. Never advertise macros as unbannable or tournament-approved.
