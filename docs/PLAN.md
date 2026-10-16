# Sacred Tweaks Implementation Plan

> For agentic workers: use subagent-driven-development with independent component owners and explicit contracts.

Goal: functional private-group member/owner applications with a deployable licensing service.
Spec: SPECIFICATION.md. Architecture: ARCHITECTURE.md. Interfaces: CONTRACT.md.

Global constraints: exact tiers and lock text from spec; modern password hashes; no privileged client secrets; no bypass/injection; backups remain usable offline; permissions change at next login; all inputs stop on lost authorization. Source and build scripts are deliverable here; Windows binaries and live deployment must be labeled unverified until actually built/deployed.

Review focus: concurrent redemption; owner authorization; stale heartbeat replies after logout; held input release across cancellation; restoring only settings the app still owns.

- [x] Backend: schema, transactions, accounts, MFA/recovery, leases, overrides, admin/content APIs. Test public Service.handle boundary, concurrency, replay and authorization before marking complete.
- [x] Native source (Windows validation pending): cancellable macro engine, documented Windows hooks/SendInput, foreground/deadline watchdog, conservative config preview/backups/restore, Filter Keys and hardware. Test state machine and temporary settings boundaries.
- [x] UI: polished responsive member/manager screens, all API-backed controls, welcome and locks, error states. Browser inspect main screens with test-only fixtures.
- [x] Integration: bridge keeps tokens private, renews leases, checks permissions/enforcement, packages separate launchers. Exercise real HTTP registration/login/authorization and frontend integration.
- [x] Source delivery: Docker/Caddy, secure bootstrap, Windows builds/CI, owner guide, requirement checklist, test results, limitations. Review code, fix actionable findings, archive complete source.

- [ ] External release gate: build and run both Windows bundles, verify installed Fortnite version and real native behavior, deploy HTTPS service, perform host backup recovery, and sign/distribute only after acceptance.
