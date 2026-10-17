# Sacred Overlay — Windows test build

The desktop app and the Game Bar widget are separate applications. Python's
build-windows.ps1 does not install a Game Bar widget. Keep the desktop member
app running and signed in; the widget only controls that app's input engine.
Manager is for account management, not the companion you need to pair.

## Build and register on your own PC

Install Visual Studio 2022 with Universal Windows Platform development, its
C# UWP tools, and Windows SDK 10.0.22621.0. Enable Windows Developer Mode in
Settings for development registration. From the source folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-gamebar.ps1 -Register
```

If Windows reports a missing runtime dependency during registration, deploy
`gamebar/SacredOverlay.csproj` from Visual Studio (Debug, x64, Local Machine) so
Visual Studio installs its UWP debug dependencies. These development builds
are not a signed Store distribution; retail packaging and Store submission are
separate release steps. Do not distribute a private signing key.

The widget uses an authenticated local HTTP connection. UWP blocks loopback by
default. For this development package only, open an Administrator PowerShell:

```powershell
$widgetPackage = Get-AppxPackage -Name SacredOverlay
if (-not $widgetPackage) { throw 'Register the widget first in your normal account.' }
CheckNetIsolation.exe LoopbackExempt -a -n=$($widgetPackage.PackageFamilyName)
```

This allows only this package's loopback traffic. Undo with the same command
using `-d` instead of `-a`. Do not disable the Windows firewall or grant a
blanket exception. This development transport requires review before Store
submission; it is not presented as a Store-certified distribution route.

## Open, pair, and pin

1. Run the rebuilt Sacred Tweaks member app and sign in to the hosted backend.
2. Open Macro studio, select a new macro card, and click Pair Game Bar widget.
3. Press Win+G. Open the Widgets menu, choose Sacred Overlay, and pin it.
4. Enter the local port and temporary pairing code from the desktop app.
5. Choose a macro, edit the bindings/timing, Save, acknowledge the cheat-risk
   warning, and Enable. Close Game Bar to return input focus to Fortnite.
6. Tab expands/collapses the pinned widget's content; its header remains. F9
   and F10 are alternatives in widget settings. Game Bar owns input focus:
   use Win+G to click controls. Tab is not swallowed and can also open Fortnite's
   inventory; rebind it if that conflicts. If the hotkey watcher cannot start,
   the widget reports the error and Win+G remains the supported access path.
7. Change panel opacity and accent in widget settings. Those appearance and
   hotkey choices persist locally. Pairing secrets and risk acknowledgement do
   not persist. Signing out or closing the desktop app revokes pairing.

Changing a macro stops the previous one. One macro is active at a time. Focus
loss while running, disconnect, expired authorization and emergency stop release
synthetic inputs. Opening Game Bar during a running macro stops it; re-enable
explicitly when ready. Opening controls is not an exemption from authorization.

## Macro behavior and compatibility

- Pre-fire: one manually triggered shot, wall selection, placement input. It
  does not detect opponents, edits, or the correct firing time.
- Fast pickup: repeated interact input while held, minimum 30 ms interval.
  It cannot bypass server pickup rules or guarantee the fastest pickup.
- Wall replace: pickaxe selection, swing, wall selection, placement attempt.
  Tune step delay for the weapon animation. It cannot detect wall health,
  destroy a full-health wall in one swing, or guarantee claiming a wall.
- Auto Build: holding any of four distinct piece binds holds a separate
  secondary-place input; releasing all piece binds releases it. Bind that
  secondary input to Place Building in Fortnite. Native piece binds pass through.
- Mantle repeat (requested as “zenn mantle”): repeated jump/mantle input while
  held. Reachable ledges and game mantle settings determine success. This is
  not a fall-damage exploit and does not prevent death from a fall.
- Quick Reset and Floor + Cone are the only two extra ideas selected from the
  supplied listings (below the requested five-item cap). These are original
  input sequences; listing scripts were not supplied or copied.

Bindings are typed names: A–Z, 0–9, F1–F24, SPACE, TAB, SHIFT, CTRL, ALT,
MOUSE1–MOUSE5, and supported navigation names. Use a separate activation key
for sequences. Do not overlap emergency stop with any output/activation key.

Old jetpack, invisible-wall, invulnerability and XP listings are not included.
The list spans 2023–2026; a recent listing date does not establish compatibility.
All game outcomes need Windows/in-game validation. Tests of input sequences do
not establish Fortnite compatibility, tournament permission, or ban safety.

## Verification boundaries

Automated tests cover sequence order, hold/release, overlapping piece keys,
focus/lease/emergency cancellation, pairing authentication, token rotation,
browser-origin rejection, and command allowlisting. Windows CI compiles the
apps/widget; interactive pinning, Tab behavior, fullscreen behavior, and game
input still require testing on the target Windows installation.

Epic's statement: https://www.fortnite.com/news/fortnite-chapter-2-season-5-competitive-integrity-update
Game Bar SDK: https://learn.microsoft.com/en-us/gaming/game-bar/overview
SDK sample/API source: https://github.com/microsoft/XboxGameBarSamples

## Ownership limits

Sacred LLC notices establish the claimed ownership of original work. They do
not make public source or binaries uncopyable and do not force AI systems to
obey the text. Server-side entitlement checks remain the functional access
control. Public-repository visibility was not changed. Third-party license
notices remain applicable.
