# Work ledger

2026-10-15: Supplied specification accepted as design authority. Implementation choices are authorized by the brief. New isolated development repository; source not linked to an external git service.

Environment: Linux; Python and Node available; Windows compiler/runtime unavailable. Native execution, Windows packaging, signing and live hosted deployment are external validation gates.

Architecture and API contract recorded. Component implementation begins.

Implementation completed as a Windows validation candidate: service, member and Manager interfaces, native tool boundary, deployment configuration and Windows build scripts. The native implementations use real Windows APIs; test platforms are confined to tests.

Review corrections: reject alternate authentication URLs; preserve newer sessions when old requests fail; bind settings commits to the current authorization snapshot; keep emergency input release independent of disk writes; expose restore before sign-in; use fresh sign-in after connection loss; reflect native macro stop status; display available CPU/RAM records; load appearance preferences on startup. Follow-up inspection caught the empty-query URL variant and a watchdog lock regression, both corrected with regression coverage.

83 Python tests pass. Real local HTTP integration and a production-cost scrypt owner login passed. Browser scenarios pass for Core, Plus, Pro, Elite and Manager; major screens and dialogs inspected. Detailed record is in VERIFICATION.md. Windows execution, executable production, live deployment, installed game-version certification, signing and on-device animation resource measurement remain outstanding. REQUIREMENTS.md tracks these boundaries explicitly.
