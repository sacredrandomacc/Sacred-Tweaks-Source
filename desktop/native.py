# Copyright (c) 2026 Sacred LLC. All rights reserved. See LICENSE.
"""Native boundary: allowlisted local operations, Windows input and lease watchdog.

No process injection, game memory reads, anti-cheat bypass or hidden settings.
Low-level hooks discard unrelated input immediately, never record typed text,
and ignore injected keyboard/mouse events. Hooks only enqueue configured
activation/emergency transitions; the independent worker owns input output.
"""
from __future__ import annotations

import ctypes
from contextlib import contextmanager
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import platform as system_platform
import queue
import re
import threading
import time
import uuid

from .macros import KEY_CODES, MacroCoordinator, validate_config, DEFAULT_CONFIG, EXTENDED_DEFAULTS, COMMON_EXTENDED, DEFAULT_TOGGLES
from .settings import SettingsManager, FilterKeysManager, atomic_json

FORTNITE_EXECUTABLES = frozenset({'fortniteclient-win64-shipping.exe', 'fortniteclient-win64-shipping_eac_eos.exe',
                                'fortniteclient-win64-shipping_be.exe'})
WINDOWS_PAGES = {'game_mode': 'ms-settings:gaming-gamemode', 'power': 'ms-settings:powersleep',
                 'capture': 'ms-settings:gaming-gamedvr', 'graphics': 'ms-settings:display-advancedgraphics',
                 'startup': 'ms-settings:startupapps', 'display': 'ms-settings:display',
                 'keyboard': 'ms-settings:easeofaccess-keyboard'}
PROCEDURE = ('Use the same Fortnite replay or Creative route, resolution, render mode and FPS cap. '
             'Warm up for five minutes, then observe three equal 60-second runs before and after one change. '
             'Record the in-game FPS counter or an external supported capture tool manually, name records '
             'Before/After, and include route and duration in notes. These records are not automatic benchmarks.')


# Must match web/particles.js styles and the font list in web/app.js.
PARTICLE_STYLES = {'none', 'stardust', 'fireflies', 'snow', 'embers', 'bubbles', 'constellation', 'sakura', 'rain', 'bats', 'waves', 'starfield', 'aurora', 'grid'}
SOUND_PACKS = {'soft', 'mechanical', 'scifi'}
LAYOUTS = {'comfortable', 'compact'}
# Free-form page data (journal, training, overlay tools), stored per PC.
WORKSPACE_KEYS = {'journal', 'training', 'overlay_tools', 'goals', 'meta', 'custom_themes', 'routines', 'custom_sounds'}
WORKSPACE_MAX_BYTES = 64 * 1024
WORKSPACE_LIMITS = {'custom_sounds': 768 * 1024}  # Three short clips as base64.
FONTS = {'system', 'bahnschrift', 'cascadia', 'trebuchet', 'georgia', 'verdana', 'franklin'}

class UnsupportedPlatform:
    available = False
    error = 'Native input requires Windows 10/11. No input is generated on this platform.'

    def start(self, callback, interested):
        pass

    def down(self, key):
        raise OSError(self.error)

    def up(self, key):
        raise OSError(self.error)

    def move(self, dx, dy):
        raise OSError(self.error)

    def foreground(self):
        return False

    def game_running(self):
        return False

    def close(self):
        pass


