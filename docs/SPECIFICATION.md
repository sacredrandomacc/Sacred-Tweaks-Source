Build **Sacred Tweaks**, a polished, private-group Windows application for Fortnite settings, input tools, and macros, together with a separate owner application named **Sacred Tweaks Manager**.

Deliver working applications, a real licensing backend, source code, build instructions, and packaged Windows executables. A visual mockup or interface with nonfunctional buttons is insufficient.

Use the requirements below as the agreed product specification. Make reasonable technical decisions without repeatedly asking me small questions. Ask only when credentials, hosting access, or a genuinely blocking decision is required.

## 1. Architecture and delivery

Create three connected components:

1. **Sacred Tweaks:** the member Windows app.
2. **Sacred Tweaks Manager:** a separate owner-only Windows app.
3. **Hosted backend:** accounts, licenses, permissions, device registrations, sessions, and administration.

Choose a maintainable stack that supports polished animation, Windows integration, secure authentication, and `.exe` packaging. Briefly explain your choice before implementing.

The backend must enforce owner authorization. Possessing the Manager executable must never grant administrative access. Never embed owner credentials, database credentials, signing secrets, or privileged API keys in either executable.

Prefer documented Windows APIs and supported Fortnite settings. Do not implement anti-cheat bypasses, game injection, memory manipulation, or stealth mechanisms. Do not claim the macros are unbannable or tournament-approved: Epic’s competitive rules prohibit gameplay automation.

## 2. Visual design

Use a **black-and-violet** theme:

- Near-black backgrounds with layered violet accents.
- Custom buttons, animated toggles, smooth navigation, and polished dropdowns.
- Subtle glass panels, particles, cursor parallax, and a rotating 3D Sacred logo.
- Clear typography, consistent spacing, readable contrast, and resizable layouts.
- Proper loading, empty, disconnected, locked, and error states.
- Adjustable animation intensity, reduced-motion support, and a lightweight mode.
- Pause expensive decorative effects while Fortnite is running or the app is minimized.

Animations should feel cohesive and responsive. Keep the app’s CPU/GPU use low.

## 3. Accounts and license redemption

This is an **invite-only private-group application**.

Registration flow:

1. Enter an unused license key.
2. Validate it and display its tier.
3. Choose a unique username and password.
4. Create the account and bind the license atomically.
5. Display downloadable/copyable recovery codes.
6. Register the member’s device.
7. Play the tier welcome screen.

A license must only be redeemable once. Concurrent redemption attempts must not create duplicate accounts or claims.

**License duration begins on successful redemption**, using server time. Creating a key does not start its timer. Support timed and permanent licenses.

Reinstalling, resetting a password, renaming an account, or transferring a device must not restart the license duration.

Members cannot change their usernames. Only the owner can rename them, preserving their account identity and history.

## 4. Account-sharing protection and recovery

Use:

- One registered PC per account by default.
- One active authorized session per account.
- Server-side session verification and revocation.
- Device-transfer requests that the owner can approve.
- Owner-controlled transfer/reset cooldowns.
- Rate limits and login-abuse protections.
- Alerts for conflicting sessions and repeated device changes.

Use privacy-conscious device registration that tolerates ordinary Windows updates. A changed IP address alone must not cause an automatic ban. Explain practical limitations honestly; device registration cannot prove which person is physically using a PC.

Passwords must be securely hashed using a suitable modern password-hashing algorithm. Store session secrets securely using Windows facilities where appropriate.

Account recovery uses **recovery codes and owner-assisted resets, without requiring email**:

- Show plaintext recovery codes only when generated.
- Store their verification hashes.
- Each code works once.
- Generating a replacement set invalidates the old set.
- Owner-assisted recovery issues an expiring, single-use reset credential.
- Password resets revoke existing sessions.
- The owner can never view member passwords.

Owner authentication requires a password plus an authenticator-app code, with recovery codes.

## 5. Internet and session behavior

Internet is required throughout use.

Regularly validate the session, license expiration, bans, and revocations. Use a documented short heartbeat/authorization window; do not claim mathematically instantaneous revocation.

When authorization cannot be renewed:

- Pause licensed tools.
- Stop every running macro.
- Release every synthetic held input.
- Show a clear reconnect or access-denied screen.
- Never automatically resume a macro after reconnection.

