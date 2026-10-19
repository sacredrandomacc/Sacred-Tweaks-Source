# Copyright (c) 2026 Sacred LLC. All rights reserved. See LICENSE.
"""A separate Windows companion window; no game rendering or process access."""
import ctypes
from ctypes import wintypes
import json
import re
from pathlib import Path
import threading
import time

from .settings import atomic_json

# F8 belongs to the desktop app's emergency stop control.
HOTKEYS = {'TAB': 0x09, **{f'F{n}': 0x6F + n for n in (6, 7, 9, 10, 11)}}
# 'app' follows the main app's theme; other values are web/themes.js ids or legacy accents.
ACCENT_PATTERN = re.compile(r'[a-z0-9-]{1,32}')
DEFAULTS = {'hotkey': 'TAB', 'accent': 'app', 'opacity': 94, 'reduced_motion': False,
            'size': 'wide', 'position': 'center', 'glass': False, 'sounds': True, 'particles': 'none', 'widgets': False}
PARTICLES = {'none', 'stardust', 'fireflies', 'snow', 'embers', 'bubbles', 'constellation', 'sakura', 'rain', 'bats', 'waves', 'starfield', 'aurora', 'grid'}
WINDOW_SIZES = {'wide': (1200, 740)}


def layout_rect(bounds, size, position):
    if not isinstance(bounds, (tuple, list)) or len(bounds) != 4:
        return None
    left, top, right, bottom = (int(value) for value in bounds)
    area_w, area_h = max(1, right - left), max(1, bottom - top)
    requested_w, requested_h = WINDOW_SIZES[size]
    width, height = min(requested_w, max(1, area_w - 64)), min(requested_h, max(1, area_h - 64))
    margin_x, margin_y = min(32, max(0, (area_w - width) // 2)), min(32, max(0, (area_h - height) // 2))
    x = left + margin_x if position == 'left' else right - width - margin_x if position == 'right' else left + (area_w - width) // 2
    y = top + (area_h - height) // 2
    return x, y, x + width, y + height


def valid_preferences(values):
    if not isinstance(values, dict):
        raise ValueError('Invalid overlay preferences.')
    result = dict(DEFAULTS)
    result.update(values)
    # Existing installations may still have one of the removed sizes saved.
    if result['size'] in ('compact', 'standard'):
        result['size'] = 'wide'
    if (result['hotkey'] not in HOTKEYS or not isinstance(result['accent'], str)
            or not ACCENT_PATTERN.fullmatch(result['accent'])
            or type(result['glass']) is not bool or type(result['sounds']) is not bool
            or result['particles'] not in PARTICLES or type(result['widgets']) is not bool
            or type(result['opacity']) is not int or not 75 <= result['opacity'] <= 100
            or type(result['reduced_motion']) is not bool
            or result['size'] not in WINDOW_SIZES or result['position'] not in {'center', 'left', 'right'}):
        raise ValueError('Invalid overlay preference value.')
    return {key: result[key] for key in DEFAULTS}


class OverlayBridge:
    """Expose account display, saved profile editing, and companion preferences."""
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
        self._timer = {'running': False, 'elapsed_ms': 0, 'started_at': None}

    def set_timer(self, running, elapsed_ms):
        """The companion's session timer, mirrored for the widget bar."""
        if type(running) is not bool or not isinstance(elapsed_ms, (int, float)) or not 0 <= elapsed_ms <= 864e5:
            raise ValueError('Invalid timer state.')
        self._timer = {'running': running, 'elapsed_ms': int(elapsed_ms), 'started_at': time.time() if running else None}
        return True

    def widget_state(self):
        timer = dict(self._timer)
        if timer['running'] and timer['started_at']:
            timer['elapsed_ms'] += int((time.time() - timer['started_at']) * 1000)
        try:
            macros = self.macro_status().get('macros', {})
            enabled = sum(1 for m in macros.values() if isinstance(m, dict) and m.get('enabled'))
        except (PermissionError, ValueError):
            enabled = None
        return {'timer': timer, 'enabled': enabled, 'theme': self.app_theme(), 'accent': self._values['accent']}

    def preferences(self):
        return dict(self._values)

    def save_preferences(self, values):
        chosen = valid_preferences(values)
        try:
            macros = self.macro_status().get('macros', {})
        except PermissionError:
            macros = {}
        if any(isinstance(macro, dict) and macro.get('config', {}).get('toggle') == chosen['hotkey']
               for macro in macros.values()):
            raise ValueError('The overlay hotkey conflicts with a macro toggle. Choose another key.')
        self._path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(self._path, chosen)
        self._values = chosen
        if self._controller:
            self._controller.apply_layout()
        return self.preferences()

    def app_theme(self):
        """The main app's saved palette, validated, so the companion can match it."""
        try:
            theme = json.loads((self._path.parent / 'theme.json').read_text('utf-8'))
        except (OSError, ValueError):
            return None
        if not isinstance(theme, dict):
            return None
        colors = {key: theme.get(key) for key in ('accent', 'surface', 'text_color', 'muted_color')}
        if not all(isinstance(v, str) and re.fullmatch('#[0-9A-Fa-f]{6}', v) for v in colors.values()):
            return None
        font = theme.get('font')
        return {**colors, 'glass': theme.get('glass') is True, 'preset': theme.get('preset') if isinstance(theme.get('preset'), str) else 'custom',
                'font': font if isinstance(font, str) and re.fullmatch('[a-z]{1,20}', font) else 'system'}

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
                    'permissions': {'profiles': session.get('permissions', {}).get('profiles') is True}}

    def _local(self, action, payload=None):
        with self._api._lock:
            if not self._api._session or not self._api._token or self._api._clock() >= self._api._deadline:
                raise PermissionError('Sign in to use live controls.')
        result = self._api.local(action, payload or {})
        if not result.get('ok'):
            raise ValueError(str(result.get('error', 'Action failed.'))[:200])
        return result['data']

    def macro_status(self):
        return self._local('macro_status')

    def toggle_macro(self, kind, enabled):
        if not isinstance(kind, str) or type(enabled) is not bool:
            raise ValueError('Invalid macro toggle.')
        from .macros import EXTENDED_DEFAULTS
        if kind not in ('single_edit', 'drag', *EXTENDED_DEFAULTS):
            raise ValueError('Unknown macro.')
        return self._local('macro_enable', {'kind': kind, 'enabled': enabled})

    def tools_state(self):
        return self._local('workspace_get', {'key': 'overlay_tools'})['value']

    def save_tools_state(self, value):
        return self._local('workspace_save', {'key': 'overlay_tools', 'value': value})

    def heavy_apps(self):
        return self._local('heavy_apps')

    def quick_note(self, text):
        """Append a one-line note to the Match journal."""
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 200:
            raise ValueError('Write a note of 1-200 characters.')
        journal = self._local('workspace_get', {'key': 'journal'})['value']
        entries = journal.get('entries') if isinstance(journal.get('entries'), list) else []
        entry = {'id': f'q{int(time.time() * 1000):x}', 'title': text.strip()[:80], 'mode': 'Quick note', 'placement': None,
                 'tags': ['overlay'], 'notes': text.strip(), 'created_at': time.time()}
        self._local('workspace_save', {'key': 'journal', 'value': {**journal, 'entries': [entry, *entries][:200]}})
        return {'saved': True}

    def hardware(self):
        """Read-only device summary for the System panel."""
        return self._local('hardware')

    def emergency_stop(self):
        return self._local('emergency_stop')

    def loadouts(self):
        return self._local('loadout_list')

    def preview_loadout(self, identifier):
        return self._local('loadout_preview', {'id': identifier})

    def apply_loadout(self, identifier):
        return self._local('loadout_apply', {'id': identifier})

    def macro_profiles(self):
        """Return saved configurations for editing, without enabling input tools."""
        with self._api._lock:
            session = self._api._session
            active = bool(session and self._api._token and self._api._clock() < self._api._deadline)
            allowed = bool(active and session.get('permissions', {}).get('profiles') is True)
        if not allowed:
            return {'available': False, 'profiles': []}
        response = self._api.request('GET', '/v1/profiles')
        if not response.get('ok'):
            return {'available': True, 'profiles': [], 'error': str(response.get('error', 'Profiles could not be loaded.'))[:200]}
        rows = response.get('data', {}).get('profiles', [])
        if not isinstance(rows, list):
            return {'available': True, 'profiles': []}
        safe = []
        for row in rows[:100]:
            if not isinstance(row, dict) or not isinstance(row.get('name'), str):
                continue
            config = row.get('config') if isinstance(row.get('config'), dict) else {}
            kind = config.get('kind', 'custom')
            safe.append({'id': row.get('id'), 'name': row['name'][:80],
                         'kind': kind[:40] if isinstance(kind, str) else 'custom',
                         'config': config.get('config') if isinstance(config.get('config'), dict) else {},
                         'saved_at': row.get('created_at')})
        return {'available': True, 'profiles': safe}

    def save_macro_profile(self, profile_id, name, config):
        """Update a saved profile only. Loading or enabling remains an explicit main-app action."""
        if type(profile_id) is not int or profile_id < 1 or not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('Enter a valid profile name.')
        if not isinstance(config, dict):
            raise ValueError('Invalid profile configuration.')
        profiles = self.macro_profiles()
        if not profiles['available']:
            raise ValueError('Profiles are unavailable for this account.')
        selected = next((item for item in profiles['profiles'] if item['id'] == profile_id), None)
        if not selected:
            raise ValueError('Profile not found. Refresh the list and try again.')
        previous = selected['config']
        if set(config) != set(previous) or any(type(config[key]) is not type(value) for key, value in previous.items()):
            raise ValueError('Edit the existing settings without changing their types.')
        if any(isinstance(value, str) and (len(value) > 80 or not value.strip()) for value in config.values()):
            raise ValueError('A setting is empty or too long.')
        result = self._api.request('POST', '/v1/profiles', {'id': profile_id, 'name': name.strip(),
                                                           'config': {'kind': selected['kind'], 'config': config}})
        if not result.get('ok'):
            raise ValueError(str(result.get('error', 'Could not save profile.'))[:200])
        return {'saved': True}

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


class WidgetBridge:
    """Read-only state for the widget bar; exposes nothing that changes settings."""
    def __init__(self, overlay_bridge):
        self._overlay = overlay_bridge

    def state(self):
        return self._overlay.widget_state()


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
        u.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
        u.GetAncestor.restype = wintypes.HWND
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        u.AttachThreadInput.restype = wintypes.BOOL
        u.BringWindowToTop.argtypes = [wintypes.HWND]
        u.BringWindowToTop.restype = wintypes.BOOL
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel32.GetCurrentThreadId.restype = wintypes.DWORD

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

    def place(self, window_hwnd, rect):
        left, top, right, bottom = rect
        self.user32.SetWindowPos(window_hwnd, None, left, top, right - left, bottom - top,
                                 0x0004 | 0x0010)  # Preserve z-order and activation.

    def root(self, hwnd):
        # Dropdowns and other WebView2 popups are owned by the overlay window.
        return (self.user32.GetAncestor(hwnd, 3) or hwnd) if hwnd else hwnd  # GA_ROOTOWNER

    def prepare_passive(self, hwnd):
        """Widget bar: never activates, never takes clicks, hidden from Alt-Tab."""
        u = self.user32
        u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = ctypes.c_long
        u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        u.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_ubyte, wintypes.DWORD]
        style = u.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
        u.SetWindowLongW(hwnd, -20, style | 0x08000000 | 0x00000080 | 0x00000020 | 0x00080000)  # NOACTIVATE|TOOLWINDOW|TRANSPARENT|LAYERED
        u.SetLayeredWindowAttributes(hwnd, 0, 235, 0x2)  # LWA_ALPHA

    def show_passive(self, hwnd, rect):
        left, top, right, bottom = rect
        self.user32.SetWindowPos(hwnd, wintypes.HWND(-1), left, top, right - left, bottom - top,
                                 0x0010 | 0x0040)  # HWND_TOPMOST, SWP_NOACTIVATE|SWP_SHOWWINDOW

    def hide_passive(self, hwnd):
        self.user32.ShowWindow(hwnd, 0)

    def focus(self, hwnd):
        u = self.user32
        if u.SetForegroundWindow(hwnd) and u.GetForegroundWindow() == hwnd:
            return True
        # Windows refuses foreground changes from background processes; sharing the
        # current foreground thread's input state is the documented way around it.
        target = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
        mine = self.kernel32.GetCurrentThreadId()
        attached = bool(target and target != mine and u.AttachThreadInput(mine, target, True))
        try:
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
        finally:
            if attached:
                u.AttachThreadInput(mine, target, False)
        return u.GetForegroundWindow() == hwnd


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
        self.last_layout = None
        self.was_down = False
        self.last_key = None
        self.lock = threading.RLock()
        self.widget_hwnd = None
        self.widget_shown = False

    def attach_widget(self, hwnd):
        self.widget_hwnd = hwnd
        if hasattr(self.probe, 'prepare_passive'):
            self.probe.prepare_passive(hwnd)

    def _update_widget(self, game_active):
        if not self.widget_hwnd or not hasattr(self.probe, 'show_passive'):
            return
        want = bool(self.bridge._values.get('widgets') and game_active and not self.open and self.game_hwnd)
        if want:
            bounds = self.probe.bounds(self.game_hwnd)
            if bounds:
                width, height = 380, 44
                x = (bounds[0] + bounds[2] - width) // 2
                self.probe.show_passive(self.widget_hwnd, (x, bounds[1] + 14, x + width, bounds[1] + 14 + height))
                self.widget_shown = True
        elif self.widget_shown:
            self.probe.hide_passive(self.widget_hwnd)
            self.widget_shown = False

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
            if current and self.overlay_hwnd and self.probe.root(current) == self.overlay_hwnd:
                current = self.overlay_hwnd
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
                self.apply_layout()
            self._update_widget(game_active)

    def apply_layout(self):
        if not self.game_hwnd or not self.probe.exists(self.game_hwnd):
            return
        bounds = self.probe.bounds(self.game_hwnd)
        values = self.bridge._values
        layout_key = (bounds, values['size'], values['position'])
        if layout_key == self.last_layout:
            return
        rect = layout_rect(bounds, values['size'], values['position'])
        if hasattr(self.window, 'resize') and rect:
            self.window.resize(rect[2] - rect[0], rect[3] - rect[1])
        if hasattr(self.probe, 'place') and rect:
            self.probe.place(self.overlay_hwnd, rect)
        else:
            self.probe.center(self.overlay_hwnd, self.game_hwnd)
        self.last_bounds, self.last_layout = bounds, layout_key

    def show(self):
        if self.open or not self.game_hwnd:
            return
        self.window.show()
        self.apply_layout()
        self.probe.focus(self.overlay_hwnd)
        self.open = True
        # Account and lease data may have changed since this hidden page loaded.
        self.window.evaluate_js("document.body.classList.remove('closing'); document.body.classList.remove('opening'); "
                                "void document.body.offsetWidth; document.body.classList.add('opening'); "
                                "window.SacredOverlay && (window.SacredOverlay.opened(), window.SacredOverlay.refresh()); "
                                "(document.querySelector('.nav.active') || document.body).focus()")

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
