# Sacred Tweaks overlay, account, and usability design

**Date:** 2026-10-17  
**Status:** Approved in conversation; awaiting review of this written spec  
**Scope:** Member desktop application, standalone Windows companion overlay, and hosted account service

## Purpose and constraints

Improve the standalone Fortnite companion and the main Sacred Tweaks app while preserving all current main-app functionality. The overlay should expose practical, legitimate app controls and avoid looking or behaving like game-input automation. No work in this design may add game injection, memory reads, render hooks, modified Fortnite files, or anti-cheat bypasses. Do not claim Epic approval, undetectability, or ban safety.

The repository currently uses Python, pywebview/WebView2, local HTML/CSS/JS, a hosted HTTP service, and Windows DPAPI for the installation identity. Keep those architectural choices where possible. Do not discard the existing uncommitted standalone-overlay work in the working tree.

## Current state observed

- `web/overlay.html`, `web/overlay.js`, and `web/overlay.css` implement Overview, Performance, Windows, and Appearance pages in a separate topmost window.
- Performance, Measurements, and Backups & Restore are also first-class main-app views; removing the overlay's access must not remove those main-app views.
- Macro configurations and saved profiles already exist. Current macro bindings and timing can describe gameplay input automation.
- Main-app bearer tokens are held in memory. Server sessions are renewed by heartbeat and have a short lease, so persisting the current token alone will not survive a closed app.
- Usernames currently have format validation. The database has no moderation state or owner review queue. User rename is currently owner-managed.
- Appearance provides one accent color, lightweight mode, reduced motion, and an animation intensity slider.
- The standalone window depends on Windows window-management behavior. Reliable visibility over Fortnite requires Windowed Fullscreen; exclusive fullscreen is not supported reliably by ordinary topmost desktop windows.

## User-approved direction

### Overlay

Use a compact four-destination layout: Home, Macros, Windows, Appearance. Keep account identity and remaining license time in the header dropdown. Remove Performance, Measurements, and Backups & Restore from the overlay only. They remain available in the normal app.

The Macros page will list saved profile names and their saved/available status, show safe read-only summary details, and offer a button to open the corresponding section in the normal app. It will not edit bindings/timing, enable/disable macros, or send gameplay input from the overlay. Those execution-related controls remain in the normal app. This boundary reflects the user's requirement that the overlay stay practical and focused on legitimate app settings.

Add overlay appearance settings for hotkey, adjustable panel size and position, opacity, accent, and reset-to-default. Closing hides the entire window. The menu takes focus while open so controls work; closing restores focus to Fortnite. Hidden-state input pass-through and focus handling remain subject to real Windows/Fortnite acceptance testing. Windowed Fullscreen is the supported mode; explain the exclusive-fullscreen limitation in setup guidance.

### Main app usability and appearance

- Keep all existing views and functionality, including Performance, Measurements, Backups & Restore, macro configuration, and saved profiles.
- Replace the numeric animation intensity slider with an On/Off preference. Retain lightweight mode and the Windows reduced-motion respect behavior unless implementation review finds an overlap worth simplifying without losing functionality.
- Expand appearance options to a recommended charcoal/warm-white/violet palette, with user-adjustable accent and supporting surface colors, plus an obvious reset option.
- Add short usage summaries with expandable detailed instructions to feature pages and feature-level controls where the detailed sequence materially differs.
- Add quality-of-life improvements that reuse existing systems: validated saved-profile import/export and an explicit privacy-safe diagnostic log export. Do not send logs automatically.

### Account session persistence

Add an opt-in remember-session flow using a dedicated server-issued refresh credential, with expiry, rotation/reuse detection, server-side revocation, and sign-out revocation. Store the client credential only after Windows DPAPI protection; never write the bearer access token or refresh secret in plaintext. Keep the existing short-lived access lease and native authorization watchdog. If DPAPI is unavailable or cannot decrypt the value, fail closed to ordinary sign-in and provide a clear recovery message. Do not silently fall back to plaintext persistence.

The API/schema change must be backward compatible for existing users and compatible with the hosted deployment workflow. Add tests for expired, revoked, rotated/replayed refresh credentials, sign-out, restart resume, and DPAPI adapter behavior through a fake protector on non-Windows CI.

### Username moderation and recovery

Run the username policy on registration and every supported rename. Store policy version and moderation state on the server. For a policy match, do not grant a usable session; mark the account as requiring owner review and show the user a specific pending-review explanation plus a contact/recovery path. Owner review must be available in Manager with flagged username, timestamp, matched rule category (not an unnecessary reproduction of slur text), and approve/rename/reject actions with audit records.

Use a maintained, versioned prohibited-term/rule set and normalized comparisons (case folding, Unicode normalization, and conservative common obfuscation handling). Avoid claiming perfect hate-speech detection. Do not automatically block a pre-existing account merely because a future policy update introduces a new match; existing-account rescans should create a review queue for owner action. Owner approval restores access only after the username complies or an exception is explicitly documented and audited. Exact prohibited lexicon must not be exposed in public error messages.

### Usage help

