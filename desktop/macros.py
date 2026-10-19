# Copyright (c) 2026 Sacred LLC. All rights reserved. See LICENSE.
"""Deterministic, nonblocking macro state machine. No keyboard history is kept.

The driver feeds only activation/emergency events and monotonic times. Every
synthetic press is tracked so cancellation can release it. Single-edit taps
finish the current three-tap cycle; release cancels repetition. Safety stops
cancel the entire cycle. Timing is best effort, never a real-time guarantee.
"""
from __future__ import annotations
import math

DEFAULT_CONFIG = {
    'activation': 'F', 'edit': 'E', 'select': 'MOUSE1', 'confirm': 'E',
    'emergency': 'F8', 'toggle': 'F9', 'step_delay_ms': 20, 'repeat_ms': 150, 'press_ms': 15,
    'confirm_mode': 'manual', 'game_auto_confirm': False,
}
KEY_CODES = {**{chr(n): n for n in range(65, 91)},
             **{str(n): 48 + n for n in range(10)},
             **{f'F{n}': 111 + n for n in range(1, 25)},
             'SPACE': 0x20, 'TAB': 0x09, 'ENTER': 0x0D, 'ESC': 0x1B,
             'SHIFT': 0x10, 'CTRL': 0x11, 'ALT': 0x12,
             'LEFT': 0x25, 'UP': 0x26, 'RIGHT': 0x27, 'DOWN': 0x28,
             'INSERT': 0x2D, 'DELETE': 0x2E, 'HOME': 0x24, 'END': 0x23,
             'PAGEUP': 0x21, 'PAGEDOWN': 0x22, 'BACKSPACE': 0x08,
             'MOUSE1': 1, 'MOUSE2': 2, 'MOUSE3': 4, 'MOUSE4': 5, 'MOUSE5': 6}


# Each entry describes ordinary input requests, not verified game outcomes.
EXTENDED_DEFAULTS = {
    'prefire': {'fire':'MOUSE1', 'wall':'Q', 'place':'K'},
    'pickup': {'interact':'E'},
    'wall_replace': {'pickaxe':'1', 'fire':'MOUSE1', 'wall':'Q', 'place':'K'},
    'auto_build': {'wall':'Q', 'stair':'V', 'floor':'X', 'cone':'C', 'place':'K'},
    'mantle': {'jump':'SPACE'},
    'quick_reset': {'edit':'E', 'reset':'MOUSE2', 'confirm':'E'},
    'floor_cone': {'floor':'X', 'cone':'C', 'place':'K'},
    'double_edit': {'floor':'X', 'cone':'C', 'place':'K', 'edit':'E', 'select':'MOUSE1', 'confirm':'E',
                    'first_dx':0, 'first_dy':0, 'second_dx':0, 'second_dy':0, 'trigger_mode':'tap'},
    'gun_pullout': {'weapon':'2'},
}
COMMON_EXTENDED = {'activation':'F', 'emergency':'F8', 'toggle':'F9', 'step_delay_ms':50, 'repeat_ms':100, 'press_ms':15}
DEFAULT_TOGGLES = {'single_edit':'F9', 'drag':'F10', 'prefire':'F11', 'pickup':'F12',
                   'wall_replace':'F13', 'auto_build':'F14', 'mantle':'F15',
                   'quick_reset':'F16', 'floor_cone':'F17', 'double_edit':'F18',
                   'gun_pullout':'F19'}


