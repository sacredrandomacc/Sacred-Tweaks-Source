# Comparable-tool review and follow-up ideas

## Useful additions implemented in this update

- Validated profile import/export adds the portability commonly expected from tools that support saved configurations. Import is bounded, rejects unknown or unsafe fields, asks for confirmation, and never enables a macro.
- User-initiated diagnostics export adds a support path without serializing credentials or arbitrary user content.
- The overlay gains size and position controls, quick Windows shortcuts, appearance settings, and saved profile editing while leaving activation in the main app.

## Suggestions for review

1. **Per-game workspaces:** let users associate saved Sacred profiles with a game detected by process/window title, then offer a manual apply prompt. Keep switching opt-in and require the game to be closed before changing config files. Many gaming utilities offer per-game optimization or profiles, and this would fit the existing Windows settings/profile model without driver hooks.
2. **Repeatable before/after test sessions:** add named test runs to the existing manual measurements so players can compare the same map, route, and settings over time. Keep user-entered FPS/frame-time clearly labeled and system readings separate; do not claim performance causality.
3. **Windows maintenance shortcuts:** add documented, read-only status and deep links for Windows Update, startup apps, and Storage Sense. Windows PC Manager and Microsoft Support already point users to these controls; Sacred should open native Settings pages rather than silently changing startup services or deleting files.
4. **Driver and game settings checklist:** show the installed display-adapter/driver version and link to the GPU vendor's official update page. Do not download or install drivers automatically.

The update does not add GPU overclocking, fan curves, process injection, memory editing, or anti-cheat bypass. Those areas need privileged/vendor-specific code or create unnecessary integrity and support risks for a Windows settings companion.

## Sources reviewed

- [MSI Afterburner guide](https://www.msi.com/support/technical_details/VGA_MSI_Utility_AfterBurner) — saved profiles and in-game monitoring via a separate overlay service.
- [NVIDIA App in-game performance overlay](https://nvidia.custhelp.com/app/answers/detail/a_id/5084/kw/overlay) — a configurable in-game performance/latency overlay.
- [Microsoft PC Manager](https://pcmanager.microsoft.com/en-us/) and [Windows PC Health Check guidance](https://support.microsoft.com/en-us/windows/experience/compatibility/how-to-use-the-pc-health-check-app) — health checks, storage, update status, and startup-app settings.
