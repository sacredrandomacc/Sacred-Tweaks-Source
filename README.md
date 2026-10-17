# Sacred Tweaks

A private-group Windows member application, a separate owner Manager, and a deployable licensing service. The supplied product brief is preserved in `docs/SPECIFICATION.md`.

**Release status:** source implementation for Windows validation. This source archive does **not** contain prebuilt Windows executables. Windows packaging and real Fortnite testing cannot be performed in the Linux build workspace. No backend has been deployed to a public host and no binaries have been code-signed. Read `docs/VERIFICATION.md` and `docs/REQUIREMENTS.md` for the exact validation record and outstanding work.

## Components

| Component | Entry point | Runtime |
|---|---|---|
| Member | `member.py` | Python 3.12, pywebview, Windows WebView2 |
| Owner Manager | `manager.py` | Same runtime, server-enforced owner role |
| Licensing API | `python -m server` | Python 3.12 standard library, SQLite |

The HTML/CSS/JavaScript interface is bundled locally. There is no Node build step or cloud UI dependency. Passwords use scrypt; tokens and recovery codes are verified by hashes. Session tokens stay in desktop process memory. Device registration uses an opaque random ID protected by the current Windows profile's DPAPI.

## Run the service locally

```powershell
py -3.12 -m server --db data/sacred.db --bootstrap-owner owner
py -3.12 -m server --db data/sacred.db --host 127.0.0.1 --port 8765
```

Bootstrap prompts for an owner password and prints the authenticator secret and recovery codes once. Import the secret into an authenticator and keep the recovery codes private. There are no default accounts or credentials.

Copy `client-config.example.json` to `client-config.json` and use this only for local development:

```json
{"api_url":"http://127.0.0.1:8765","allow_local_http":true}
```

Then, on Windows:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.venv\Scripts\python.exe manager.py
.venv\Scripts\python.exe member.py
```

Sign in to Manager with the owner password and authenticator code. Generate a license, then redeem it in the member app using a separate member account. Owner and member sessions follow the same one-active-session rule.

## Build Windows applications

Install 64-bit Python 3.12 and Microsoft Edge WebView2 Runtime on Windows 10/11. Run:

```powershell
.\build-windows.ps1
```

The build runs tests, packages both launchers separately with PyInstaller, and attempts a real WebView2 window startup check for each. Output folders contain `Sacred Tweaks.exe` and `Sacred Tweaks Manager.exe`, each with its required `_internal` folder. ZIPs are created in `dist/`. These are portable application bundles, not installation wizards. Do not distribute an `.exe` without its associated folder. They are unsigned; signing is an external release step.

The included GitHub Actions workflow supports a manual Windows build after you upload this source to your own repository. It has not been run on your account. Do not put real passwords, licenses, recovery codes, or server databases in that repository.

## Tests

```sh
python -m unittest discover -s tests -v
```

Backend tests use isolated temporary SQLite databases and a deliberately cheaper constructor-only password cost. Production CLI always uses the stronger default. Browser checks live in `tests/ui-smoke.cjs` and require Playwright/Chromium; their fixtures are test-only and are not bundled into the desktop apps.

See `docs/DEPLOYMENT.md`, `docs/OWNER-GUIDE.md`, and `docs/MEMBER-GUIDE.md`.

## Permanent hosted backend

For Vercel with persistent PostgreSQL, follow [the hosted setup guide](docs/VERCEL.md).
The Windows app build is separate from the hosted API.

## Macro studio and Game Bar

Seven additional input modes, a paired Game Bar companion, and Sacred LLC ownership notices are included. See [Game Bar setup and limitations](docs/GAME-BAR.md). The widget needs its own Windows build and registration. Gameplay automation is cheating under Epic’s rules and carries account-ban and tournament risks.
