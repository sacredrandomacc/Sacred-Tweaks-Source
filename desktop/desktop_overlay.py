# Copyright (c) 2026 Sacred LLC. All rights reserved. See LICENSE.
"""A separate Windows companion window; no game rendering or process access."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import threading
import time

from .settings import atomic_json

# F8 belongs to the desktop app's emergency stop control.
HOTKEYS = {'TAB': 0x09, **{f'F{n}': 0x6F + n for n in (6, 7, 9, 10, 11)}}
ACCENTS = {'violet', 'blue', 'amber'}
DEFAULTS = {'hotkey': 'TAB', 'accent': 'violet', 'opacity': 94, 'reduced_motion': False}


def valid_preferences(values):
    if not isinstance(values, dict):
        raise ValueError('Invalid overlay preferences.')
    result = dict(DEFAULTS)
    result.update(values)
    if (result['hotkey'] not in HOTKEYS or result['accent'] not in ACCENTS
            or type(result['opacity']) is not int or not 75 <= result['opacity'] <= 100
            or type(result['reduced_motion']) is not bool):
        raise ValueError('Invalid overlay preference value.')
    return {key: result[key] for key in DEFAULTS}


class OverlayBridge:
    """Only account display, appearance, and supported read-only settings are exposed."""
    def __init__(self, api, data_dir):
        # pywebview recursively walks public bridge attributes. Keep object
        # references private so it cannot traverse the native engine/window.
        self._api = api
        self._path = Path(data_dir) / 'overlay-preferences.json'
        try:
            self._values = valid_preferences(json.loads(self._path.read_text('utf-8')))
        except (OSError, ValueError, TypeError, KeyError):
            self._values = dict(DEFAULTS)
        self._controller = None

    def preferences(self):
        return dict(self._values)

    def save_preferences(self, values):
        chosen = valid_preferences(values)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(self._path, chosen)
        self._values = chosen
        return self.preferences()

    def snapshot(self):
        with self._api._lock:
            session = self._api._session
            active = bool(session and self._api._token and self._api._clock() < self._api._deadline)
            if not active:
                return {'signed_in': False, 'username': '', 'tier': '', 'license': None, 'permissions': {}}
            return {'signed_in': True, 'username': session.get('user', {}).get('username', ''),
                    'tier': session.get('tier', ''), 'license': {
                        'expires_at': session.get('expires_at'),
                        'permanent': session.get('expires_at') is None},
                    'permissions': {'performance': session.get('permissions', {}).get('performance') is True}}

    def preview_performance(self, preset, target_fps):
        if preset not in ('performance', 'balanced') or type(target_fps) is not int or not 30 <= target_fps <= 1000:
            raise ValueError('Choose a supported preset and frame-rate target.')
        response = self._api.local('settings_preview', {'preset': preset, 'target_fps': target_fps})
        if not response['ok']:
            raise ValueError(response['error'])
        plan = response['data']
        return {'preset': plan.get('preset'), 'target_fps': plan.get('target_fps'),
                'changes': plan.get('changes', []), 'tradeoffs': plan.get('tradeoffs', []),
                'restart_required': plan.get('restart_required', False)}

    def open_windows_settings(self, page):
        if page not in ('game_mode', 'capture', 'graphics', 'display'):
            raise ValueError('Unknown settings page.')
        response = self._api.local('windows_settings', {'page': page})
        if not response['ok']:
            raise ValueError(response['error'])
        return response['data']

    def close_menu(self):
        if self._controller:
            self._controller.hide(restore=True)
        return True

    def open_desktop(self):
        if self._controller:
            self._controller.hide(restore=False)
            self._controller.show_desktop()
        return True


class WindowsOverlayProbe:
    """Documented desktop window/input state only; never opens the game process."""
    class RECT(ctypes.Structure):
        _fields_ = [('left', wintypes.LONG), ('top', wintypes.LONG),
                    ('right', wintypes.LONG), ('bottom', wintypes.LONG)]

    def __init__(self, platform):
        self.platform = platform
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        u = self.user32
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetAsyncKeyState.argtypes = [ctypes.c_int]
        u.GetAsyncKeyState.restype = ctypes.c_short
        u.IsWindow.argtypes = [wintypes.HWND]
        u.IsWindow.restype = wintypes.BOOL
        u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(self.RECT)]
        u.GetWindowRect.restype = wintypes.BOOL
        u.SetForegroundWindow.argtypes = [wintypes.HWND]
        u.SetForegroundWindow.restype = wintypes.BOOL
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        u.SetWindowPos.restype = wintypes.BOOL

    def foreground(self):
        return self.user32.GetForegroundWindow()

    def is_game(self):
        return self.platform.foreground()

    def down(self, hotkey):
        return bool(self.user32.GetAsyncKeyState(HOTKEYS[hotkey]) & 0x8000)

    def exists(self, hwnd):
        return bool(hwnd and self.user32.IsWindow(hwnd))

    def bounds(self, hwnd):
        rect = self.RECT()
        return (rect.left, rect.top, rect.right, rect.bottom) if self.user32.GetWindowRect(hwnd, ctypes.byref(rect)) else None

    def center(self, window_hwnd, game_hwnd):
        game, overlay = self.bounds(game_hwnd), self.bounds(window_hwnd)
        if game and overlay:
            x = (game[0] + game[2] - (overlay[2] - overlay[0])) // 2
            y = (game[1] + game[3] - (overlay[3] - overlay[1])) // 2
            self.user32.SetWindowPos(window_hwnd, None, x, y, 0, 0, 0x0015)  # No resize, z-order or activation.

    def focus(self, hwnd):
        return bool(self.user32.SetForegroundWindow(hwnd))


class DesktopOverlayController:
    """Polls only while the member app runs; hidden windows own no input area."""
    def __init__(self, window, desktop, bridge, probe):
        self.window, self.desktop, self.bridge, self.probe = window, desktop, bridge, probe
        bridge._controller = self
        self.stop_event = threading.Event()
        self.thread = None
        self.open = False
        self.game_hwnd = None
        self.overlay_hwnd = None
        self.last_bounds = None
        self.was_down = False
        self.last_key = None
        self.lock = threading.RLock()

    def start(self):
        if self.thread:
            return
        self.overlay_hwnd = int(self.window.native.Handle.ToInt64())
        self.thread = threading.Thread(target=self._run, name='Sacred-window-overlay', daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stop_event.wait(.035 if self.open or self.game_hwnd else .18):
            try:
                self.tick()
            except Exception:
                self.hide(restore=False)

    def tick(self):
        with self.lock:
            current = self.probe.foreground()
            game_active = bool(current and current != self.overlay_hwnd and self.probe.is_game())
            if game_active:
                self.game_hwnd = current
            if self.game_hwnd and not self.probe.exists(self.game_hwnd):
                self.game_hwnd = None
                self.hide(restore=False)
            if self.open and current not in (self.game_hwnd, self.overlay_hwnd):
                self.hide(restore=False)  # Alt-Tab or another application took focus.
            if not self.open and not game_active:
                self.game_hwnd = None
            key = self.bridge._values['hotkey']
            if key != self.last_key:
                self.was_down = False
                self.last_key = key
            down = self.probe.down(key) if (game_active or self.open) else False
            if down and not self.was_down:
                if self.open:
                    self.hide(restore=True)
                elif game_active:
                    self.show()
            self.was_down = down
            if self.open and self.game_hwnd and self.probe.exists(self.game_hwnd):
                bounds = self.probe.bounds(self.game_hwnd)
                if bounds != self.last_bounds:
                    self.probe.center(self.overlay_hwnd, self.game_hwnd)
                    self.last_bounds = bounds

    def show(self):
        if self.open or not self.game_hwnd:
            return
        self.window.show()
        self.probe.center(self.overlay_hwnd, self.game_hwnd)
        self.last_bounds = self.probe.bounds(self.game_hwnd)
        self.probe.focus(self.overlay_hwnd)
        self.open = True
        # Account and lease data may have changed since this hidden page loaded.
        self.window.evaluate_js("document.body.classList.remove('closing'); document.body.classList.remove('opening'); "
                                "void document.body.offsetWidth; document.body.classList.add('opening'); "
                                "window.SacredOverlay && window.SacredOverlay.refresh()")

    def hide(self, restore=False):
        with self.lock:
            if not self.open:
                return
            if restore and not self.bridge._values['reduced_motion']:
                self.window.evaluate_js("document.body.classList.remove('opening'); document.body.classList.add('closing')")
                time.sleep(.12)
            self.window.hide()
            self.open = False
            if restore and self.probe.exists(self.game_hwnd):
                self.probe.focus(self.game_hwnd)

    def show_desktop(self):
        self.desktop.show()
        hwnd = int(self.desktop.native.Handle.ToInt64())
        self.probe.focus(hwnd)

    def close(self):
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)
