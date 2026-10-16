# Hosting and release guide

## Supported deployment

Use one Linux VM with Python 3.12 or Docker Compose, a persistent local disk, and Caddy for HTTPS. The service is intended for a small private group. Allow at least 2 GiB of RAM for the example deployment: each concurrent production scrypt operation needs about 128 MiB and the HTTP service admits up to eight workers; measure your real load before sizing down. It is not a multi-region/high-availability platform. SQLite must stay on local persistent storage, not a network filesystem, and one application service instance is the supported deployment. The Python HTTP listener must not be exposed directly to the public Internet; expose only Caddy ports 80/443.

1. Point a domain's A/AAAA records at your server.
2. Copy `.env.example` to `.env`; set `SACRED_DOMAIN` to that hostname.
3. Run `docker compose build` and `docker compose up -d`.
4. Run `docker compose exec api python -m server --db /data/sacred.db --bootstrap-owner owner` interactively. Keep the authenticator seed/recovery codes private. Bootstrap refuses a second owner.
5. Verify `https://YOUR-DOMAIN/v1/health` and sign in through Manager with MFA.
6. Put `{"api_url":"https://YOUR-DOMAIN","allow_local_http":false}` in `client-config.json` beside each distributed executable.

Caddy obtains and renews a TLS certificate when DNS and ports are correct. Its reverse proxy is the only public route. Compose assigns Caddy `172.30.90.3` on a dedicated network and the backend trusts forwarded client addresses only from that exact peer. If this subnet conflicts with your host, change the Compose network and trusted-proxy address together. This example assumes direct clients, without a CDN/upstream proxy. Do not broadly trust client-supplied forwarding headers. See the backend report for its implemented limiter policy.

## Persistence, secrets, and backups

The `sacred-data` Docker volume holds the database, including the server-only owner TOTP seed and password verification data. The volume is never mounted into either desktop app. Restrict host access and use encrypted disks/snapshots. Back up through SQLite's backup API (or stop the API before copying the database); copying only the main file during WAL activity can lose transactions. Keep encrypted backups off the VM and test a restore before real membership use. Never commit the database, `.env`, setup output, or generated license keys.

An owner recovery code is sensitive. Reset credentials and new license keys are shown only when generated. Audit logs deliberately omit full keys/passwords/tokens. Prefer OS-level access controls and encrypted backups for the database; this implementation is not a substitute for a managed secrets vault.

## Authorization timing

Clients renew every 10 seconds. Their monotonic authorization deadline is at most 25 seconds after a successful authorization request begins. Native tools independently enforce this deadline. Network failures stop tools as soon as observed. Service checks current ban, suspension, revocation and expiration on authorized requests; permission/tier snapshots change at login. A stalled or unavailable client may retain authorization until its window expires. Reconnection does not start macros. System shutdown/power loss cannot guarantee a final Windows input API call; the normal shutdown and stop paths explicitly release owned synthetic inputs.

## Costs and services

No paid authentication, email, telemetry, or payment service is required. Python, SQLite, Caddy, WebView2, and the build tools do not require a software subscription. A public deployment requires a server with persistent storage and a domain (or an existing suitable hostname). Budget roughly US$5–15/month for a small VM plus domain registration and backups; this is a planning estimate, not a current provider quote. Code signing has a separate provider-dependent cost if you choose to obtain a certificate. GitHub Actions use may count against your account's included minutes/storage. No hosting purchase or deployment has been made.

## Release steps

Build on clean 64-bit Windows, complete `WINDOWS-ACCEPTANCE.md`, review dependency updates, run both packages as a standard Windows user, and test on a second machine. The apps do not require blanket administrator privileges. Sign binaries only with a certificate you control; signing does not guarantee antivirus reputation or game compatibility. Publish packages and SHA-256 checksums at a trusted HTTPS location, then add the release entry in Manager. Release metadata and HTTPS package links with optional SHA-256 checksums are published through Manager. Members copy the link from Account → Download details and install manually; this build does not silently download and execute software updates.
