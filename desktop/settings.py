"""Conservative, explicit settings changes with per-value selective restoration.

Only observed keys in the game's existing config are touched. This is schema
validation, not a claim that an unseen Fortnite build has been certified.
"""
from __future__ import annotations

import ctypes
from contextlib import nullcontext
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

GAME_SECTION = '/Script/FortniteGame.FortGameUserSettings'
QUALITY_KEYS = ('sg.ViewDistanceQuality', 'sg.AntiAliasingQuality', 'sg.ShadowQuality',
                'sg.PostProcessQuality', 'sg.TextureQuality', 'sg.EffectsQuality',
                'sg.FoliageQuality', 'sg.ShadingQuality')


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
    _atomic_write(path, data)


def _atomic_write(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.sacred-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def replace_config(path, expected, data):
    if path.read_bytes() != expected:
        raise ValueError('Settings changed during the operation. Preview again.')
    _atomic_write(path, data)


def _decode(raw):
    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        return raw.decode('utf-16'), 'utf-16'
    return raw.decode('utf-8-sig'), 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8'


def _parse(raw):
    text, encoding = _decode(raw)
    lines, values, locations, section = text.splitlines(keepends=True), {}, {}, ''
    for index, line in enumerate(lines):
        match = re.match(r'^\s*\[([^\]]+)\]\s*(?:[;#].*)?$', line.strip())
        if match:
            section = match[1]
            continue
        match = re.match(r'^(\s*([^;#=\s]+)\s*=\s*)(.*?)(\r?\n)?$', line)
        if match:
            key = (section, match[2])
            if key in values:
                raise ValueError(f'Duplicate setting {section}/{key[1]}; resolve it in-game first.')
            values[key] = match[3].strip()
            locations[key] = (index, match[1], match[4] or '')
    return lines, values, locations, encoding


def _replace(raw, changes):
    lines, values, locations, encoding = _parse(raw)
    for key, value in changes.items():
        index, prefix, newline = locations[key]
        lines[index] = prefix + value + newline
    return ''.join(lines).encode(encoding)


def _valid(key, value):
    try:
        if key in QUALITY_KEYS:
            return re.fullmatch('[0-4]', value) is not None
        if key == 'bUseVSync':
            return value.lower() in ('true', 'false')
        number = float(value)
        return math.isfinite(number) and (0 <= number <= 1000 if key == 'FrameRateLimit' else 25 <= number <= 100)
    except (ValueError, TypeError):
        return False


class BackupStore:
    def __init__(self, data_dir):
        self.folder = Path(data_dir) / 'backups'
        self.folder.mkdir(parents=True, exist_ok=True)

    def path(self, backup_id):
        if not isinstance(backup_id, str) or not re.fullmatch('[a-f0-9]{32}', backup_id):
            raise ValueError('Invalid backup identifier.')
        return self.folder / f'{backup_id}.json'

    def create(self, kind, **data):
        result = {'id': uuid.uuid4().hex, 'kind': kind, 'created_at': time.time(), 'status': 'prepared', **data}
        self.save(result)
        return result

    def save(self, value):
        atomic_json(self.path(value['id']), value)

    def get(self, backup_id):
        return json.loads(self.path(backup_id).read_text('utf-8'))

    def list(self):
        output = []
        for path in self.folder.glob('*.json'):
            try:
                value = json.loads(path.read_text('utf-8'))
                output.append({k: value[k] for k in ('id', 'kind', 'created_at', 'status')})
            except (OSError, ValueError, KeyError):
                continue
        return sorted(output, key=lambda item: item['created_at'], reverse=True)


class SettingsManager:
    def __init__(self, data_dir, config_path=None, game_running=lambda: False, authorize=lambda: None):
        self.store = BackupStore(data_dir)
        self.config_path = Path(config_path) if config_path else Path(os.environ.get('LOCALAPPDATA', '')) / 'FortniteGame/Saved/Config/WindowsClient/GameUserSettings.ini'
        self.game_running = game_running
        self.authorize = authorize
        self.plans = {}

    def preview(self, preset='performance', target_fps=144, advanced=None):
        if preset == 'max_fps':
            preset = 'performance'
        if preset not in ('performance', 'balanced', 'potato', 'custom'):
            raise ValueError('Choose performance, balanced, potato, or custom.')
        if isinstance(target_fps, bool) or not isinstance(target_fps, (int, float)) or not 30 <= target_fps <= 1000:
            raise ValueError('Target FPS must be a number from 30 to 1000.')
        if advanced is None:
            advanced = {}
        if not isinstance(advanced, dict) or (preset == 'custom' and not advanced):
            raise ValueError('Custom controls require a nonempty settings object.')
        custom_values = {}
        for key, value in advanced.items():
            if key == 'bUseVSync':
                if type(value) is not bool:
                    raise ValueError('bUseVSync must be a boolean.')
                custom_values[(GAME_SECTION, key)] = 'True' if value else 'False'
            elif key in QUALITY_KEYS:
                if type(value) is not int or not 0 <= value <= 4:
                    raise ValueError(f'{key} must be an integer from 0 to 4.')
                custom_values[('ScalabilityGroups', key)] = str(value)
            elif key in ('FrameRateLimit', 'sg.ResolutionQuality'):
                low, high = (30, 1000) if key == 'FrameRateLimit' else (25, 100)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
                    raise ValueError(f'{key} must be a finite number from {low} to {high}.')
                if key == 'FrameRateLimit' and value != target_fps:
                    raise ValueError('FrameRateLimit must equal the target FPS to preserve enforced target values.')
                custom_values[(GAME_SECTION if key == 'FrameRateLimit' else 'ScalabilityGroups', key)] = f'{value:.6f}'
            else:
                raise ValueError(f'Unsupported advanced setting: {key}')
        if not self.config_path.is_file():
            raise FileNotFoundError('Fortnite settings not found. Launch Fortnite once and save its video settings first.')
        raw = self.config_path.read_bytes()
        _, values, _, _ = _parse(raw)
        if not any(section == GAME_SECTION for section, _ in values):
            raise ValueError('This file does not contain recognized Fortnite user settings.')
        proposed = {(GAME_SECTION, 'FrameRateLimit'): f'{target_fps:.6f}', (GAME_SECTION, 'bUseVSync'): 'False'}
        proposed.update({('ScalabilityGroups', key): ('1' if preset == 'balanced' else '0') for key in QUALITY_KEYS})
        if preset == 'potato':
            proposed[('ScalabilityGroups', 'sg.ResolutionQuality')] = '50.000000'
        if preset == 'custom':
            proposed = {}
        proposed.update(custom_values)
        changes, skipped = [], []
        for (section, key), value in proposed.items():
            current = values.get((section, key))
            if current is None or not _valid(key, current):
                skipped.append(f'{key}: absent or unsupported current value; use the in-game menu.')
            elif current != value:
                changes.append({'section': section, 'key': key, 'current': current, 'proposed': value})
        plan_id = uuid.uuid4().hex
        plan = {'plan_id': plan_id, 'preset': preset, 'feature': 'potato' if preset == 'potato' else 'performance',
                'target_fps': target_fps, 'advanced': advanced.copy(), 'requires_advanced': bool(advanced) or preset == 'custom',
                'changes': changes, 'skipped': skipped,
                'tradeoffs': ['Lower detail, shadows and effects can improve FPS; results depend on hardware.',
                              'VSync off may cause screen tearing.'] + (['50% 3D resolution is noticeably blurry.'] if preset == 'potato' else []),
                'compatibility': 'Only recognized keys already saved by this installation are eligible. New game builds are not certified; review in-game after launch.',
                'administrator_required': False, 'restart_required': True, 'game_running': self.game_running()}
        self.plans[plan_id] = {'public': plan, 'hash': hashlib.sha256(raw).hexdigest(), 'created': time.monotonic()}
        # Bound memory for a long-running window.
        if len(self.plans) > 20:
            self.plans.pop(next(iter(self.plans)))
        return plan

    def get_plan(self, plan_id):
        plan = self.plans.get(plan_id)
        if not plan or time.monotonic() - plan['created'] > 600:
            raise ValueError('Preview expired. Generate a new preview.')
        return plan

    def _closed_game(self):
        if self.game_running():
            raise ValueError('Close Fortnite before writing or restoring its settings.')

    def apply(self, plan_id, *, guard=nullcontext):
        self._closed_game()
        saved = self.get_plan(plan_id)
        plan = saved['public']
        raw = self.config_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != saved['hash']:
            raise ValueError('Settings changed since the preview. Preview again.')
        if not plan['changes']:
            return {'success': True, 'backup_id': None, 'applied': [], 'errors': [], 'restart_required': False}
        backup = self.store.create('fortnite', path=str(self.config_path.resolve()), changes=plan['changes'])
        # Original bytes are saved once for manual recovery; automatic restore
        # uses only the per-value journal and never overwrites unrelated edits.
        original = self.store.folder / f"{backup['id']}.original.ini"
        _atomic_write(original, raw)
        errors = []
        try:
            data = _replace(raw, {(c['section'], c['key']): c['proposed'] for c in plan['changes']})
            self._closed_game()
            with guard():
                self.authorize()
                replace_config(self.config_path, raw, data)
            backup['status'] = 'applied'
            self.plans.pop(plan_id, None)
        except PermissionError:
            raise
        except (OSError, ValueError) as exc:
            backup['status'] = 'apply_failed'
            errors.append(str(exc))
        try:
            self.store.save(backup)
        except OSError as exc:
            errors.append(f'Backup status update failed; original backup remains: {exc}')
        return {'success': not errors, 'backup_id': backup['id'], 'applied': plan['changes'] if backup['status'] == 'applied' else [],
                'errors': errors, 'restart_required': backup['status'] == 'applied'}

    def backups(self):
        return self.store.list()

    def restore(self, backup_id):
        self._closed_game()
        backup = self.store.get(backup_id)
        if backup['kind'] != 'fortnite' or Path(backup['path']).resolve() != self.config_path.resolve():
            raise ValueError('Backup does not belong to this Fortnite settings file.')
        raw = self.config_path.read_bytes()
        _, values, _, _ = _parse(raw)
        updates, restored, conflicts = {}, [], []
        for change in backup['changes']:
            key = (change['section'], change['key'])
            current = values.get(key)
            if current == change['proposed']:
                updates[key] = change['current']
                restored.append(change['key'])
            elif current != change['current']:
                conflicts.append(change['key'])
        errors = []
        try:
            if updates:
                self._closed_game()
                replace_config(self.config_path, raw, _replace(raw, updates))
            backup['status'] = 'partially_restored' if conflicts else 'restored'
            self.store.save(backup)
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
        return {'success': not conflicts and not errors, 'restored': restored if not errors else [], 'conflicts': conflicts, 'errors': errors}


class WindowsFilterKeys:
    class FILTERKEYS(ctypes.Structure):
        _fields_ = [('cbSize', ctypes.c_uint32), ('dwFlags', ctypes.c_uint32), ('iWaitMSec', ctypes.c_uint32),
                    ('iDelayMSec', ctypes.c_uint32), ('iRepeatMSec', ctypes.c_uint32), ('iBounceMSec', ctypes.c_uint32)]

    def __init__(self):
        if os.name != 'nt':
            raise OSError('Windows Filter Keys requires Windows.')
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.user32.SystemParametersInfoW.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        self.user32.SystemParametersInfoW.restype = ctypes.c_int

    def get(self):
        value = self.FILTERKEYS()
        value.cbSize = ctypes.sizeof(value)
        if not self.user32.SystemParametersInfoW(0x0032, value.cbSize, ctypes.byref(value), 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return {'enabled': bool(value.dwFlags & 1), 'flags': value.dwFlags, 'wait_ms': value.iWaitMSec,
                'delay_ms': value.iDelayMSec, 'repeat_ms': value.iRepeatMSec, 'bounce_ms': value.iBounceMSec}

    def set(self, value):
        flags = (value['flags'] & ~1) | int(value['enabled'])
        structure = self.FILTERKEYS(ctypes.sizeof(self.FILTERKEYS), flags, value['wait_ms'], value['delay_ms'], value['repeat_ms'], value['bounce_ms'])
        if not self.user32.SystemParametersInfoW(0x0033, structure.cbSize, ctypes.byref(structure), 3):
            raise ctypes.WinError(ctypes.get_last_error())


class FilterKeysManager:
    FIELDS = ('enabled', 'wait_ms', 'delay_ms', 'repeat_ms', 'bounce_ms')

    def __init__(self, data_dir, api=None, authorize=lambda: None):
        self.store = BackupStore(data_dir)
        self.api = api if api is not None else WindowsFilterKeys()
        self.authorize = authorize

    def get(self):
        return self.api.get() | {'available': True,
                                 'note': 'Acceptance delay, repeat delay, repeat interval and bounce filtering have different effects. Filter Keys does not universally reduce latency.'}

    def apply(self, payload, *, guard=nullcontext):
        if set(payload) - set(self.FIELDS):
            raise ValueError('Unknown Filter Keys setting.')
        before = self.api.get()
        after = before | payload
        if type(after['enabled']) is not bool:
            raise ValueError('enabled must be a boolean.')
        for key in self.FIELDS[1:]:
            if type(after[key]) is not int or not 0 <= after[key] <= 20000:
                raise ValueError(f'{key} must be an integer from 0 to 20000 milliseconds.')
        if after['bounce_ms'] and any(after[key] for key in ('wait_ms', 'delay_ms', 'repeat_ms')):
            raise ValueError('Bounce filtering cannot be combined with acceptance or repeat timings.')
        after['flags'] = (before['flags'] & ~1) | int(after['enabled'])
        backup = self.store.create('filter_keys', before=before, applied=after)
        try:
            with guard():
                self.authorize()
                self.api.set(after)
            observed = self.api.get()
            if any(observed[k] != after[k] for k in self.FIELDS):
                raise OSError('Windows did not accept the requested Filter Keys values.')
            backup['status'] = 'applied'
            self.store.save(backup)
            return {'success': True, 'backup_id': backup['id'], 'settings': observed, 'errors': []}
        except OSError as exc:
            # Keep the journal even on partial platform failure; restore is
            # compare-before-write and remains available without authorization.
            backup['status'] = 'apply_failed'
            self.store.save(backup)
            return {'success': False, 'backup_id': backup['id'], 'errors': [str(exc)]}

    def restore(self, backup_id):
        backup = self.store.get(backup_id)
        if backup['kind'] != 'filter_keys':
            raise ValueError('Not a Filter Keys backup.')
        current, restored, conflicts = self.api.get(), [], []
        result = current.copy()
        for key in self.FIELDS:
            if current[key] == backup['applied'][key]:
                result[key] = backup['before'][key]
                restored.append(key)
            elif current[key] != backup['before'][key]:
                conflicts.append(key)
        result['flags'] = (current['flags'] & ~1) | int(result['enabled'])
        # A mixed restore may create an unsupported bounce/repeat combination.
        if result['bounce_ms'] and any(result[k] for k in ('wait_ms', 'delay_ms', 'repeat_ms')):
            return {'success': False, 'restored': [], 'conflicts': conflicts, 'errors': ['Later Filter Keys changes conflict; restore manually in Windows keyboard settings.']}
        errors = []
        try:
            self.api.set(result)
            backup['status'] = 'partially_restored' if conflicts else 'restored'
            self.store.save(backup)
        except OSError as exc:
            errors.append(str(exc))
        return {'success': not conflicts and not errors, 'restored': restored if not errors else [], 'conflicts': conflicts, 'errors': errors}