Bans, revoked licenses, and expiration terminate access when detected.

**Tier and ordinary permission changes apply at the next successful login.** Keep the current session’s permission snapshot until then, except for bans, revocations, and expiration.

Restoring previously changed settings must remain available after expiration, suspension, revocation, or disconnection.

## 6. Tier permissions

Use these exact tiers:

| Feature                                           | Core   | Plus   | Pro    | Elite |
| ------------------------------------------------- | ------ | ------ | ------ | ----- |
| Single Edit Macro                                 | Yes    | Yes    | Yes    | Yes   |
| Fortnite performance presets                      | Yes    | Yes    | Yes    | Yes   |
| Performance measurements                          | Yes    | Yes    | Yes    | Yes   |
| Custom themes and visual effects                  | Yes    | Yes    | Yes    | Yes   |
| Potato graphics presets                           | Locked | Yes    | Yes    | Yes   |
| Filter Keys settings and presets                  | Locked | Locked | Yes    | Yes   |
| Owner-published presets                           | Locked | Locked | Yes    | Yes   |
| Drag Macro                                        | Locked | Locked | Locked | Yes   |
| Advanced performance controls                     | Locked | Locked | Locked | Yes   |
| Multiple custom profiles and saved configurations | Locked | Locked | Locked | Yes   |
| Beta update channel                               | Locked | Locked | Locked | Yes   |

All tiers include backups, restoration, account protection, and stable updates.

Members with access to a macro can customize its current configuration and use included presets. Saving multiple personal configurations is Elite-only by default.

For each individual license, the owner can:

- Inherit tier permissions.
- Explicitly unlock a feature.
- Explicitly lock a feature.
- Enforce a setting value where applicable.

Individual overrides take priority. Validate permissions and enforced values beyond the UI. Explain that local executable modification cannot be made impossible.

Locked features remain visible:

- Feature names stay readable.
- Controls and values are blurred.
- Show a lock icon and required-tier badge.
- Individually restricted features show “Locked by owner.”
- Prevent mouse, keyboard, shortcut, and alternate-route activation.
- Clicking displays exactly: **“contact the owner for upgrading”**
- Do not include an upgrade-request button or payment flow.

## 7. Welcome screens and account menu

Play the appropriate welcome animation on **every successful login**.

Tier text uses a moving animated gradient:

- **Core:** bronze/copper.
- **Plus:** silver/steel/white.
- **Pro:** diamond/icy blue/cyan/white.
- **Elite:** gold/amber/pale yellow.

Give tiers distinct welcome presentations within the black-and-violet brand. Manager can customize welcome text, effects, and badges, including per-license welcome messages.

Place the username at the **top right** with a downward chevron and hover feedback indicating it is clickable.

Clicking opens an animated dropdown showing:

- Tier with animated gradient.
- Remaining license duration or “Permanent.”
- Account settings.
- Sign out.

License time stays hidden while closed. Rotate the chevron when opened; clicking outside closes it.

## 8. Macro tools

Provide explicit enable/disable controls, customizable activation keys, relevant input bindings, timing in milliseconds, selectable presets, visible status, and binding-conflict detection.

Never guarantee exact timing or successful in-game edits; OS scheduling and game settings affect behavior.

**Single Edit Macro:**

- Each cycle sends **Edit → Select → Confirm**.
- Tapping the activation key runs one cycle.
- Holding repeats cycles at the configured interval.
- Releasing cancels pending repetition and releases held synthetic inputs.
- Members customize bindings, delays between steps, and repeat interval.
- The player still aims and chooses edit tiles.

**Drag Macro:**

- Uses the member’s edit bind as its activation key.
- Activating edit automatically engages the configured select input.
- Holding allows the player to drag across tiles without separately clicking select.
- Releasing releases the synthetic select input.
- Offer two modes:
  - **Auto Confirm:** release select and send the configured confirm input.
  - **Manual Confirm:** release select; the player confirms normally.
- Account for Fortnite’s own confirmation settings to avoid duplicate confirmation.

Handle activation/output binding overlap without recursive triggering.

All macros must:

- Work only while Fortnite has foreground focus.
- Stop and release held inputs on focus loss, logout, disconnect, shutdown, revocation, or emergency stop.
- Avoid conflicting simultaneous execution.
- Have a configurable emergency-stop shortcut.
- Start disabled after login.
- Avoid recording unrelated keyboard input.