def validate_extended(kind, config):
    result = COMMON_EXTENDED | EXTENDED_DEFAULTS[kind]
    result['toggle'] = DEFAULT_TOGGLES[kind]
    if set(config) - set(result):
        raise ValueError('Unknown macro setting.')
    result.update(config)
    for key, value in result.items():
        if key == 'trigger_mode':
            if value not in ('tap', 'hold'):
                raise ValueError('Trigger mode must be tap or hold.')
        elif key.endswith(('_dx', '_dy')):
            if type(value) is not int or not -500 <= value <= 500:
                raise ValueError(f'{key} must be an integer from -500 to 500.')
        elif key.endswith('_ms'):
            minimum = 30 if key == 'repeat_ms' else 5
            if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or not minimum <= value <= 10000:
                raise ValueError(f'{key} must be finite and between {minimum} and 10000 ms.')
        else:
            result[key] = normalize_key(value)
    bindings = {k:v for k,v in result.items() if not k.endswith(('_ms', '_dx', '_dy')) and k != 'trigger_mode'}
    if any(v == result['emergency'] for k,v in bindings.items() if k != 'emergency'):
        raise ValueError('Emergency shortcut must differ from all other bindings.')
    if result['toggle'] == result['activation'] or any(result['toggle'] == result[k] for k in EXTENDED_DEFAULTS[kind]):
        raise ValueError('Toggle shortcut must differ from activation and output bindings.')
    if kind == 'auto_build':
        pieces = [result[k] for k in ('wall','stair','floor','cone')]
        if len(set(pieces)) != 4 or result['place'] in pieces:
            raise ValueError('Use four different piece bindings and a separate secondary place binding.')
    elif any(result['activation']==result[k] for k in EXTENDED_DEFAULTS[kind] if not k.endswith(('_dx', '_dy')) and k != 'trigger_mode'):
        raise ValueError('Use a separate activation key for this macro.')
    return result


def normalize_key(key):
    if not isinstance(key, str) or key.upper().strip() not in KEY_CODES:
        raise ValueError('Use A–Z, 0–9, F1–F24, a named navigation key, or MOUSE1–MOUSE5.')
    return key.upper().strip()


def validate_config(kind, config):
    if kind in EXTENDED_DEFAULTS and isinstance(config, dict):
        return validate_extended(kind, config)
    if kind not in ('single_edit', 'drag') or not isinstance(config, dict):
        raise ValueError('Unknown macro configuration.')
    if set(config) - set(DEFAULT_CONFIG):
        raise ValueError('Unknown macro setting.')
    result = DEFAULT_CONFIG | config
    if 'toggle' not in config:
        result['toggle'] = DEFAULT_TOGGLES[kind]
    for key in ('activation', 'edit', 'select', 'confirm', 'emergency', 'toggle'):
        result[key] = normalize_key(result[key])
    if kind == 'drag':
        result['activation'] = result['edit']
    for key, minimum, maximum in (('step_delay_ms', 5, 1000), ('repeat_ms', 30, 10000), ('press_ms', 5, 100)):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum:
            raise ValueError(f'{key} must be between {minimum} and {maximum} milliseconds.')
    if result['repeat_ms'] < 2 * result['step_delay_ms'] + 10:
        raise ValueError('Repeat interval must exceed the complete cycle by at least 10 ms.')
    if type(result['game_auto_confirm']) is not bool or result['confirm_mode'] not in ('auto', 'manual'):
        raise ValueError('Invalid confirmation settings.')
    if result['emergency'] in {result[k] for k in ('activation', 'edit', 'select', 'confirm')}:
        raise ValueError('Emergency shortcut must differ from activation and output bindings.')
    if result['toggle'] in {result[k] for k in ('activation', 'edit', 'select', 'confirm', 'emergency')}:
        raise ValueError('Toggle shortcut must differ from activation and output bindings.')
    if result['select'] in (result['edit'], result['confirm'], result['activation']):
        raise ValueError('Select must differ from edit, confirm and activation bindings.')
    if result['game_auto_confirm'] and (kind == 'single_edit' or result['confirm_mode'] == 'auto'):
        raise ValueError('Disable in-game automatic confirmation for explicit confirm, or use Drag Manual Confirm.')
    return result