class WindowsPlatform:
    """Documented user32 hooks/SendInput; no injection into another process.

    SendInput is subject to UIPI and may be rejected by a protected application.
    We do not elevate or circumvent that restriction. Name matching identifies
    expected Fortnite executables; it is not executable authenticity attestation.
    """
    available = True

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [('wVk', ctypes.c_uint16), ('wScan', ctypes.c_uint16), ('dwFlags', ctypes.c_uint32),
                    ('time', ctypes.c_uint32), ('dwExtraInfo', ctypes.c_size_t)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [('dx', ctypes.c_int32), ('dy', ctypes.c_int32), ('mouseData', ctypes.c_uint32),
                    ('dwFlags', ctypes.c_uint32), ('time', ctypes.c_uint32), ('dwExtraInfo', ctypes.c_size_t)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [('uMsg', ctypes.c_uint32), ('wParamL', ctypes.c_uint16), ('wParamH', ctypes.c_uint16)]

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [('vkCode', ctypes.c_uint32), ('scanCode', ctypes.c_uint32), ('flags', ctypes.c_uint32),
                    ('time', ctypes.c_uint32), ('dwExtraInfo', ctypes.c_size_t)]

    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [('x', ctypes.c_int32), ('y', ctypes.c_int32), ('mouseData', ctypes.c_uint32),
                    ('flags', ctypes.c_uint32), ('time', ctypes.c_uint32), ('dwExtraInfo', ctypes.c_size_t)]

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [('dwSize', ctypes.c_uint32), ('cntUsage', ctypes.c_uint32), ('th32ProcessID', ctypes.c_uint32),
                    ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', ctypes.c_uint32),
                    ('cntThreads', ctypes.c_uint32), ('th32ParentProcessID', ctypes.c_uint32),
                    ('pcPriClassBase', ctypes.c_int32), ('dwFlags', ctypes.c_uint32), ('szExeFile', ctypes.c_wchar * 260)]

    def __init__(self):
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self.error = None
        self.thread = None
        self.thread_id = None
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self.hooks = []
        self._callbacks = []  # Keep ctypes callback closures alive until unhooked.
        self._foreground_cache = (None, 0.0, False)
        class INPUTUNION(ctypes.Union):
            _fields_ = [('ki', WindowsPlatform.KEYBDINPUT), ('mi', WindowsPlatform.MOUSEINPUT), ('hi', WindowsPlatform.HARDWAREINPUT)]
        class INPUT(ctypes.Structure):
            _anonymous_ = ('union',)
            _fields_ = [('type', ctypes.c_uint32), ('union', INPUTUNION)]
        self.INPUT = INPUT
        u, k = self.user32, self.kernel32
        u.SendInput.argtypes = [ctypes.c_uint32, ctypes.POINTER(INPUT), ctypes.c_int]
        u.SendInput.restype = ctypes.c_uint32
        u.GetForegroundWindow.restype = wintypes.HWND
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(ctypes.c_uint32)]
        u.GetWindowThreadProcessId.restype = ctypes.c_uint32
        u.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t]
        u.CallNextHookEx.restype = ctypes.c_ssize_t
        u.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
        u.SetWindowsHookExW.restype = ctypes.c_void_p
        u.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        u.UnhookWindowsHookEx.restype = wintypes.BOOL
        u.PostThreadMessageW.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t, ctypes.c_ssize_t]
        u.PostThreadMessageW.restype = wintypes.BOOL
        u.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, ctypes.c_uint32, ctypes.c_uint32]
        u.GetMessageW.restype = ctypes.c_int
        u.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        u.TranslateMessage.restype = wintypes.BOOL
        u.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        u.DispatchMessageW.restype = ctypes.c_ssize_t
        u.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
        u.PeekMessageW.restype = wintypes.BOOL
        k.GetCurrentThreadId.restype = ctypes.c_uint32
        k.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        k.GetModuleHandleW.restype = ctypes.c_void_p
        k.OpenProcess.argtypes = [ctypes.c_uint32, wintypes.BOOL, ctypes.c_uint32]
        k.OpenProcess.restype = ctypes.c_void_p
        k.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, wintypes.LPWSTR, ctypes.POINTER(ctypes.c_uint32)]
        k.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        k.CloseHandle.restype = wintypes.BOOL
        k.CreateToolhelp32Snapshot.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        for name in ('Process32FirstW', 'Process32NextW'):
            function = getattr(k, name)
            function.argtypes = [ctypes.c_void_p, ctypes.POINTER(self.PROCESSENTRY32W)]
            function.restype = wintypes.BOOL

    def _send(self, key, down):
        event = self.INPUT()
        if key.startswith('MOUSE'):
            event.type = 0
            codes = {'MOUSE1': (0x2, 0x4, 0), 'MOUSE2': (0x8, 0x10, 0), 'MOUSE3': (0x20, 0x40, 0),
                     'MOUSE4': (0x80, 0x100, 1), 'MOUSE5': (0x80, 0x100, 2)}
            press, release, data = codes[key]
            event.mi = self.MOUSEINPUT(0, 0, data, press if down else release, 0, 0x53414352)
        else:
            event.type = 1
            extended = key in ('LEFT', 'RIGHT', 'UP', 'DOWN', 'INSERT', 'DELETE', 'HOME', 'END', 'PAGEUP', 'PAGEDOWN')
            event.ki = self.KEYBDINPUT(KEY_CODES[key], 0, (0 if down else 2) | int(extended), 0, 0x53414352)
        if self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)) != 1:
            raise OSError('Windows rejected synthetic input (possibly UIPI or application restrictions). No bypass is attempted.')

    def down(self, key):
        self._send(key, True)

    def up(self, key):
        self._send(key, False)

    def move(self, dx, dy):
        event = self.INPUT()
        event.type = 0
        event.mi = self.MOUSEINPUT(dx, dy, 0, 0x0001, 0, 0x53414352)
        if self.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event)) != 1:
            raise OSError('Windows rejected synthetic mouse movement. No bypass is attempted.')

    def foreground(self):
        window = self.user32.GetForegroundWindow()
        if not window:
            return False
        previous, checked_at, value = self._foreground_cache
        if window == previous and time.monotonic() - checked_at < 1:
            return value
        pid = ctypes.c_uint32()
        self.user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        handle = self.kernel32.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return False
        try:
            size = ctypes.c_uint32(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not self.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return False
            result = Path(buffer.value).name.lower() in FORTNITE_EXECUTABLES
            self._foreground_cache = (window, time.monotonic(), result)
            return result
        finally:
            self.kernel32.CloseHandle(handle)

    def game_running(self):
        handle = self.kernel32.CreateToolhelp32Snapshot(0x2, 0)
        if handle in (None, ctypes.c_void_p(-1).value):
            raise OSError('Cannot enumerate running processes; settings changes are blocked.')
        try:
            item = self.PROCESSENTRY32W()
            item.dwSize = ctypes.sizeof(item)
            success = self.kernel32.Process32FirstW(handle, ctypes.byref(item))
            while success:
                if item.szExeFile.lower() in FORTNITE_EXECUTABLES:
                    return True
                success = self.kernel32.Process32NextW(handle, ctypes.byref(item))
            if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES is normal enumeration completion.
                raise OSError('Cannot inspect running processes; settings changes are blocked.')
            return False
        finally:
            self.kernel32.CloseHandle(handle)

    def start(self, callback, interested):
        self.thread = threading.Thread(target=self._hook_loop, args=(callback, interested), name='Sacred-input-hooks', daemon=True)
        self.thread.start()
        if not self.ready.wait(3):
            self.error = 'Windows input hooks did not start.'

    def _hook_loop(self, callback, interested):
        self.thread_id = self.kernel32.GetCurrentThreadId()
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)
        vk_names = {v: k for k, v in KEY_CODES.items() if not k.startswith('MOUSE')}
        vk_names.update({0xA0: 'SHIFT', 0xA1: 'SHIFT', 0xA2: 'CTRL', 0xA3: 'CTRL', 0xA4: 'ALT', 0xA5: 'ALT'})

        def handle(kind, code, message, address):
            try:
                if code >= 0:
                    if kind == 'keyboard':
                        event = ctypes.cast(address, ctypes.POINTER(self.KBDLLHOOKSTRUCT)).contents
                        key = vk_names.get(event.vkCode)
                        down = message in (0x100, 0x104)
                        valid = message in (0x100, 0x101, 0x104, 0x105) and not event.flags & 0x10
                    else:
                        event = ctypes.cast(address, ctypes.POINTER(self.MSLLHOOKSTRUCT)).contents
                        mapping = {0x201: ('MOUSE1', True), 0x202: ('MOUSE1', False), 0x204: ('MOUSE2', True),
                                   0x205: ('MOUSE2', False), 0x207: ('MOUSE3', True), 0x208: ('MOUSE3', False)}
                        if message in (0x20B, 0x20C):
                            key, down = ('MOUSE4' if event.mouseData >> 16 == 1 else 'MOUSE5'), message == 0x20B
                        else:
                            key, down = mapping.get(message, (None, False))
                        valid = key is not None and not event.flags & 1
                    if valid and key:
                        wanted, suppress = interested(key)
                        if wanted:
                            callback(key, down)
                            if suppress:
                                return 1
            except Exception:
                self.error = 'Input hook failed; macro operation is disabled.'
            return self.user32.CallNextHookEx(None, code, message, address)

        self._callbacks = [callback_type(lambda c, m, a: handle('keyboard', c, m, a)),
                           callback_type(lambda c, m, a: handle('mouse', c, m, a))]
        try:
            message = wintypes.MSG()
            self.user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)  # Create queue before close can post WM_QUIT.
            module = self.kernel32.GetModuleHandleW(None)
            for kind, function in zip((13, 14), self._callbacks):
                hook = self.user32.SetWindowsHookExW(kind, function, module, 0)
                if not hook:
                    raise ctypes.WinError(ctypes.get_last_error())
                self.hooks.append(hook)
            self.ready.set()
            while not self.stopping.is_set():
                result = self.user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    if result < 0:
                        self.error = 'Windows hook message loop failed.'
                    break
                self.user32.TranslateMessage(ctypes.byref(message))
                self.user32.DispatchMessageW(ctypes.byref(message))
        except Exception as exc:
            self.error = f'Windows input hooks unavailable: {exc}'
        finally:
            self.ready.set()
            for hook in self.hooks:
                self.user32.UnhookWindowsHookEx(hook)
            self.hooks.clear()

    def close(self):
        self.stopping.set()
        if self.thread_id:
            self.user32.PostThreadMessageW(self.thread_id, 0x12, 0, 0)
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)


