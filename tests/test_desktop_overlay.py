import tempfile
import unittest
from pathlib import Path

from desktop.desktop_overlay import DesktopOverlayController, OverlayBridge, valid_preferences


class Window:
    def __init__(self, handle):
        self.native = type('Native', (), {'Handle': type('Handle', (), {'ToInt64': lambda self: handle})()})()
        self.calls = []

    def show(self): self.calls.append('show')
    def hide(self): self.calls.append('hide')
    def evaluate_js(self, script): self.calls.append('refresh')


class Probe:
    def __init__(self):
        self.current = 1
        self.game = True
        self.pressed = False
        self.valid = {1, 2, 3}
        self.rect = (0, 0, 1920, 1080)
        self.focused = []
        self.centered = []

    def foreground(self): return self.current
    def is_game(self): return self.game
    def down(self, key): return self.pressed
    def exists(self, handle): return handle in self.valid
    def bounds(self, handle): return self.rect
    def center(self, overlay, game): self.centered.append((overlay, game))
    def focus(self, handle): self.focused.append(handle); self.current = handle; return True


class Api:
    def __init__(self):
        import threading
        self._lock = threading.RLock()
        self._clock = lambda: 10
        self._deadline = 25
        self._token = 'secret-token'
        self._session = {'user': {'username': 'Player'}, 'tier': 'Elite',
                         'expires_at': 2_000_000_000, 'permissions': {'performance': True},
                         'token': 'must-not-leak'}

    def local(self, action, payload):
        return {'ok': True, 'data': {'changes': [{'key': 'FrameRateLimit', 'current': '60', 'proposed': '144'}]}}


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.api = Api()
        self.bridge = OverlayBridge(self.api, self.tmp.name)
        self.window = Window(2)
        self.desktop = Window(3)
        self.probe = Probe()
        self.controller = DesktopOverlayController(self.window, self.desktop, self.bridge, self.probe)
        self.controller.overlay_hwnd = 2

    def test_session_exposes_only_display_information(self):
        snapshot = self.bridge.snapshot()
        self.assertEqual(snapshot['username'], 'Player')
        self.assertEqual(snapshot['license']['expires_at'], 2_000_000_000)
        self.assertNotIn('secret-token', repr(snapshot))
        self.api._deadline = 5
        self.assertFalse(self.bridge.snapshot()['signed_in'])

    def test_js_bridge_does_not_expose_app_or_controller_objects(self):
        public = {name: getattr(self.bridge, name) for name in dir(self.bridge)
                  if not name.startswith('_')}
        self.assertTrue(public)
        self.assertTrue(all(callable(value) for value in public.values()))

    def test_hotkey_opens_once_then_hides_whole_window_and_restores_game(self):
        self.probe.pressed = True
        self.controller.tick()
        self.assertTrue(self.controller.open)
        self.controller.tick()
        self.assertEqual(self.window.calls, ['show', 'refresh'])
        self.probe.pressed = False
        self.controller.tick()
        self.probe.pressed = True
        self.controller.tick()
        self.assertEqual(self.window.calls, ['show', 'refresh', 'refresh', 'hide'])
        self.assertEqual(self.probe.focused[-1], 1)
        self.probe.pressed = False
        self.probe.current, self.probe.game = 3, False
        self.controller.tick()
        self.probe.pressed = True
        self.controller.tick()
        self.assertEqual(self.window.calls, ['show', 'refresh', 'refresh', 'hide'])

    def test_alt_tab_restart_and_window_bounds(self):
        self.probe.pressed = True
        self.controller.tick()
        self.probe.current, self.probe.game = 3, False
        self.controller.tick()
        self.assertFalse(self.controller.open)
        self.assertEqual(self.window.calls, ['show', 'refresh', 'hide'])
        self.probe.valid.remove(1)
        self.probe.pressed = False
        self.controller.tick()
        self.probe.current, self.probe.game = 4, True
        self.probe.valid.add(4)
        self.probe.pressed = True
        self.controller.tick()
        self.assertEqual(self.controller.game_hwnd, 4)
        self.probe.rect = (0, 0, 2560, 1440)
        self.controller.tick()
        self.assertIn((2, 4), self.probe.centered)
        self.assertEqual(self.controller.last_bounds, (0, 0, 2560, 1440))

    def test_preferences_persist_and_reject_bad_values(self):
        values = self.bridge.save_preferences({'hotkey': 'F9', 'accent': 'blue', 'opacity': 82,
                                               'reduced_motion': True})
        self.assertEqual(OverlayBridge(self.api, self.tmp.name).preferences(), values)
        self.assertTrue(Path(self.tmp.name, 'overlay-preferences.json').exists())
        with self.assertRaises(ValueError): valid_preferences({'hotkey': 'F8'})
        with self.assertRaises(ValueError): valid_preferences({'opacity': True})


if __name__ == '__main__':
    unittest.main()