class MacroEngine:
    def __init__(self, sink):
        self.sink = sink
        self.kind = 'single_edit'
        self.config = DEFAULT_CONFIG.copy()
        self.enabled = False
        self.authorized = False
        self.deadline = 0.0
        self.pressed = False
        self.held = set()
        self.phase = None
        self.due = 0.0
        self.cycle_start = 0.0
        self.reason = 'Disabled after login'
        self.release_errors = []
        self.build_keys = set()
        self.sequence = []
        self.pulse_key = None
        self.pulse_due = 0.0
        self.completed = 0
        self._pending_completion = False

    def activation_keys(self):
        if self.kind == 'gun_pullout':
            return set()
        return {self.config[k] for k in ('wall','stair','floor','cone')} if self.kind == 'auto_build' else {self.config['activation']}

    def set_authorization(self, authorized, deadline):
        self.authorized, self.deadline = bool(authorized), deadline
        if not authorized:
            self.stop('Authorization unavailable')

    def configure(self, kind, config):
        self.stop('Configuration changed; enable explicitly')
        candidate = validate_config(kind, config)
        self.kind, self.config = kind, candidate

    def enable(self, enabled, now):
        self.stop('Disabled')
        if enabled:
            if not self.authorized or now >= self.deadline:
                raise PermissionError('Authorization expired. Sign in again.')
            if self.held:
                raise OSError('An input release failed; retry emergency stop before enabling.')
            self.enabled, self.reason = True, 'Ready; foreground Fortnite required'

    def _down(self, key):
        # Record before calling the platform; a partial/uncertain failure still
        # requires a best-effort release during the driver's stop path.
        self.held.add(key)
        self.sink.down(key)

    def _up(self, key):
        self.sink.up(key)
        self.held.discard(key)

    def _tap(self, key, now):
        self._down(key)
        self.pulse_key = key
        self.pulse_due = now + self.config['press_ms'] / 1000

    def stop(self, reason='Stopped'):
        self.enabled = self.pressed = False
        self.phase = None
        self.sequence = []
        self.pulse_key = None
        self._pending_completion = False
        self.build_keys.clear()
        self.reason = reason
        self.release_errors = []
        for key in tuple(self.held):
            try:
                self._up(key)
            except Exception as exc:
                self.release_errors.append(f'{key}: {exc}')

    def _safe(self, now, foreground):
        if not self.authorized or now >= self.deadline:
            if self.enabled or self.held:
                self.stop('Authorization expired')
            return False
        if not foreground:
            if self.pressed or self.phase or self.held:
                self.stop('Fortnite lost focus; enable explicitly')
            return False
        return self.enabled

    def input(self, key, down, now, foreground, injected=False):
        if injected:
            return
        if key == self.config['emergency'] and down:
            self.stop('Emergency stop')
            return
        # Unrelated key events are not recorded, stored, or exported.
        if key not in self.activation_keys() or not self._safe(now, foreground):
            return
        if self.kind in EXTENDED_DEFAULTS:
            self._extended_input(key, down, now)
            return
        if down:
            if self.pressed or self.phase not in (None, 'repeat'):
                return  # Ignore keyboard autorepeat, overlapping cycles.
            self.pressed = True
            if self.kind == 'drag':
                self._down(self.config['select'])
            else:
                self._start(now)
        else:
            was_pressed, self.pressed = self.pressed, False
            if self.kind == 'drag' and was_pressed:
                self._up(self.config['select'])
                if self.config['confirm_mode'] == 'auto' and not self.config['game_auto_confirm']:
                    self._tap(self.config['confirm'], now)
                    self._pending_completion = True
                else:
                    self.completed += 1
            elif self.phase == 'repeat':
                self.phase = None

    def _extended_input(self, key, down, now):
        if self.kind == 'auto_build':
            if down and key not in self.build_keys:
                if not self.build_keys:
                    self._down(self.config['place'])
                self.build_keys.add(key)
            elif not down:
                self.build_keys.discard(key)
                if not self.build_keys and self.config['place'] in self.held:
                    self._up(self.config['place'])
            self.pressed = bool(self.build_keys)
            return
        if down:
            if self.pressed or self.phase or self.pulse_key:
                return
            self.pressed = True
            self._extended_start(now)
        else:
            self.pressed = False
            if self.kind in ('pickup', 'mantle'):
                self.phase = None
            elif self.kind == 'double_edit' and self.config['trigger_mode'] == 'hold':
                self.phase = None
                self.sequence = []
                self.pulse_key = None
                self._pending_completion = False
                for held in tuple(self.held):
                    self._up(held)

    def _extended_start(self, now):
        if self.kind == 'double_edit':
            c = self.config
            self.sequence = [c['floor'], c['place'], c['cone'], c['place'],
                             c['edit'], ('down', c['select']), ('move', c['first_dx'], c['first_dy']),
                             ('up', c['select']), c['confirm'], c['edit'],
                             ('down', c['select']), ('move', c['second_dx'], c['second_dy']),
                             ('up', c['select']), c['confirm']]
            self._sequence_step(now)
            return
        outputs = {
            'prefire': ('fire','wall','place'),
            'wall_replace': ('pickaxe','fire','wall','place'),
            'quick_reset': ('edit','reset','confirm'),
            'floor_cone': ('floor','place','cone','place'),
            'gun_pullout': ('weapon',),
            'pickup': ('interact',), 'mantle': ('jump',),
        }[self.kind]
        self.sequence = [self.config[k] for k in outputs]
        self._sequence_step(now)

    def _sequence_step(self, now):
        step = self.sequence.pop(0)
        if isinstance(step, tuple):
            if step[0] == 'down':
                self._down(step[1])
            elif step[0] == 'up':
                self._up(step[1])
            elif step[1] or step[2]:
                self.sink.move(step[1], step[2])
        else:
            self._tap(step, now)
        if self.sequence:
            self.phase, self.due = 'sequence', now + self.config['step_delay_ms']/1000
        elif (self.kind in ('pickup', 'mantle') or (self.kind == 'double_edit' and self.config['trigger_mode'] == 'hold')) and self.pressed:
            self.phase, self.due = 'extended_repeat', now + self.config['repeat_ms']/1000
        else:
            self.phase = None
            if self.kind in EDITING_KINDS:
                self._pending_completion = True

    def _start(self, now):
        self.cycle_start = now
        self._tap(self.config['edit'], now)
        self.phase, self.due = 'select', now + self.config['step_delay_ms'] / 1000

    def tick(self, now, foreground):
        if not self.enabled and self.held:
            self.stop(self.reason)  # Retry a transient rejected release without resuming.
        if not self._safe(now, foreground):
            return
        if self.pulse_key is not None:
            if now < self.pulse_due:
                return
            self._up(self.pulse_key)
            self.pulse_key = None
            if self._pending_completion:
                self.completed += 1
                self._pending_completion = False
        if self.phase is None or now < self.due:
            return
        # Process one phase per tick. A late scheduler must not burst/catch up.
        if self.phase == 'sequence':
            self._sequence_step(now)
        elif self.phase == 'extended_repeat':
            if self.pressed:
                self._extended_start(now)
            else:
                self.phase = None
        elif self.phase == 'select':
            self._tap(self.config['select'], now)
            self.phase, self.due = 'confirm', now + self.config['step_delay_ms'] / 1000
        elif self.phase == 'confirm':
            self._tap(self.config['confirm'], now)
            self._pending_completion = True
            self.phase = 'repeat' if self.pressed else None
            self.due = max(now + .01, self.cycle_start + self.config['repeat_ms'] / 1000)
        elif self.phase == 'repeat':
            if self.pressed:
                self._start(now)
            else:
                self.phase = None

    def status(self):
        return {'kind': self.kind, 'config': self.config.copy(), 'enabled': self.enabled,
                'active': self.pressed or self.phase is not None or self.pulse_key is not None, 'reason': self.reason,
                'held_inputs': sorted(self.held), 'release_errors': self.release_errors.copy()}


