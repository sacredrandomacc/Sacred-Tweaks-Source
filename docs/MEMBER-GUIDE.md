# Member guide

Keep the executable and its `_internal` directory together. Install Microsoft Edge WebView2 Runtime if startup requests it. The owner supplies the correct `client-config.json` API address. Double-click the member executable; do not run it with unnecessary administrator privileges.

Redeem your unused license, choose your username/password, and save the recovery codes when shown. Codes work once. Your license clock starts at redemption. You can change your password through recovery; the owner handles username changes and transfers to another PC. Internet is required throughout licensed use.

On the member sign-in form, “Remember me on this PC” is optional. It saves a rotating refresh credential encrypted with Windows DPAPI for the current Windows user. It expires after 30 days and is cleared when you sign out or recover your password. If Windows cannot unlock it, sign in normally. A flagged username pauses account access until the owner reviews it; the review screen explains how to contact the owner for a compliant rename or status update.

Your username at the top right opens the account menu; license duration appears inside it. Sacred access includes the full feature set. An owner may lock an individual feature; those changes take effect at the next login.

With Sacred Tweaks running and Fortnite focused in Windowed Fullscreen, press Tab to open the standalone companion window. Choose another hotkey in Appearance if Tab is already bound in-game. The menu shows loadout previews, live macro toggles and emergency stop, saved profile editing, Windows shortcuts, and appearance controls. Closing the menu restores game focus. Performance, measurements, and restore controls remain in the main app. For display-mode limits, see `STANDALONE-OVERLAY.md` included beside this guide.
If startup hangs, launch `Sacred Tweaks.exe` with `--no-overlay` from PowerShell as described in that guide, then share the last lines of `%LOCALAPPDATA%\SacredTweaks\startup.log` for diagnosis.

Home opens with loadouts. Configure macros, binds, and appearance, then save a named loadout. Preview before applying; Apply releases current inputs, installs the saved setup, and leaves every macro disabled until you enable it. Loadouts do not change Performance or Windows settings.

Macros start disabled. The first time this account opens Macro Studio on this PC, acknowledge the usage warning; it remains available to reread. Each macro has an individual toggle shortcut. Misc → Editing macro conflicts defaults to keeping the most recently enabled editing macro; Allow multiple is optional. Conflicting simultaneous input sequences are skipped. Single Edit sends edit/select/confirm; Drag holds select while the edit key is held. Double Edit places floor and cone, then performs two configurable selection gestures. Auto gun pullout sends the chosen weapon slot after an edit sequence completes. Configure the actual Fortnite binds and timing; set the press duration to suit your setup. Fortnite may reject synthetic inputs, and the app cannot verify that a build or edit succeeded. Focus loss, session loss, and emergency stop release held inputs. A reconnect never restarts macros.

Before changing graphics, close Fortnite, inspect the current/proposed values, and approve the plan. Preserve backups. Use Restore previous settings on the sign-in screen, or Backups & restore inside the workspace. Restoration is available without login or an active license and skips values changed by something else since Sacred Tweaks applied them. Review any conflict/partial-failure report. Windows Settings links open the relevant Windows page for manual changes.

Filter Keys is an accessibility feature. Filtering, repeat delay and repeat rate are distinct; aggressive settings can make normal typing difficult. Use the test area and restore backup if needed. It is not a universal latency reduction.

Performance records distinguish manually supplied FPS/frame-time results from available system readings. Use the same map, route, resolution and measurement interval for before/after comparisons. Unsupported metrics remain unavailable; the app does not invent FPS improvements.

If access is lost, use Restore or sign in again. If another active session or device prevents login, contact your owner or submit a transfer request. Keep recovery codes and reset credentials private.

In My profiles, Import and Export move a bounded JSON profile bundle between installs. Imported profiles are saved as data only and stay disabled until you load and explicitly enable a macro. Account → Export basic diagnostics creates a small allowlisted app report after you choose a save location; inspect it before sharing.

For updates, open Account → Download details. Copy the owner’s HTTPS package link into your browser, verify the published SHA-256 when provided, close the app, and replace the application folder while keeping the correct client-config.json. Local backups/preferences live separately in your Windows profile. Updates are manual.