Switching configurations automatically stops macros and releases inputs **before** loading the new configuration. Do not restart them automatically.

Elite members can save, name, duplicate, edit, and delete multiple configurations, subject to license overrides.

## 9. Fortnite and Windows performance tools

Detect CPU, GPU, RAM, Windows version, display resolution, and refresh rate.

Let members choose target FPS: 60, 120, 144, 165, 240, 360, or Custom.

Recommendations prioritize **maximum FPS**. Highlight monitor refresh rate, explain recommendations, and allow manual preset selection. Never apply changes automatically from detection alone.

Provide:

- Simple preset mode for Core and above.
- Advanced individual controls for Elite by default.
- Potato graphics presets for Plus and above.
- Owner-published presets for Pro and above.

Respect tier boundaries: Core recommendations must not silently apply Plus-only potato settings.

Before applying, show current values, proposed values, visual tradeoffs, compatibility, administrator requirements, and restart requirements.

Use supported Fortnite configuration options. Validate against the installed version and preserve unrelated settings. Do not modify game assets or force unsupported hidden settings.

Optional Windows controls can cover Game Mode, supported power settings, background capture, graphics preferences, and startup-app review. Where no supported programmatic method exists, open the correct Windows settings page and explain the manual step.

Members choose Fortnite changes, Windows changes, or both. Never silently disable security software, Windows Update, or unrelated services.

Back up original values before changes. Support reliable restoration, partial-failure reporting, and rollback without overwriting unrelated later changes.

## 10. Filter Keys and measurements

Provide supported Windows Filter Keys controls, repeat settings where available, presets, a keyboard test area, and restoration.

Clearly distinguish repeat delay, repeat rate, and filtering behavior. Do not claim Filter Keys universally reduces latency.

Only label a preset with a professional player’s name when its settings have a verifiable source and date. Otherwise use descriptive names.

Performance measurements are available to every tier:

- Before/after comparison records.
- FPS and frame-time information through a supported, non-injection method where available.
- CPU/GPU/RAM usage where supported.
- A repeatable measurement procedure and saved results.

Clearly mark unavailable metrics and explain measurement limitations. Never fabricate benchmark data, latency reductions, or FPS gains.

## 11. Sacred Tweaks Manager

Provide working screens for:

- User search and account details.
- Owner-only username changes.
- Individual and bulk license generation.
- Tier, duration, expiration, and redemption status.
- License extensions, suspension, revocation, and replacement.
- Per-license permissions and enforced values.
- Temporary/permanent application bans with reasons.
- Session termination and device resets/transfers.
- Recovery and password-reset assistance.
- Tier welcome editors with previews.
- Owner preset publishing and version history.
- Announcements, maintenance notices, and releases.
- Stable/beta channel management.
- Member feedback and optional diagnostic attachments.
- Administrative audit history.

These bans apply to Sacred Tweaks, not Fortnite accounts.

Require confirmation for destructive administrative actions. Record who changed what and when without logging passwords, recovery codes, or complete license keys.

## 12. Verification and deliverables

Implement in manageable stages while preserving this specification. Keep a requirements checklist and explicitly identify incomplete or externally blocked work.

Test meaningful behavior, including:

- Concurrent key redemption.
- Tier inheritance and individual overrides.
- Next-login permission updates.
- Bans, expiration, revocation, and connection loss.
- Duplicate sessions and device transfer.
- Recovery-code reuse prevention and owner authorization.
- Macro cancellation, focus loss, configuration switching, and input release.
- Settings backup, restoration, and partial failures.
- Locked controls through mouse and keyboard.
- Installation and launch of both packaged apps.

Inspect actual screenshots of all major screens, tiers, dropdowns, dialogs, and error states. Verify text, blur, gradients, layout, and animation performance.

Deliver:

1. Both Windows executables/installers.
2. Complete source code.t0
3. Backend service, schema, and migrations.
4. Configuration template without real secrets.
5. Build, hosting, deployment, and initial-owner setup instructions.
6. Required hosting costs and external-service dependencies.
7. Test results and known limitations.
8. A short owner guide for creating licenses and managing members.

If live hosting credentials or a code-signing certificate are unavailable, provide deployment-ready components and state exactly what remains. Do not describe a local-only demo as a deployed service or an unsigned executable as signed.