EDITING_KINDS = frozenset({'single_edit', 'drag', 'quick_reset', 'double_edit'})


class _OwnedSink:
    def __init__(self, coordinator, kind):
        self.coordinator, self.kind = coordinator, kind

    def down(self, key):
        owners = self.coordinator._owners.setdefault(key, set())
        if self.kind not in owners:
            first = not owners
            owners.add(self.kind)
            if first:
                self.coordinator.sink.down(key)

    def up(self, key):
        owners = self.coordinator._owners.get(key)
        if owners and self.kind in owners:
            if len(owners) == 1:
                self.coordinator.sink.up(key)
                del self.coordinator._owners[key]
            else:
                owners.remove(self.kind)

    def move(self, dx, dy):
        self.coordinator.sink.move(dx, dy)


class MacroCoordinator:
    """Independent enable states with one physical owner set per synthetic key."""
    def __init__(self, sink):
        self.sink = sink
        self.instances = {}
        self._owners = {}
        self.permissions = {}
        self.deadline = 0.0
        self.kind = 'single_edit'
        self.editing_conflicts = 'newest'
        self._toggle_down = set()
        self._pending_gun_due = None
        self.configure('single_edit', {})

    @property
    def config(self):
        return self.instances[self.kind].config

    @property
    def enabled(self):
        return any(engine.enabled for engine in self.instances.values())

    @property
    def held(self):
        return set(self._owners)

    def activation_keys(self):
        return {key for engine in self.instances.values() for key in (engine.activation_keys() | {engine.config['toggle']})}

    def set_authorization(self, permissions, deadline):
        self.permissions = permissions if isinstance(permissions, dict) else {self.kind: bool(permissions)}
        self.deadline = deadline
        for kind, engine in self.instances.items():
            engine.set_authorization(self.permissions.get(kind) is True, deadline)

    def configure(self, kind, config):
        candidate = validate_config(kind, config)
        for other_kind, engine in self.instances.items():
            if other_kind != kind and candidate['toggle'] == engine.config['toggle']:
                raise ValueError('Each configured macro needs a distinct toggle shortcut.')
        if kind in self.instances:
            self.instances[kind].stop('Configuration changed; enable explicitly')
        engine = MacroEngine(_OwnedSink(self, kind))
        engine.configure(kind, candidate)
        engine.set_authorization(self.permissions.get(kind) is True, self.deadline)
        self.instances[kind] = engine
        self.kind = kind

    def enable(self, kind, enabled, now):
        engine = self.instances[kind]
        if enabled:
            for other_kind, other in self.instances.items():
                if (other_kind != kind and other.enabled and engine.activation_keys() & other.activation_keys()
                        and not (self.editing_conflicts == 'newest' and kind in EDITING_KINDS and other_kind in EDITING_KINDS)):
                    raise ValueError(f'{kind.replace("_", " ")} shares an activation bind with {other_kind.replace("_", " ")}. Choose separate bindings.')
        if enabled and self.editing_conflicts == 'newest' and kind in EDITING_KINDS:
            for other_kind, other in self.instances.items():
                if other_kind != kind and other_kind in EDITING_KINDS and other.enabled:
                    other.stop(f'Disabled when {kind.replace("_", " ")} was enabled')
        engine.enable(enabled, now)

    def stop(self, reason='Stopped'):
        for engine in self.instances.values():
            engine.stop(reason)
        self._toggle_down.clear()
        self._pending_gun_due = None

    def _edit_finished(self, kind, previous_completed, now):
        if (kind in EDITING_KINDS and self.instances[kind].completed > previous_completed
                and 'gun_pullout' in self.instances and self.instances['gun_pullout'].enabled):
            self._pending_gun_due = now + self.instances['gun_pullout'].config['step_delay_ms'] / 1000

    def _outputs(self, engine):
        return {value for key, value in engine.config.items()
                if key not in ('activation', 'toggle', 'emergency', 'trigger_mode', 'confirm_mode', 'game_auto_confirm')
                and not key.endswith(('_ms', '_dx', '_dy'))}

    def input(self, key, down, now, foreground, injected=False):
        if injected:
            return
        if down and any(key == e.config['emergency'] for e in self.instances.values()):
            self.stop('Emergency stop')
            return
        for kind, engine in self.instances.items():
            if key == engine.config['toggle']:
                if down and key not in self._toggle_down and foreground:
                    self._toggle_down.add(key)
                    self.enable(kind, not engine.enabled, now)
                elif not down:
                    self._toggle_down.discard(key)
                return
        for kind, engine in self.instances.items():
            if key not in engine.activation_keys() or not engine.enabled:
                continue
            if down and any(other_kind != kind and other.status()['active'] and self._outputs(other) & self._outputs(engine)
                            for other_kind, other in self.instances.items()):
                engine.reason = 'Skipped: another macro is using these inputs'
                return
            previous_completed = engine.completed
            engine.input(key, down, now, foreground)
            self._edit_finished(kind, previous_completed, now)

    def tick(self, now, foreground):
        if not foreground:
            self._pending_gun_due = None
        for kind, engine in self.instances.items():
            previous_completed = engine.completed
            engine.tick(now, foreground)
            if foreground:
                self._edit_finished(kind, previous_completed, now)
        if self._pending_gun_due is not None and now >= self._pending_gun_due:
            self._pending_gun_due = None
            gun = self.instances.get('gun_pullout')
            if foreground and gun and gun.enabled and gun.authorized and now < gun.deadline:
                gun._extended_start(now)

    def status(self):
        current = self.instances[self.kind].status()
        return current | {'enabled': self.enabled, 'macros': {kind: engine.status() for kind, engine in self.instances.items()},
                          'editing_conflicts': self.editing_conflicts, 'held_inputs': sorted(self.held)}
