# Sacred Tweaks standalone companion

The member Windows app starts a second, initially hidden desktop window. With
Fortnite active, press **Tab** to open the companion; press Tab, Escape, or the
close button to hide the entire window. Its saved key can be changed to F6,
F7, F9, F10, or F11 on the Appearance page. Choose a key that is unused in
Fortnite: while the menu is hidden, the key still reaches the game. F8 is
reserved for the desktop app's emergency stop.

## Install and launch

1. Download `Sacred-Tweaks-Windows-x64.zip` from the Windows build artifact.
   On Windows, if the downloaded ZIP shows an **Unblock** checkbox in Properties,
   select it before extraction. Extract the whole ZIP into a folder; keep the
   `.exe` and `_internal` folder together.
2. In the extracted folder, set `client-config.json` to your HTTPS licensing API
   origin. Launch `Sacred Tweaks.exe` and sign in. The owner Manager is a
   separate download and has no companion window.
3. In Fortnite's video settings, select **Windowed Fullscreen** (borderless).
   Leave Sacred Tweaks running. Focus Fortnite and press Tab. You can click
   buttons and controls directly; Windows + G and widget registration are not
   used. Use the Appearance page to change the key if Tab conflicts with a
   game binding.

The companion has four pages: Home, Macros, Windows, and Appearance. Home previews
and applies saved loadouts; applying always releases current inputs and starts
macros disabled. Macros shows individual enable switches and emergency stop,
and lets members edit saved profile names, keybinds, and timing. Saving a profile
does not load or enable it. Configure new macros in the main app. Performance,
Measurements, and Backups & Restore remain in the main app.

In Appearance, customize the shortcut, panel position (Center, Left, Right),
opacity, accent color, and reduced motion. Wide is the only size for now; old
Compact and Standard preferences are upgraded to Wide on launch. Use
Reset to default to restore the original appearance. The overlay is a separate
topmost desktop window. When hidden it has no visible or interactive input
area, so Windows delivers input to the active application. Switching away from
Fortnite closes the menu; returning makes the hotkey available again. Closing
and restarting Fortnite is handled the same way. The app watches foreground
window identity and key state; it does not inject into Fortnite, inspect its
memory, hook its renderer, or change its files to draw the interface.

If display scaling clips the controls, click the ↺ button in the header or
press **Ctrl+Shift+0** while the companion is focused to restore Wide size
and Center position. If even that is inaccessible, close Sacred
Tweaks and rename `%LOCALAPPDATA%\SacredTweaks\overlay-preferences.json` before
reopening it; the defaults will be recreated.
The companion's hidden WebView2 window is initialized when the member app
starts. Allow it to load before pressing the hotkey for the first time.

If Sacred Tweaks freezes at startup, close it in Task Manager, then open
PowerShell in the extracted `Sacred Tweaks` folder and run:

```powershell
& '.\Sacred Tweaks.exe' --no-overlay
```

This starts the normal desktop app without the companion, which helps isolate
the issue. The non-sensitive startup trace is at
`%LOCALAPPDATA%\SacredTweaks\startup.log`; share its last few lines if the
problem persists. Never share your `client-config.json` or account credentials.

Exclusive fullscreen may prevent normal desktop windows from appearing over
the game; use Windowed Fullscreen for reliable overlay visibility. Windows
controls foreground activation, and some system states can deny focus changes.
If the panel is visible but not interactive, click the panel once and retry;
report the Windows and Fortnite display modes for diagnosis. The app is not
officially approved or guaranteed ban safe. Avoid using third-party software
where a game or event disallows it. The separate desktop macro studio has
additional gameplay automation risks; the overlay can toggle configured macros.

## Build from source

On Windows 10/11 with Python 3.12, WebView2, and a configured backend:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-windows.ps1
```

The member and owner ZIPs are written to `dist`. The script runs unit tests,
packages both apps, and launches each for a WebView2 smoke test unless
`-SkipSmokeTest` is used. No Xbox Game Bar or UWP build is involved.

## Validation boundary

Unit and source smoke checks cover edge-triggered hotkeys, full-window hiding,
focus restoration calls, Alt-Tab, game restart, clamped size/position within
changing window bounds, preference persistence, permission-gated profile
editing, and account-data minimization. Only a Windows computer running
Fortnite can verify actual topmost visibility, mouse interaction, focus policy,
display scaling, resolution changes, and anti-cheat compatibility. Test these
on your own PC in a permitted environment before relying on the companion.
