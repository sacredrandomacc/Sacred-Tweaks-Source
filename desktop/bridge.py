# Copyright (c) 2026 Sacred LLC. All rights reserved. See LICENSE.
"""Authenticated desktop boundary. The renderer never receives bearer tokens."""
import json
import os
import re
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from desktop.storage import atomic_json, load_device_id

VERSION = "0.1.0"


class ApiError(Exception):
    def __init__(self, message, code="request_failed", status=0):
        super().__init__(message)
        self.code, self.status = code, status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ApiError("The service redirected the request. Check the configured API URL.", "redirect_blocked")


def validate_api_url(url, allow_http=False):
    parsed = urllib.parse.urlsplit(url)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (allow_http and local and parsed.scheme == "http"):
        raise ValueError("An HTTPS API URL is required. HTTP is allowed only for explicitly enabled local development.")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("API URL must be an origin, such as https://api.example.com, without credentials or a path.")
    return url.rstrip("/")


class Api:
    def __init__(self, mode, data_dir, api_url, native, *, device_id=None, allow_http=False, transport=None, clock=time.monotonic):
        self._mode = mode
        self._data_dir = Path(data_dir)
        self._api_url = validate_api_url(api_url, allow_http)
        self._native = native
        self._device_id = device_id if device_id is not None else load_device_id(self._data_dir)
        self._token = None
        self._session = None
        self._deadline = 0
        self._generation = 0
        self._lock = threading.RLock()
        self._auth_lock = threading.Lock()
        self._clock = clock
        self._shutdown = threading.Event()
        self._window = None
        self._transport = transport or self._http
        self._thread = None
        self._overlay = None

    def bootstrap(self):
        preferences = {}
        try:
            theme = json.loads((self._data_dir / "theme.json").read_text("utf-8"))
            if (type(theme.get("intensity")) in {int, float} and 0 <= theme["intensity"] <= 1
                    and type(theme.get("lightweight")) is bool
                    and isinstance(theme.get("accent"), str) and re.fullmatch(r"#[A-Fa-f0-9]{6}", theme["accent"])):
                preferences["theme"] = {k: theme[k] for k in ("intensity", "lightweight", "accent")}
                preferences["reduced_motion"] = theme.get("reduced_motion") is True
        except (OSError, ValueError, AttributeError):
            pass
        return {"ok": True, "data": {"mode": self._mode, "api_url": self._api_url, "device_id": self._device_id, "native": os.name == "nt", "version": VERSION, **preferences}}

    def _attach(self, window):
        self._window = window
        if self._thread is None:
            self._thread = threading.Thread(target=self._heartbeat, name="authorization", daemon=True)
            self._thread.start()

    def _emit(self, value):
        if self._window:
            try:
                self._window.evaluate_js("window.dispatchEvent(new CustomEvent('sacred-status',{detail:" + json.dumps(value) + "}))")
            except Exception:
                pass  # A closing/not-yet-loaded renderer cannot prolong authorization.

    def _http(self, method, path, data, token):
        if not isinstance(path, str) or not path.startswith("/v1/") or any(c in path for c in "\r\n\\#"):
            raise ApiError("Invalid API path.")
        body = None if method == "GET" else json.dumps(data or {}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(self._api_url + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=5) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise ApiError("Service response is too large.")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            try:
                error = json.loads(exc.read(65536))
            except Exception:
                error = {}
            raise ApiError(error.get("error", f"Service returned HTTP {exc.code}."), error.get("code", "request_failed"), exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ApiError("Cannot reach the licensing service. Tools have stopped; check your connection and sign in again.", "disconnected") from exc

    def _clear(self, reason, expected_generation=None):
        with self._lock:
            if expected_generation is not None and expected_generation != self._generation:
                return
            self._generation += 1
            if self._overlay:
                self._overlay.revoke()
            self._token = self._session = None
            self._deadline = 0
            self._native.stop(reason)
            self._native.set_authorization({}, {}, 0)
            self._emit({"authorized": False, "reason": reason})

    def _accept(self, session):
        if self._mode == "manager" and session.get("user", {}).get("role") != "owner":
            try:
                self._transport("POST", "/v1/auth/logout", {}, session.get("token"))
            finally:
                raise ApiError("Manager requires an owner account.", "owner_required", 403)
        token = session.get("token")
        if not token:
            raise ApiError("The service did not return a session token.")
        safe = {k: v for k, v in session.items() if k != "token"}
        with self._lock:
            self._generation += 1
            self._token, self._session = token, safe
            self._deadline = self._clock() + min(25, max(0, float(session.get("lease_seconds", 25))))
            self._native.stop("login")
            self._native.set_authorization(safe.get("permissions", {}), safe.get("enforced", {}), self._deadline)
        self._emit({"authorized": True, "reason": "signed_in"})
        return safe

    def request(self, method, path, payload=None):
        with self._lock:
            request_generation = self._generation
        try:
            if method not in {"GET", "POST", "DELETE"} or not isinstance(path, str) or not path.startswith("/v1/"):
                raise ApiError("Invalid API request.")
            parsed = urllib.parse.urlsplit(path)
            # Reject alternate spellings before classifying sensitive routes.
            if (parsed.scheme or parsed.netloc or parsed.fragment or parsed.path.endswith("/")
                    or any(ord(c) < 32 or ord(c) == 127 for c in path)
                    or any(c in path for c in "\\\r\n#") or "%" in parsed.path or "//" in parsed.path
                    or any(part in {".", ".."} for part in parsed.path.split("/"))
                    or ("?" in path and not (method == "GET" and parsed.path == "/v1/admin/users"))):
                raise ApiError("Use the canonical API path.")
            data = dict(payload or {})
            auth = path in {"/v1/auth/login", "/v1/auth/register"}
            if auth:
                if method != "POST":
                    raise ApiError("Authentication requires POST.")
                if not self._auth_lock.acquire(blocking=False):
                    raise ApiError("Another sign-in request is still running.", "busy")
                try:
                    with self._lock:
                        epoch = self._generation
                    data["device_id"] = self._device_id
                    started = self._clock()
                    result = self._transport(method, path, data, None)
                    result["lease_seconds"] = max(0, float(result.get("lease_seconds", 25)) - (self._clock() - started))
                    with self._lock:
                        if epoch != self._generation:
                            try:
                                self._transport("POST", "/v1/auth/logout", {}, result.get("token"))
                            finally:
                                raise ApiError("Sign-in was cancelled.", "cancelled")
                        result = self._accept(result)
                finally:
                    self._auth_lock.release()
            else:
                if path == "/v1/device/request":
                    data["device_id"] = self._device_id
                with self._lock:
                    token, request_generation = self._token, self._generation
                if path == "/v1/auth/logout":
                    self._clear("Signed out", request_generation)
                result = self._transport(method, path, data, token)
            return {"ok": True, "data": result}
        except ApiError as exc:
            if path not in {"/v1/auth/login", "/v1/auth/register", "/v1/auth/recover", "/v1/license/validate", "/v1/device/request"}:
                if exc.status == 401 or exc.code in {"disconnected", "expired", "revoked", "banned", "suspended", "session_expired", "session_revoked", "license_expired", "license_inactive"}:
                    self._clear(str(exc), request_generation)
            return {"ok": False, "error": str(exc), "code": exc.code}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:300], "code": "client_error"}

    def _renew_once(self):
        with self._lock:
            token, epoch = self._token, self._generation
        if not token:
            return
        try:
            started = self._clock()
            result = self._transport("POST", "/v1/session/heartbeat", {}, token)
            with self._lock:
                if epoch != self._generation or token != self._token:
                    return
                # Snapshot is deliberately retained until a new login.
                self._deadline = started + min(25, max(0, float(result.get("lease_seconds", 25))))
                self._native.set_authorization(self._session.get("permissions", {}), self._session.get("enforced", {}), self._deadline)
        except Exception as exc:
            self._clear(str(exc) or "Authorization could not be renewed", epoch)

    def _heartbeat(self):
        next_heartbeat = self._clock() + 10
        previous_status = None
        while not self._shutdown.wait(0.5):
            now = self._clock()
            with self._lock:
                expired = bool(self._token and now >= self._deadline)
                epoch = self._generation
            if expired:
                self._clear("Authorization window expired. Sign in to reconnect.", epoch)
            if now >= next_heartbeat:
                self._renew_once()
                next_heartbeat = self._clock() + 10
            try:
                status = self._native.call("macro_status", {})
                if status != previous_status:
                    self._emit({"game_running": status.get("game_running", False), "macro": status})
                    previous_status = status
            except Exception:
                pass

    def local(self, action, payload=None):
        try:
            payload = dict(payload or {})
            if action == "export_recovery":
                codes = payload.get("codes", [])
                if not isinstance(codes, list) or not codes or any(not isinstance(c, str) or len(c) > 200 for c in codes):
                    raise ValueError("Invalid recovery codes.")
                if not self._window:
                    raise ValueError("The desktop window is unavailable.")
                import webview
                target = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename="Sacred-Recovery-Codes.txt", file_types=("Text files (*.txt)",))
                if not target:
                    return {"ok": True, "data": {"cancelled": True}}
                filename = target[0] if isinstance(target, (list, tuple)) else target
                Path(filename).write_text("Sacred Tweaks recovery codes\nKeep private. Each code can be used once.\n\n" + "\n".join(codes), encoding="utf-8")
                return {"ok": True, "data": {"saved": True}}
            if action not in {"backups", "restore", "emergency_stop", "macro_status", "hardware"}:
                with self._lock:
                    if not self._token or self._clock() >= self._deadline:
                        raise ApiError("Sign in to use this tool.", "unauthorized", 401)
            if action == 'overlay_pair':
                from desktop.overlay import OverlayServer
                with self._lock:
                    if self._overlay is None:
                        self._overlay = OverlayServer(self, authorization_lock=self._lock)
                    return {'ok':True,'data':self._overlay.pair()}
            result = self._native.call(action, payload)
            return {"ok": True, "data": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:500], "code": getattr(exc, "code", "local_error")}

    def _close(self):
        with self._lock:
            token = self._token
        if self._overlay:
            self._overlay.close()
        self._shutdown.set()
        self._clear("Application closed")
        self._native.close()
        if token:
            try:
                self._transport("POST", "/v1/auth/logout", {}, token)
            except Exception:
                pass