def hardware_info():
    result = {'available': os.name == 'nt', 'cpu': system_platform.processor() or 'Unavailable', 'gpu': None,
              'ram_gb': None, 'windows': system_platform.platform(), 'display': {'width': None, 'height': None, 'refresh_hz': None},
              'limitations': []}
    if os.name != 'nt':
        result['limitations'].append('Windows hardware and input APIs are unavailable on this platform.')
        return result
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            result['cpu'] = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
    except OSError:
        result['limitations'].append('CPU model could not be queried.')
    try:
        memory = memory_info()
        result['ram_gb'] = memory['total_bytes'] / (1024 ** 3)
    except OSError:
        result['limitations'].append('Physical RAM information unavailable.')
    user32, gdi32 = ctypes.WinDLL('user32'), ctypes.WinDLL('gdi32')
    class DISPLAY_DEVICE(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_uint32), ('DeviceName', ctypes.c_wchar * 32), ('DeviceString', ctypes.c_wchar * 128),
                    ('StateFlags', ctypes.c_uint32), ('DeviceID', ctypes.c_wchar * 128), ('DeviceKey', ctypes.c_wchar * 128)]
    user32.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, ctypes.c_uint32, ctypes.POINTER(DISPLAY_DEVICE), ctypes.c_uint32]
    user32.EnumDisplayDevicesW.restype = wintypes.BOOL
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
    gdi32.GetDeviceCaps.restype = ctypes.c_int
    adapters = []
    for index in range(16):
        device = DISPLAY_DEVICE()
        device.cb = ctypes.sizeof(device)
        if not user32.EnumDisplayDevicesW(None, index, ctypes.byref(device), 0):
            break
        if device.DeviceString and device.DeviceString not in adapters:
            adapters.append(device.DeviceString)
    result['gpu'] = ', '.join(adapters) or None
    dc = user32.GetDC(None)
    if dc:
        try:
            refresh = gdi32.GetDeviceCaps(dc, 116)
            result['display'] = {'width': gdi32.GetDeviceCaps(dc, 118), 'height': gdi32.GetDeviceCaps(dc, 117),
                                 'refresh_hz': refresh if refresh > 1 else None}
        finally:
            user32.ReleaseDC(None, dc)
    result['limitations'].append('Display metrics describe the primary desktop; hybrid GPU names do not identify the adapter rendering Fortnite.')
    return result


