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

The companion is a separate topmost desktop window. When hidden it has no
visible or invisible input rectangle, so Windows delivers input to the active
application. Switching away from Fortnite closes the menu; returning to it
makes the hotkey available again. Closing and restarting Fortnite is handled
the same way. The app watches foreground window identity and key state; it does
not inject into Fortnite, inspect its memory, hook its renderer, or change its
files to draw the interface.

Exclusive fullscreen may prevent normal desktop windows from appearing over
the game; use Windowed Fullscreen for reliable overlay visibility. Windows
controls foreground activation, and some system states can deny focus changes.
If the panel is visible but not interactive, click the panel once and retry;
report the Windows and Fortnite display modes for diagnosis. The app is not
officially approved or guaranteed ban safe. Avoid using third-party software
where a game or event disallows it. The separate desktop macro studio has
additional gameplay automation risks and is not shown in this companion.

## Build from source

On Windows 10/11 with Python 3.12, WebView2, and a configured backend:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-windows.ps1
```

The member and owner ZIPs are written to `dist`. The script runs unit tests,
packages both apps, and launches each for a WebView2 smoke test unless
`-SkipSmokeTest` is used. No Xbox Game Bar or UWP build is involved.

## Validation boundary

Source checks and simulated controller tests cover edge-triggered hotkeys,
full-window hiding, focus restoration calls, Alt-Tab, game restart, changing
window bounds, preference persistence, and account-data minimization. Only a
Windows computer running Fortnite can verify actual topmost visibility, mouse
interaction, focus policy, display scaling, resolution changes, and anti-cheat
compatibility. Test these on your own PC in a permitted environment before
relying on the companion.