Each feature gets a concise default summary and a keyboard-accessible expand/collapse control for complete steps, prerequisites, risks, and restoration/recovery instructions. Avoid duplicating the full manual in every card; link to a shared help component/content source where feasible. Help text must not promise performance gains or anti-cheat safety.

### Recommended palette

Default palette: charcoal backgrounds (#111318 and #191D25), warm white text (#F2F0EA), muted cool-gray supporting text, and restrained Sacred violet (#9A82F7) for actions/focus. Provide adjustable accent color and supporting surface tint with accessible contrast checks and reset-to-default. Maintain readable focus indication and avoid relying on color alone.

## UI sketch for implementation reference

```text
┌────────────────────────────────────────────────────────────────────┐
│ SACRED / COMPANION                  Player · Elite · 12 days left  ×│
├──────────────┬─────────────────────────────────────────────────────┤
│ ◈ Home       │  QUICK CONTROLS                                     │
│ ▤ Macros     │  Fortnite detected · Windowed Fullscreen            │
│ ⊞ Windows    │                                                     │
│ ✦ Appearance │  Saved profiles                                     │
│              │  ┌──────────────────┐  ┌──────────────────┐         │
│              │  │ Practice         │  │ Custom           │         │
│              │  │ Saved · inactive │  │ Saved · inactive │         │
│              │  │ View details     │  │ View details     │         │
│              │  └──────────────────┘  └──────────────────┘         │
│              │                                                     │
│              │  Input automation controls stay in the desktop app.│
├──────────────┴─────────────────────────────────────────────────────┤
│ External companion · F6 to close · Borderless mode recommended     │
└────────────────────────────────────────────────────────────────────┘
```

## Research-based recommendations

Official AMD and NVIDIA gaming software documents per-game settings/profiles and configurable performance metrics or real-time statistics. Sacred already has local settings previews, measurements, profile storage, and Windows settings shortcuts. The recommended safe gap-fills are validated profile import/export, a privacy-safe user-initiated diagnostics export, and clearer contextual feature help. Do not add driver tuning, automatic overclocking, game capture, filters, input macros, or automatic game-file edits as part of this work; those are outside this app's safe current purpose and platform support.

References reviewed:

- AMD application profiles: https://www.amd.com/en/resources/support-articles/faqs/DH3-012.html
- AMD performance monitoring: https://www.amd.com/en/resources/support-articles/faqs/DH3-038.html
- NVIDIA app features: https://www.nvidia.com/en-us/geforce/news/gfecnt/202410/nvidia-app-beta-update-g-sync-controls-rtx-hdr-multi-monitor/

## Platform and delivery limitations

- Ordinary topmost desktop windows cannot reliably appear over exclusive fullscreen. Windowed Fullscreen is required for the supported Fortnite setup.
- While the overlay is open, it must take foreground focus for text fields and direct interaction; hotkey changes cannot prevent conflicts with Fortnite bindings. The hotkey is configurable and should be selected to avoid conflicts.
- Desktop-only Linux CI can test controllers and web UI but cannot certify Windows DPAPI, WebView2, window activation, game focus, DPI scaling, display changes, or Fortnite restart behavior. These need a Windows acceptance checklist and user-PC verification.
- Username language moderation is imperfect and culturally/contextually ambiguous. It must provide a human review path and be audited.
- Refresh-token persistence increases credential sensitivity. DPAPI protects at rest for the current Windows profile but is not protection against malware running as that user or a modified client.

## Acceptance criteria

1. Overlay navigation includes Home, Macros, Windows, Appearance only. Performance, Measurements, and Backups & Restore are absent there and remain reachable in the main app.
2. Overlay Macros lists saved profiles and safe read-only summaries; no gameplay input automation can be configured or started from the overlay.
3. Overlay hotkey, size, position, opacity, accent, and reset settings persist and validate; hidden overlay owns no visible or interactive window area; open/close focus behavior is covered by controller tests.
4. Main app appearance uses a boolean animation setting and adjustable palette; all existing main app views remain reachable.
5. Feature help summaries are visible by default and detailed instructions can be expanded with keyboard and pointer.
6. Remember-me renewal credentials are DPAPI-protected locally, hashed/rotated/revocable on the server, and never exposed to frontend JavaScript or logs.
7. Username checks cover registration and changes. Flagged accounts receive no usable session and see review guidance; owner review actions are authorized and audited.
8. Profile import/export rejects malformed, unsupported, oversized, or executable payloads and never enables automation as a side effect.
9. Diagnostic export contains only explicitly documented operational/app data, excludes tokens/passwords/recovery codes, and is user initiated.
10. Automated tests cover service, bridge, UI, import/export, and overlay lifecycle. A separate Windows acceptance checklist records tests not runnable in CI.

## Out of scope

- Game Bar dependency or registration.
- Fortnite injection, memory reads, render hooks, anti-cheat bypass, game file modification, aim/build automation, or claims of ban safety.
- Automatic driver installation, GPU overclocking, or live FPS capture from Fortnite.
- Silent telemetry or background log upload.