def startup_apps():
    """Read-only list of programs Windows starts at sign-in (Run keys)."""
    if os.name != 'nt':
        return []
    import winreg
    apps = []
    for hive, scope in ((winreg.HKEY_CURRENT_USER, 'This user'), (winreg.HKEY_LOCAL_MACHINE, 'All users')):
        try:
            with winreg.OpenKey(hive, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
                for index in range(256):
                    try:
                        name, command, _ = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    apps.append({'name': str(name)[:120], 'command': str(command)[:300], 'scope': scope})
        except OSError:
            continue
    return apps


# Common background apps that compete with games for CPU, RAM or bandwidth.
HEAVY_APPS = {'chrome.exe': 'Google Chrome', 'msedge.exe': 'Microsoft Edge', 'firefox.exe': 'Firefox', 'opera.exe': 'Opera',
              'brave.exe': 'Brave', 'obs64.exe': 'OBS Studio', 'spotify.exe': 'Spotify', 'steamwebhelper.exe': 'Steam',
              'onedrive.exe': 'OneDrive', 'teams.exe': 'Microsoft Teams', 'ms-teams.exe': 'Microsoft Teams',
              'adobe desktop service.exe': 'Adobe Creative Cloud', 'medal.exe': 'Medal', 'overwolf.exe': 'Overwolf',
              'bluestacks.exe': 'BlueStacks', 'blender.exe': 'Blender', 'premiere pro.exe': 'Premiere Pro'}


def running_heavy_apps():
    """Names (not command lines) of known heavy background apps, via tasklist."""
    if os.name != 'nt':
        return []
    import csv
    import subprocess
    try:
        output = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, timeout=5,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = {}
    for row in csv.reader(output.splitlines()):
        if len(row) >= 5 and row[0].lower() in HEAVY_APPS:
            label = HEAVY_APPS[row[0].lower()]
            memory = int(re.sub(r'\D', '', row[4]) or 0) // 1024
            found[label] = found.get(label, 0) + memory
    return [{'name': name, 'memory_mb': mb} for name, mb in sorted(found.items(), key=lambda item: -item[1])]


def display_modes():
    """Current and highest refresh rate available at the current resolution."""
    result = {'current_hz': None, 'max_hz': None, 'width': None, 'height': None}
    if os.name != 'nt':
        return result
    class DEVMODE(ctypes.Structure):
        _fields_ = [('dmDeviceName', ctypes.c_wchar * 32), ('dmSpecVersion', ctypes.c_uint16), ('dmDriverVersion', ctypes.c_uint16),
                    ('dmSize', ctypes.c_uint16), ('dmDriverExtra', ctypes.c_uint16), ('dmFields', ctypes.c_uint32),
                    ('dmPositionX', ctypes.c_int32), ('dmPositionY', ctypes.c_int32), ('dmDisplayOrientation', ctypes.c_uint32),
                    ('dmDisplayFixedOutput', ctypes.c_uint32), ('dmColor', ctypes.c_short), ('dmDuplex', ctypes.c_short),
                    ('dmYResolution', ctypes.c_short), ('dmTTOption', ctypes.c_short), ('dmCollate', ctypes.c_short),
                    ('dmFormName', ctypes.c_wchar * 32), ('dmLogPixels', ctypes.c_uint16), ('dmBitsPerPel', ctypes.c_uint32),
                    ('dmPelsWidth', ctypes.c_uint32), ('dmPelsHeight', ctypes.c_uint32), ('dmDisplayFlags', ctypes.c_uint32),
                    ('dmDisplayFrequency', ctypes.c_uint32), ('dmICMMethod', ctypes.c_uint32), ('dmICMIntent', ctypes.c_uint32),
                    ('dmMediaType', ctypes.c_uint32), ('dmDitherType', ctypes.c_uint32), ('dmReserved1', ctypes.c_uint32),
                    ('dmReserved2', ctypes.c_uint32), ('dmPanningWidth', ctypes.c_uint32), ('dmPanningHeight', ctypes.c_uint32)]
    user32 = ctypes.WinDLL('user32')
    user32.EnumDisplaySettingsW.argtypes = [wintypes.LPCWSTR, ctypes.c_uint32, ctypes.POINTER(DEVMODE)]
    user32.EnumDisplaySettingsW.restype = wintypes.BOOL
    mode = DEVMODE()
    mode.dmSize = ctypes.sizeof(DEVMODE)
    if not user32.EnumDisplaySettingsW(None, 0xFFFFFFFF, ctypes.byref(mode)):  # ENUM_CURRENT_SETTINGS
        return result
    width, height = mode.dmPelsWidth, mode.dmPelsHeight
    result.update(current_hz=mode.dmDisplayFrequency, width=width, height=height)
    best = mode.dmDisplayFrequency
    for index in range(1024):
        option = DEVMODE()
        option.dmSize = ctypes.sizeof(DEVMODE)
        if not user32.EnumDisplaySettingsW(None, index, ctypes.byref(option)):
            break
        if option.dmPelsWidth == width and option.dmPelsHeight == height:
            best = max(best, option.dmDisplayFrequency)
    result['max_hz'] = best
    return result


def memory_info():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [('dwLength', ctypes.c_uint32), ('dwMemoryLoad', ctypes.c_uint32),
                    ('ullTotalPhys', ctypes.c_uint64), ('ullAvailPhys', ctypes.c_uint64), ('ullTotalPageFile', ctypes.c_uint64),
                    ('ullAvailPageFile', ctypes.c_uint64), ('ullTotalVirtual', ctypes.c_uint64),
                    ('ullAvailVirtual', ctypes.c_uint64), ('ullAvailExtendedVirtual', ctypes.c_uint64)]
    value = MEMORYSTATUSEX()
    value.dwLength = ctypes.sizeof(value)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMORYSTATUSEX)]
    kernel32.GlobalMemoryStatusEx.restype = wintypes.BOOL
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {'total_bytes': value.ullTotalPhys, 'available_bytes': value.ullAvailPhys, 'usage_percent': value.dwMemoryLoad}


def system_cpu_times():
    if os.name != 'nt':
        return None
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GetSystemTimes.argtypes = [ctypes.POINTER(wintypes.FILETIME)] * 3
    kernel32.GetSystemTimes.restype = wintypes.BOOL
    idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    if not kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None
    return tuple((v.dwHighDateTime << 32) | v.dwLowDateTime for v in (idle, kernel, user))


class CpuSampler:
    """Nonblocking system CPU estimate between samples; kernel time includes idle."""
    def __init__(self, read_times=system_cpu_times):
        self.read_times = read_times
        self.previous = None

    def sample(self, now=None):
        now = time.monotonic() if now is None else now
        current = self.read_times()
        result = {'cpu_usage_percent': None, 'cpu_sample_seconds': None}
        if current is not None and self.previous is not None:
            prior, when = self.previous
            idle = current[0] - prior[0]
            total = current[1] - prior[1] + current[2] - prior[2]
            if total > 0 and now > when and 0 <= idle <= total:
                result = {'cpu_usage_percent': round(100 * (1 - idle / total), 2), 'cpu_sample_seconds': round(now - when, 3)}
        self.previous = (current, now) if current is not None else None
        return result


