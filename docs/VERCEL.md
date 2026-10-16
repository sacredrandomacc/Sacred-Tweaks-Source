# Hosted backend: Vercel + Neon PostgreSQL

This deploys only the API. The Windows member and manager apps remain desktop
apps. Your PC can be off after setup. Hosting availability and costs depend on
your provider plan; a sleeping database can make the first login slower.

## 1. Prepare the code

Merge the Vercel/PostgreSQL pull request into `main`, then use GitHub Desktop's
**Fetch origin → Pull origin** to update your local source folder. Do not build
or upload the Windows executables to Vercel.

## 2. Create a dedicated database

Open https://console.neon.tech and create a PostgreSQL project in US East
(Northern Virginia), near the Vercel `iad1` region used in `vercel.json`.
Use its Connect dialog to copy the pooled PostgreSQL connection string. Keep
`sslmode=require` (or stronger) in it. This URL contains the database password;
never put it in GitHub, client-config.json, chat, screenshots or a command line.

This guide creates a **new cloud database**. It does not transfer local SQLite
accounts/licenses or change your existing local database. Existing local users
must receive new cloud licenses and register again. If existing paid licenses
must be preserved, stop before switching clients and arrange a data migration.

## 3. Initialize the schema and owner privately

In PowerShell, in the updated source folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m server.setup_cloud
```

Paste the database URL at the hidden prompt, choose an owner username and a
12–128 character password. Hidden input shows no dots. Save the authenticator
secret and recovery codes privately. Add the secret to an authenticator app.
The command initializes tables once, creates one owner, then exits. Rerunning
it does not overwrite accounts or create a second owner. There is no public
HTTP owner-creation endpoint.

## 4. Import the GitHub repository into Vercel

Open https://vercel.com/new, select `sacredrandomacc/Sacred-Tweaks-Source` and
import it. Use the repository root (`./`), production branch `main`, and the
**Flask** framework preset. Keep the preset build/output settings; do not set
`build-windows.ps1` as a build command.

Add this environment variable for **Production**:

| Name | Value |
| --- | --- |
| `DATABASE_URL` | Your pooled Neon PostgreSQL URL with TLS enabled |

Deploy. Keep production credentials out of Preview/Development environments;
use a separate database/Neon branch if you enable previews later. A missing URL
fails closed with a JSON 503 instead of creating an ephemeral SQLite database.
Environment changes require redeployment.

The production API must accept requests without a Vercel-account login. If
Deployment Protection covers Production, configure it so the production API
is reachable by desktop clients. Keep preview deployments protected. The API
still requires its own member/owner authentication. Never distribute a Vercel
protection-bypass token in a desktop config.

## 5. Verify and connect both desktop apps

Visit `https://YOUR-PROJECT.vercel.app/v1/health`. It should return JSON with
`ok: true`. A plain `/` URL can return 404; this is an API, not a website.
503 means the environment/database/schema is unavailable. HTML or a Vercel login
page means Deployment Protection is blocking the request.

Close each desktop app. Edit the `client-config.json` beside its EXE:

```json
{
  "api_url": "https://YOUR-PROJECT.vercel.app",
  "allow_local_http": false
}
```

Use the stable Production domain, not a temporary preview URL. Do not add
`/v1` to `api_url`. Update both your Manager and your friend's member app.
Sign into Manager with the cloud owner credentials, generate a member license,
and have your friend redeem it while registering their own account. Do not
share the owner login. You can close the local backend PowerShell window after
both clients work against the hosted API.

## Operations and limits

- Database transactions use one transaction-scoped advisory lock to preserve
  the original service's single-writer behavior across Vercel instances. This
  is intended for small installations; load-test before adding many members.
- PostgreSQL stores shared rate limits, sessions, recovery use and license
  redemption. Function restarts do not reset them.
- Client leases remain 25 seconds with 10-second heartbeats. Slow or unavailable
  hosting stops tools; the client never resumes them automatically. Database
  wake-up/cold starts can exceed the current client 5-second request timeout;
  retry sign-in after the database wakes, or use an always-active database plan.
- Enable database backups/restore retention appropriate to your provider plan.
  Anyone with database credentials can access account authentication data.
- Keep the original SQLite setup until cloud login and member redemption work.
  Switching back to its URL is possible, but the two databases are independent.

## Verification

`python -m unittest discover -s tests -v` runs the local suite. Install
`requirements.txt` to include Flask tests. For PostgreSQL tests, point
`TEST_DATABASE_URL` at a disposable database named **sacred_test**. These tests
truncate the test tables; they refuse other database names. GitHub Actions
`Backend tests` provisions PostgreSQL 16 and runs both storage backends.

References:
- https://vercel.com/docs/frameworks/backend/flask
- https://vercel.com/docs/headers/request-headers
- https://neon.com/docs/guides/vercel-overview
