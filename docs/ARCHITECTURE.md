# Sacred Tweaks implementation

The supplied SPECIFICATION.md is the approved product brief. Work proceeds without additional design approval, as requested in that brief.

Python 3.12+, stdlib SQLite/HTTP service, scrypt passwords, opaque hashed session tokens, and WebView2 through pywebview. Member and Manager have separate launchers and executable packages. Server authorization never depends on the launcher. The frontend is local HTML/CSS/JavaScript without a bundler. Windows integration uses documented ctypes APIs and conservative settings edits. Caddy terminates HTTPS in deployment. One backend process with a persistent local SQLite volume is the supported topology.

Sessions renew every 10 seconds and locally expire after 25 seconds without a successful response. Native tools check a monotonic deadline, independently of the interface. A failure stops inputs immediately when observed; reconnection never re-enables tools. Permission snapshots are fixed at login. Bans, revocation, suspension, and expiration are checked on every authorized server request.

Device registration uses a random installation identity protected with Windows DPAPI, not a hardware fingerprint or IP ban. Password and device proof authorize a login; an active competing session is rejected, rather than silently replaced. Owner recovery/transfer is the escape hatch. A copied unlocked Windows profile and modified executables remain outside guarantees.

Validation boundaries: HTTP API integration tests, macro state-machine tests with a fake input sink, settings tests against temporary files, and browser UI checks. Native Windows hooks, WebView2 startup, packaging, real Fortnite behavior, and live TLS hosting require a Windows/hosting environment and are reported separately.