class NativeTools:
    def __init__(self, data_dir: Path, *, platform=None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.platform = platform if platform is not None else (WindowsPlatform() if os.name == 'nt' else UnsupportedPlatform())
        self.engine = MacroCoordinator(self.platform)
        self.lock = threading.RLock()
        self.actions_lock = threading.RLock()
        self.authorization_lock = threading.RLock()
        self.events = queue.Queue(maxsize=64)
        self.overflow = threading.Event()
        self.closed = threading.Event()
        self.permissions, self.enforced, self.deadline = {}, {}, 0.0
        self.foreground = False
        self.account_id = None
        self.authorization_generation = 0
        self._interest = (frozenset({'F'}), frozenset({'F8'}), frozenset())  # Immutable snapshot: hook never takes a lock or blocks.
        self.settings = SettingsManager(self.data_dir, game_running=self.platform.game_running, authorize=self._require)
        self.cpu = CpuSampler()
        self.live_cpu = CpuSampler()  # Separate so live readings never skew saved measurements.
        self.cpu.sample()
        self.filter = None
        self.platform.start(self._enqueue, self._interested)
        self.worker = threading.Thread(target=self._loop, name='Sacred-authorization-watchdog', daemon=True)
        self.worker.start()

    def _interested(self, key):
        activation, emergency, suppressed = self._interest
        return (key in activation or key in emergency), key in suppressed and time.monotonic() < self.deadline

    def _enqueue(self, key, down):
        activation, emergency, _ = self._interest
        if key not in activation and key not in emergency:
            return
        try:
            self.events.put_nowait((key, down))
        except queue.Full:
            self.overflow.set()

    def _drain(self):
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                return

    def _update_interest(self):
        suppressed = set()
        if self.foreground:
            for engine in self.engine.instances.values():
                if engine.authorized:
                    suppressed.add(engine.config['toggle'])
                    if engine.enabled and engine.kind not in ('drag', 'auto_build'):
                        suppressed.update(engine.activation_keys())
        emergency = {engine.config['emergency'] for engine in self.engine.instances.values()}
        self._interest = (frozenset(self.engine.activation_keys()), frozenset(emergency), frozenset(suppressed))

    def _loop(self):
        while not self.closed.wait(.005 if self.engine.enabled or self.engine.held else .05):
            try:
                foreground = self.platform.foreground()
                with self.lock:
                    now = time.monotonic()
                    if self.overflow.is_set():
                        self.engine.stop('Input event overflow; enable explicitly')
                        self._drain()
                        self.overflow.clear()
                    if self.platform.error:
                        self.engine.stop(self.platform.error)
                        self._drain()
                    if self.foreground and not foreground and self.engine.enabled:
                        self.engine.stop('Fortnite lost focus; enable explicitly')
                        self._drain()
                    self.foreground = foreground
                    # Deadline and focus are checked even if no event/GUI call arrives.
                    self.engine.tick(now, foreground)
                    while True:
                        try:
                            key, down = self.events.get_nowait()
                        except queue.Empty:
                            break
                        self.engine.input(key, down, now, foreground)
                    self._update_interest()
            except Exception as exc:
                with self.lock:
                    self.engine.stop(f'Native input stopped: {exc}')
                    self._drain()
                    self._update_interest()

    def set_authorization(self, permissions, enforced, deadline):
        with self.authorization_lock, self.lock:
            # The bridge supplies the immutable login snapshot each renewal.
            # JSON copying prevents a caller subsequently mutating our boundary.
            if self.permissions != (permissions or {}) or self.enforced != (enforced or {}):
                self.authorization_generation += 1
            self.permissions = json.loads(json.dumps(permissions or {}))
            self.enforced = json.loads(json.dumps(enforced or {}))
            self.deadline = float(deadline)
            self.engine.set_authorization(self.permissions, self.deadline)
            self._update_interest()

    def stop(self, reason):
        with self.lock:
            self.authorization_generation += 1
            self.deadline = 0.0
            self.engine.set_authorization(False, 0)
            self.engine.stop(reason)
            self._drain()
            self._update_interest()

    def close(self):
        if self.closed.is_set():
            return
        self.stop('Application closed')
        self.closed.set()
        self.platform.close()
        if self.worker is not threading.current_thread():
            self.worker.join(timeout=2)

    def set_account(self, account_id):
        if account_id is not None and (type(account_id) is not int or account_id <= 0):
            raise ValueError('Invalid account identity.')
        with self.lock:
            if account_id != self.account_id:
                self.engine.stop('Account changed')
                self.engine = MacroCoordinator(self.platform)
                self.account_id = account_id
                self.engine.set_authorization(self.permissions, self.deadline)
                if account_id is not None:
                    try:
                        saved = self._read_json(f'macro-workspace-{account_id}.json', {})
                        if isinstance(saved, dict):
                            for kind, config in saved.get('macros', {}).items():
                                self.engine.configure(kind, config)
                            if saved.get('editing_conflicts') in ('newest', 'allow_multiple'):
                                self.engine.editing_conflicts = saved['editing_conflicts']
                    except (ValueError, TypeError, OSError, AttributeError):
                        self.engine = MacroCoordinator(self.platform)
                        self.engine.set_authorization(self.permissions, self.deadline)
                self._drain()
                self._update_interest()

    def _persist_macro_workspace(self):
        if self.account_id is not None:
            atomic_json(self.data_dir / f'macro-workspace-{self.account_id}.json',
                        {'macros': {kind: engine.config for kind, engine in self.engine.instances.items()},
                         'editing_conflicts': self.engine.editing_conflicts})

    def _loadout_path(self):
        if self.account_id is None:
            raise PermissionError('Sign in to use loadouts.')
        return self.data_dir / f'loadouts-{self.account_id}.json'

    def _loadouts(self):
        path = self._loadout_path()
        if not path.exists():
            return []
        rows = self._read_json(path.name, [])
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError('Saved loadouts are invalid.')
        return rows

    def _validated_loadout(self, row):
        if not isinstance(row, dict) or not isinstance(row.get('macros'), dict) or not isinstance(row.get('appearance'), dict):
            raise ValueError('Invalid loadout.')
        if len(row['macros']) > len(EXTENDED_DEFAULTS) + 2:
            raise ValueError('Too many macros in loadout.')
        configs = {kind: validate_config(kind, config) for kind, config in row['macros'].items()}
        if 'single_edit' not in configs:
            raise ValueError('Loadout is missing its base macro configuration.')
        toggles = [config['toggle'] for config in configs.values()]
        if len(set(toggles)) != len(toggles):
            raise ValueError('Loadout macros have overlapping toggle shortcuts.')
        if self._overlay_hotkey() in toggles:
            raise ValueError('A loadout toggle conflicts with the overlay hotkey.')
        for kind, config in configs.items():
            self._require(kind, config)
        appearance = row['appearance']
        self._require('themes')
        if any(type(appearance.get(k)) is not bool for k in ('animations_enabled', 'lightweight', 'reduced_motion')):
            raise ValueError('Invalid loadout appearance toggles.')
        if any(not isinstance(appearance.get(k), str) or not re.fullmatch('#[A-Fa-f0-9]{6}', appearance[k])
               for k in ('accent', 'surface', 'text_color', 'muted_color')):
            raise ValueError('Invalid loadout colors.')
        return configs, appearance

    def _overlay_hotkey(self):
        try:
            return self._read_json('overlay-preferences.json', {}).get('hotkey', 'TAB')
        except (OSError, AttributeError):
            return 'TAB'

    def _require(self, feature=None, settings=None):
        with self.lock:
            if time.monotonic() >= self.deadline:
                self.engine.stop('Authorization expired')
                raise PermissionError('Authorization expired. Reconnect or sign in again.')
            if feature and self.permissions.get(feature) is not True:
                raise PermissionError('contact the owner for upgrading')
            if feature and settings is not None:
                for key, value in self.enforced.get(feature, {}).items():
                    if key not in settings or settings[key] != value:
                        raise PermissionError(f'{key} is enforced by the owner.')

    def _write_guard(self, generation, requirements):
        @contextmanager
        def guard():
            # A separate lock serializes the final write with account changes.
            # Never hold the input/watchdog lock across disk or Windows API I/O.
            with self.authorization_lock:
                with self.lock:
                    if generation != self.authorization_generation:
                        raise PermissionError('Authorization changed. Review and apply again.')
                    for feature, values in requirements:
                        self._require(feature, values)
                yield
        return guard

    def _status(self):
        with self.lock:
            result = self.engine.status() | {'foreground': self.foreground, 'available': self.platform.available, 'permissions': self.permissions.copy(), 'catalog': {'single_edit': DEFAULT_CONFIG, 'drag': DEFAULT_CONFIG | {'toggle': DEFAULT_TOGGLES['drag']}, **{k: COMMON_EXTENDED | v | {'toggle': DEFAULT_TOGGLES[k]} for k,v in EXTENDED_DEFAULTS.items()}}}
        try:
            result['game_running'] = self.platform.game_running()
        except OSError:
            result['game_running'] = None
        return result

    def _filter(self):
        if self.filter is None:
            self.filter = FilterKeysManager(self.data_dir, authorize=lambda: self._require('filter_keys'))
        return self.filter

    def call(self, action, payload=None):
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise ValueError('Local action payload must be an object.')
        # Status and emergency stop must never wait for disk or platform I/O.
        if action in {'emergency_stop', 'macro_status'}:
            return self._call(action, payload)
        # Serialize disk operations, keeping input/watchdog locks independent.
        with self.actions_lock:
            return self._call(action, payload)

    def _call(self, action, payload):
        if action == 'hardware':
            return hardware_info()
        if action == 'macro_status':
            return self._status()
        if action == 'emergency_stop':
            with self.lock:
                self.engine.stop('Emergency stop')
                self._drain()
                self._update_interest()
            return self._status()
        if action == 'backups':
            return {'backups': self.settings.backups()}
        if action == 'restore':
            backup = self.settings.store.get(payload.get('backup_id'))
            if backup['kind'] == 'filter_keys':
                return self._filter().restore(backup['id'])
            return self.settings.restore(backup['id'])
        self._require()
        if action == 'macro_configure':
            kind = payload.get('kind', 'single_edit')
            # Configuration changes are isolated to their target macro.
            with self.lock:
                self._drain()
                self._update_interest()
                config = validate_config(kind, payload.get('config', {}))
                if config['toggle'] == self._overlay_hotkey():
                    raise ValueError('Macro toggle conflicts with the overlay hotkey.')
                self._require(kind, config)
                self.engine.configure(kind, config)
                self._persist_macro_workspace()
                self._update_interest()
            return self._status()
        if action == 'macro_enable':
            enabled = payload.get('enabled', False)
            kind = payload.get('kind', self.engine.kind)
            if type(enabled) is not bool:
                raise ValueError('enabled must be a boolean.')
            with self.lock:
                if kind not in self.engine.instances:
                    raise ValueError('Configure this macro before enabling it.')
                self._require(kind, self.engine.instances[kind].config)
                if enabled and (not self.platform.available or self.platform.error):
                    raise OSError(self.platform.error or 'Windows input is unavailable.')
                self._drain()
                self.engine.enable(kind, enabled, time.monotonic())
                self._update_interest()
            return self._status()
        if action == 'macro_preferences':
            value = payload.get('editing_conflicts')
            if value not in ('newest', 'allow_multiple'):
                raise ValueError('Choose newest or allow_multiple for editing conflicts.')
            with self.lock:
                self.engine.editing_conflicts = value
                self._persist_macro_workspace()
            return self._status()
        if action == 'macro_warning':
            if self.account_id is None:
                raise PermissionError('Sign in to review macro access.')
            path = self.data_dir / f'macro-warning-{self.account_id}.json'
            if payload.get('acknowledge') is True:
                atomic_json(path, {'version': 1, 'acknowledged': True})
            return {'acknowledged': self._read_json(path.name, {}).get('version') == 1}
        if action == 'loadout_list':
            return {'loadouts': self._loadouts()}
        if action == 'loadout_save':
            name = payload.get('name')
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
                raise ValueError('Choose a loadout name of 1–80 characters.')
            with self.lock:
                macros = {kind: engine.config.copy() for kind, engine in self.engine.instances.items()}
            appearance = {'animations_enabled': True, 'lightweight': False,
                          'reduced_motion': False, 'accent': '#9A82F7', 'surface': '#111318',
                          'text_color': '#F2F0EA', 'muted_color': '#AAA9AD'} | self._read_json('theme.json', {})
            row = {'id': uuid.uuid4().hex, 'name': name.strip(), 'macros': macros, 'appearance': appearance,
                   'editing_conflicts': self.engine.editing_conflicts}
            self._validated_loadout(row)
            rows = self._loadouts()
            if len(rows) >= 30:
                raise ValueError('Maximum 30 loadouts per account.')
            atomic_json(self._loadout_path(), rows + [row])
            return row
        if action in ('loadout_preview', 'loadout_apply', 'loadout_delete'):
            identifier = payload.get('id')
            if not isinstance(identifier, str):
                raise ValueError('Choose a loadout.')
            rows = self._loadouts()
            selected = next((row for row in rows if row.get('id') == identifier), None)
            if selected is None:
                raise ValueError('Loadout not found.')
            if action == 'loadout_delete':
                atomic_json(self._loadout_path(), [row for row in rows if row is not selected])
                return {'deleted': True}
            configs, appearance = self._validated_loadout(selected)
            if action == 'loadout_preview':
                return {'id': identifier, 'name': selected['name'], 'macros': list(configs),
                        'appearance': appearance, 'editing_conflicts': selected.get('editing_conflicts', 'newest')}
            policy = selected.get('editing_conflicts', 'newest')
            if policy not in ('newest', 'allow_multiple'):
                raise ValueError('Invalid editing conflict setting.')
            replacement = MacroCoordinator(self.platform)
            replacement.set_authorization(self.permissions, self.deadline)
            for kind, config in configs.items():
                replacement.configure(kind, config)
            replacement.editing_conflicts = policy
            atomic_json(self.data_dir / 'theme.json', appearance)
            with self.lock:
                self.engine.stop('Loadout changed; enable explicitly')
                self.engine = replacement
                self._persist_macro_workspace()
                self._drain()
                self._update_interest()
            return self._status() | {'appearance': appearance, 'loadout': selected['name']}
        if action == 'settings_preview':
            values = {'preset': payload.get('preset', 'performance'), 'target_fps': payload.get('target_fps', 144), 'advanced': payload.get('advanced', {})}
            self._require('performance', values)
            if values['preset'] == 'potato':
                self._require('potato', values)
            if values['advanced'] or values['preset'] == 'custom':
                self._require('advanced', values)
            return self.settings.preview(**values)
        if action == 'settings_apply':
            with self.lock:
                generation = self.authorization_generation
            plan = self.settings.get_plan(payload.get('plan_id'))['public']
            values = {key: plan[key] for key in ('preset', 'target_fps', 'advanced')}
            self._require('performance', values)
            if plan['feature'] == 'potato':
                self._require('potato', values)
            if plan['requires_advanced']:
                self._require('advanced', values)
            requirements = [('performance', values)]
            if plan['feature'] == 'potato':
                requirements.append(('potato', values))
            if plan['requires_advanced']:
                requirements.append(('advanced', values))
            return self.settings.apply(plan['plan_id'], guard=self._write_guard(generation, requirements))
        if action == 'windows_settings':
            self._require('performance')
            page = payload.get('page')
            if page not in WINDOWS_PAGES:
                raise ValueError('Unknown Windows settings page.')
            if os.name != 'nt':
                raise OSError('Windows Settings requires Windows.')
            os.startfile(WINDOWS_PAGES[page])
            return {'opened': page, 'message': 'Review and change this option manually in Windows Settings. Sacred Tweaks did not change a system value.'}
        if action == 'filter_get':
            self._require('filter_keys')
            return self._filter().get()
        if action == 'filter_apply':
            with self.lock:
                generation = self.authorization_generation
                self._require('filter_keys', payload)
            return self._filter().apply(payload, guard=self._write_guard(generation, [('filter_keys', payload)]))
        if action in ('workspace_get', 'workspace_save'):
            self._require()
            key = payload.get('key')
            if key not in WORKSPACE_KEYS:
                raise ValueError('Unknown workspace section.')
            path = self.data_dir / f'workspace-{key}.json'
            if action == 'workspace_get':
                value = self._read_json(path.name, {})
                return {'key': key, 'value': value if isinstance(value, dict) else {}}
            value = payload.get('value')
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False) if isinstance(value, dict) else None
            limit = WORKSPACE_LIMITS.get(key, WORKSPACE_MAX_BYTES)
            if encoded is None or len(encoded.encode('utf-8')) > limit:
                raise ValueError(f'Saved page data must be an object under {limit // 1024} KB.')
            atomic_json(path, value)
            return {'key': key, 'saved': True}
        if action == 'system_extras':
            self._require()
            return {'startup': startup_apps(), 'heavy': running_heavy_apps(), 'display': display_modes()}
        if action == 'heavy_apps':
            self._require()
            return {'heavy': running_heavy_apps()}
        if action == 'data_bundle':
            self._require()
            workspace = {}
            for key in sorted(WORKSPACE_KEYS):
                value = self._read_json(f'workspace-{key}.json', {})
                if isinstance(value, dict) and value:
                    workspace[key] = value
            return {'format': 'sacred-local-data', 'version': 1, 'exported_at': time.time(), 'workspace': workspace,
                    'theme': self._read_json('theme.json', {}), 'overlay': self._read_json('overlay-preferences.json', {})}
        if action == 'data_restore':
            self._require()
            bundle = payload.get('bundle')
            if not isinstance(bundle, dict) or bundle.get('format') != 'sacred-local-data' or bundle.get('version') != 1:
                raise ValueError('This is not a Sacred Tweaks data backup.')
            workspace = bundle.get('workspace', {})
            if not isinstance(workspace, dict) or not set(workspace) <= WORKSPACE_KEYS:
                raise ValueError('The backup contains unknown sections.')
            restored = []
            for key, value in workspace.items():
                self._call('workspace_save', {'key': key, 'value': value})
                restored.append(key)
            theme = bundle.get('theme')
            if isinstance(theme, dict) and theme:
                self._call('theme', theme)
                restored.append('appearance')
            overlay = bundle.get('overlay')
            if isinstance(overlay, dict) and overlay:
                from .desktop_overlay import valid_preferences
                atomic_json(self.data_dir / 'overlay-preferences.json', valid_preferences(overlay))
                restored.append('overlay')
            return {'restored': restored}
        if action in ('crash_report', 'crash_clear'):
            path = self.data_dir / 'last-crash.txt'
            if action == 'crash_clear':
                path.unlink(missing_ok=True)
                return {'cleared': True}
            try:
                return {'report': path.read_text('utf-8')[-6000:]}
            except OSError:
                return {'report': None}
        if action == 'updater_channel':
            self._require('beta')
            channel = payload.get('channel')
            if channel not in ('stable', 'beta'):
                raise ValueError('Choose the stable or beta channel.')
            atomic_json(self.data_dir / 'updater.json', {'channel': channel})
            return {'channel': channel}
        if action == 'system_live':
            self._require()
            ram = None
            if os.name == 'nt':
                try:
                    ram = memory_info()['usage_percent']
                except OSError:
                    pass
            return {**self.live_cpu.sample(), 'ram_usage_percent': ram, 'sampled_at': time.time()}
        if action == 'measurements':
            self._require('measurements')
            return {'measurements': self._read_json('measurements.json', []), 'procedure': PROCEDURE,
                    'limitations': ['FPS and frame times are manual observations; no automatic capture adapter is installed.',
                                    'GPU utilization and input latency are unavailable. CPU/RAM are system-wide, not Fortnite-specific. CPU is averaged between saved observations.']}
        if action == 'measurement_save':
            self._require('measurements', payload)
            name = payload.get('name', '')
            notes = payload.get('notes', '')
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or not isinstance(notes, str) or len(notes) > 4000:
                raise ValueError('Use a measurement name of 1–100 characters and notes up to 4000 characters.')
            metrics = {}
            for key in ('fps', 'frame_time_ms'):
                value = payload.get(key)
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 10000):
                    raise ValueError(f'{key} must be a positive finite number, or omitted.')
                metrics[key] = value
            ram = None
            if os.name == 'nt':
                try:
                    ram = memory_info()['usage_percent']
                except OSError:
                    pass
            record = {'id': uuid.uuid4().hex, 'created_at': time.time(), 'name': name.strip(), 'notes': notes, **metrics,
                      'source': 'manual_observation', **self.cpu.sample(), 'gpu_usage_percent': None, 'ram_usage_percent': ram,
                      'limitations': 'GPU/FPS/frame-time automatic capture unavailable. CPU/RAM are system-wide. User-supplied FPS/frame time observations are not validated.'}
            existing = self._read_json('measurements.json', [])
            atomic_json(self.data_dir / 'measurements.json', (existing + [record])[-1000:])
            return record
        if action == 'theme':
            values = {'animations_enabled': payload.get('animations_enabled', float(payload.get('intensity', 1.0)) > 0),
                      'lightweight': payload.get('lightweight', False), 'accent': payload.get('accent', '#9b5cff'),
                      'surface': payload.get('surface', '#111318'),
                      'text_color': payload.get('text_color', '#F2F0EA'), 'muted_color': payload.get('muted_color', '#AAA9AD')}
            self._require('themes', values)
            if type(values['lightweight']) is not bool or type(values['animations_enabled']) is not bool:
                raise ValueError('Animation and lightweight settings must be enabled or disabled.')
            if any(not isinstance(values[key], str) or not re.fullmatch('#[A-Fa-f0-9]{6}', values[key]) for key in ('accent','surface','text_color','muted_color')):
                raise ValueError('Theme colors must be six-digit hex colors.')
            values['reduced_motion'] = payload.get('reduced_motion') is True
            values['glass'] = payload.get('glass', False)
            values['preset'] = payload.get('preset', 'custom')
            values['sounds'] = payload.get('sounds', True)
            if type(values['sounds']) is not bool:
                raise ValueError('Interface sounds must be enabled or disabled.')
            values['particles'] = payload.get('particles', 'stardust')
            values['particle_density'] = payload.get('particle_density', 50)
            values['font'] = payload.get('font', 'system')
            if (values['particles'] not in PARTICLE_STYLES or values['font'] not in FONTS
                    or type(values['particle_density']) is not int or not 10 <= values['particle_density'] <= 100):
                raise ValueError('Choose a listed particle style, density and font.')
            values['sound_pack'] = payload.get('sound_pack', 'soft')
            values['sound_volume'] = payload.get('sound_volume', 70)
            values['layout'] = payload.get('layout', 'comfortable')
            if (values['sound_pack'] not in SOUND_PACKS or values['layout'] not in LAYOUTS
                    or type(values['sound_volume']) is not int or not 0 <= values['sound_volume'] <= 100):
                raise ValueError('Choose a listed sound pack, volume and layout.')
            values['accent_cycle'] = payload.get('accent_cycle', False)
            values['text_scale'] = payload.get('text_scale', 100)
            if type(values['accent_cycle']) is not bool or type(values['text_scale']) is not int or not 85 <= values['text_scale'] <= 130:
                raise ValueError('Choose a text size between 85% and 130%.')
            if type(values['glass']) is not bool or not isinstance(values['preset'], str) or not re.fullmatch('[a-z0-9-]{1,32}', values['preset']):
                raise ValueError('Choose a listed theme and a valid glass setting.')
            atomic_json(self.data_dir / 'theme.json', values)
            return values
        if action == 'export_recovery':
            # Root bridge owns the explicit save dialog, so no secret is written
            # by an arbitrary local JSON action or echoed into logs here.
            raise ValueError('Recovery-code export must use the secure desktop save dialog.')
        raise ValueError('Unknown local action.')

    def _read_json(self, filename, default):
        path = self.data_dir / filename
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text('utf-8'))
        except (OSError, ValueError) as exc:
            raise OSError(f'Could not read saved {filename}: {exc}') from exc
