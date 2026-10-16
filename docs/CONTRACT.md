# Shared implementation contract

Feature IDs: single_edit, performance, measurements, themes, potato, filter_keys, owner_presets, drag, advanced, profiles, beta.
Tiers: Core, Plus, Pro, Elite (exact capitalization).

Backend `server.service.Service(db_path, **options)` exposes `handle(method, path, data=None, token=None, ip='local') -> (status:int, body:dict)` and `bootstrap_owner(username,password) -> {totp_secret,recovery_codes}`. All paths begin `/v1`. Errors are `{error: 'human-readable', code:'machine_code'}`. Payloads and returned fields use snake_case. Service accepts test clock and test password cost options; production cost must remain secure.

Public routes:
- POST /v1/license/validate {key} -> {tier,duration_days,permanent}
- POST /v1/auth/register {key,username,password,device_id} -> session plus recovery_codes
- POST /v1/auth/login {username,password,device_id,totp?,recovery_code?} -> session
- POST /v1/auth/recover {username,recovery_code?,reset_token?,new_password} -> {message}
- POST /v1/device/request {username,password,device_id,reason} -> {message}
- GET /v1/health -> {status,version}

Authorized routes:
- POST /v1/session/heartbeat {}, GET /v1/me -> session metadata without token
- POST /v1/auth/logout {}
- POST /v1/auth/recovery-codes {password} -> {recovery_codes}
- GET /v1/content -> {presets:[],announcements:[],releases:[],welcome:{}}
- POST /v1/feedback {message,diagnostics?:object}
- GET /v1/profiles -> {profiles:[]}; POST /v1/profiles {name,config}; DELETE /v1/profiles/{id}
- POST /v1/tools/authorize {feature,settings:{}} -> {settings} enforcing permissions and configured values

Session fields: token (login/register only), user:{id,username,role}, tier, permissions:{feature:boolean}, enforced:{feature:{key:value}}, expires_at (unix seconds or null), lease_seconds:25, heartbeat_seconds:10, welcome:{}. Owner role is `owner`, otherwise `member`. Owner has all permissions and permanent app authorization. HTTP token is Authorization: Bearer token.

Owner routes (server-enforced role, login requires password and TOTP or unused recovery code):
- GET /v1/admin/overview -> {users,licenses,active_sessions,alerts:[]}
- GET /v1/admin/users?q= -> {users:[]}; GET /v1/admin/users/{id} -> {user,license,sessions:[],devices:[]}
- POST /v1/admin/users/{id} {action:'rename'|'ban'|'unban'|'terminate_sessions'|'reset_device'|'reset_password', username?,reason?,until?,device_id?} -> data (reset_password returns reset_token once)
- GET /v1/admin/licenses -> {licenses:[]}; POST /v1/admin/licenses {tier,duration_days:null|number,count} -> {keys:[],licenses:[]}
- POST /v1/admin/licenses/{id} {action:'update'|'extend'|'suspend'|'resume'|'revoke'|'replace',tier?,days?,overrides?:{feature:boolean|null},enforced?:object,welcome?:object} -> data
- GET /v1/admin/transfers -> {transfers:[]}; POST /v1/admin/transfers/{id} {approve:boolean}
- GET /v1/admin/audit -> {audit:[]}
- GET /v1/admin/content -> {presets:[],announcements:[],releases:[],welcomes:[]}
- POST /v1/admin/content {kind:'preset'|'announcement'|'release'|'welcome',name,body:object,channel?:'stable'|'beta',tier?:string} -> item
- GET /v1/admin/feedback -> {feedback:[]}
- GET/POST /v1/admin/settings -> {transfer_cooldown_hours,reset_cooldown_hours}

Frontend accesses `window.pywebview.api.bootstrap()`, `.request(method,path,payload)`, `.local(action,payload)`. Each returns {ok:true,data:...} or {ok:false,error,code?}. bootstrap data: {mode:'member'|'manager',api_url,device_id,native:boolean,version}. Token never reaches frontend; bridge inserts device_id for auth and holds token privately. Frontend listens `window.addEventListener('sacred-status', e => ...)`, detail {authorized,reason,macro?,game_running?,minimized?}. It must show a reconnect/re-login view on authorization failure and preserve access to local restore actions.

Local actions: hardware, macro_status, macro_configure {kind:'single_edit'|'drag',config}, macro_enable {enabled}, emergency_stop, settings_preview {preset,target_fps}, settings_apply {plan_id}, backups, restore {backup_id}, windows_settings {page}, filter_get, filter_apply {enabled,wait_ms,delay_ms,repeat_ms,bounce_ms}, measurement_save {name,fps?,frame_time_ms?,notes?}, measurements, theme {intensity,lightweight,accent}, export_recovery {codes}. Macro config keys: activation,edit,select,confirm,emergency (key strings), step_delay_ms,repeat_ms,confirm_mode:'auto'|'manual',game_auto_confirm:boolean. Local calls must enforce session/permission snapshots and enforced values; restoration and emergency stop exempt. Bridge owns authorization, not UI.

Native module `desktop.native.NativeTools(data_dir:Path)` exposes `call(action,payload=None)` for above local actions and `set_authorization(permissions,enforced,deadline)`; `stop(reason)`; `close()`. NativeTools owns macro input loop and independent authorization watchdog. `desktop.storage.load_device_id(data_dir)` returns DPAPI-protected installation ID, errors clearly outside Windows. Root writes storage/bridge, native worker owns native.py/macros.py/settings.py and tests.

No credentials or demo data ship in production. Browser preview fixtures exist only in tests, injected through a fake pywebview API by Playwright.
