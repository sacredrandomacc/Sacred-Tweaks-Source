import tempfile
import unittest
from pathlib import Path

from desktop.desktop_overlay import DesktopOverlayController, OverlayBridge, layout_rect, valid_preferences


class Window:
    def __init__(self, handle):
        self.native = type('Native', (), {'Handle': type('Handle', (), {'ToInt64': lambda self: handle})()})()
        self.calls = []
        self.resizes = []

    def show(self): self.calls.append('show')
    def hide(self): self.calls.append('hide')
    def evaluate_js(self, script): self.calls.append('refresh')
    def resize(self, width, height): self.resizes.append((width, height))


class Probe:
    def __init__(self):
        self.current = 1
        self.game = True
        self.pressed = False
        self.valid = {1, 2, 3}
        self.rect = (0, 0, 1920, 1080)
        self.focused = []
        self.centered = []
        self.placed = []
        self.owners = {}

    def foreground(self): return self.current
    def root(self, handle): return self.owners.get(handle, handle)
    def is_game(self): return self.game
    def down(self, key): return self.pressed
    def exists(self, handle): return handle in self.valid
    def bounds(self, handle): return self.rect
    def center(self, overlay, game): self.centered.append((overlay, game))
    def place(self, overlay, rect): self.placed.append((overlay, rect))
    def prepare_passive(self, hwnd): self.passive = hwnd
    def show_passive(self, hwnd, rect): self.widget = ('shown', rect)
    def hide_passive(self, hwnd): self.widget = ('hidden', None)
    def focus(self, handle): self.focused.append(handle); self.current = handle; return True


class Api:
    def __init__(self):
        import threading
        self._lock = threading.RLock()
        self._clock = lambda: 10
        self._deadline = 25
        self._token = 'secret-token'
        self._session = {'user': {'username': 'Player'}, 'tier': 'Elite',
                         'expires_at': 2_000_000_000, 'permissions': {'performance': True, 'profiles': True},
                         'token': 'must-not-leak'}

    def local(self, action, payload):
        self.last_action, self.last_payload = action, payload
        return {'ok': True, 'data': {'changes': [{'key': 'FrameRateLimit', 'current': '60', 'proposed': '144'}]}}

    def request(self, method, path, payload=None):
        if method == 'POST':
            self.saved = payload
            return {'ok': True, 'data': {'id': payload['id']}}
        return {'ok': True, 'data': {'profiles': [
            {'id': 1, 'name': 'Practice', 'config': {'kind': 'single_edit', 'config': {'secret_bind': 'F'}}, 'created_at': 123}
        ]}}


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

    def test_live_controls_route_to_authorized_local_actions(self):
        self.api._deadline = 25
        self.bridge.macro_status()
        self.assertEqual(self.api.last_action, 'macro_status')
        self.bridge.toggle_macro('single_edit', True)
        self.assertEqual(self.api.last_action, 'macro_enable')
        self.assertEqual(self.api.last_payload, {'kind': 'single_edit', 'enabled': True})
        self.bridge.emergency_stop()
        self.assertEqual(self.api.last_action, 'emergency_stop')

    def test_overlay_hotkey_cannot_steal_macro_toggle(self):
        self.api.local = lambda action, payload: {'ok': True, 'data': {'macros': {
            'single_edit': {'config': {'toggle': 'F9'}}}}}
        with self.assertRaisesRegex(ValueError, 'macro'):
            self.bridge.save_preferences({'hotkey': 'F9'})

    def test_js_bridge_does_not_expose_app_or_controller_objects(self):
        public = {name: getattr(self.bridge, name) for name in dir(self.bridge)
                  if not name.startswith('_')}
        self.assertTrue(public)
        self.assertTrue(all(callable(value) for value in public.values()))

    def test_saved_macro_can_be_edited_without_enabling_it(self):
        profile = self.bridge.macro_profiles()['profiles'][0]
        self.assertEqual(profile['config'], {'secret_bind': 'F'})
        self.assertEqual(self.bridge.save_macro_profile(1, 'Practice 2', {'secret_bind': 'G'}), {'saved': True})
        self.assertEqual(self.api.saved, {'id': 1, 'name': 'Practice 2',
                                          'config': {'kind': 'single_edit', 'config': {'secret_bind': 'G'}}})
        with self.assertRaises(ValueError):
            self.bridge.save_macro_profile(1, 'Practice', {'secret_bind': 5})
        self.api._session['permissions']['profiles'] = False
        with self.assertRaises(ValueError):
            self.bridge.save_macro_profile(1, 'Practice', {'secret_bind': 'F'})

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

    def test_overlay_dropdown_popup_does_not_close_menu(self):
        self.probe.pressed = True
        self.controller.tick()
        self.probe.pressed = False
        self.probe.owners[5] = 2  # WebView2 <select> popup owned by the overlay.
        self.probe.current, self.probe.game = 5, False
        self.controller.tick()
        self.assertTrue(self.controller.open)
        self.assertNotIn('hide', self.window.calls)

    def test_companion_reads_validated_app_theme(self):
        import json
        target = Path(self.tmp.name) / 'theme.json'
        self.assertIsNone(self.bridge.app_theme())
        target.write_text(json.dumps({'accent': '#22D3EE', 'surface': '#0B1719', 'text_color': '#E8FAFB',
                                      'muted_color': '#9DBDC0', 'glass': True}))
        self.assertEqual(self.bridge.app_theme()['accent'], '#22D3EE')
        self.assertTrue(self.bridge.app_theme()['glass'])
        target.write_text(json.dumps({'accent': 'red;}', 'surface': '#0B1719', 'text_color': '#E8FAFB', 'muted_color': '#9DBDC0'}))
        self.assertIsNone(self.bridge.app_theme())
        self.assertEqual(self.bridge.preferences()['accent'], 'app')

    def test_widget_bar_shows_only_in_game_and_never_with_menu(self):
        self.controller.attach_widget(9)
        self.assertEqual(self.probe.passive, 9)
        self.controller.tick()
        self.assertFalse(hasattr(self.probe, 'widget'))  # Off by default.
        self.bridge._values['widgets'] = True
        self.controller.tick()
        self.assertEqual(self.probe.widget[0], 'shown')
        self.probe.pressed = True
        self.controller.tick()  # Menu opens: widget hides.
        self.assertEqual(self.probe.widget[0], 'hidden')
        self.bridge.set_timer(True, 1000)
        self.assertGreaterEqual(self.bridge.widget_state()['timer']['elapsed_ms'], 1000)
        with self.assertRaises(ValueError):
            self.bridge.set_timer('yes', -5)

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
        self.assertIn((2, layout_rect((0, 0, 2560, 1440), 'wide', 'center')), self.probe.placed)
        self.assertEqual(self.controller.last_bounds, (0, 0, 2560, 1440))

    def test_preferences_persist_and_reject_bad_values(self):
        values = self.bridge.save_preferences({'hotkey': 'F9', 'accent': 'blue', 'opacity': 82,
                                               'reduced_motion': True, 'size': 'wide', 'position': 'right'})
        self.assertEqual(OverlayBridge(self.api, self.tmp.name).preferences(), values)
        self.assertEqual(valid_preferences({'size': 'compact'})['size'], 'wide')
        self.assertEqual(valid_preferences({'size': 'standard'})['size'], 'wide')
        self.assertTrue(Path(self.tmp.name, 'overlay-preferences.json').exists())
        with self.assertRaises(ValueError): valid_preferences({'hotkey': 'F8'})
        with self.assertRaises(ValueError): valid_preferences({'opacity': True})
        with self.assertRaises(ValueError): valid_preferences({'size': 'huge'})
        with self.assertRaises(ValueError): valid_preferences({'position': 'outside'})

    def test_layout_rect_clamps_size_and_position_to_game_bounds(self):
        self.assertEqual(layout_rect((100, 50, 900, 650), 'wide', 'right'), (132, 82, 868, 618))
        self.assertEqual(layout_rect((-100, 0, 500, 400), 'wide', 'center'), (-68, 32, 468, 368))

    def test_controller_places_overlay_inside_game_bounds_after_display_change(self):
        self.bridge._values.update(size='wide', position='right')
        self.controller.game_hwnd = 1
        self.controller.show()
        self.assertEqual(self.window.resizes[-1], (1200, 740))
        self.assertEqual(self.probe.placed[-1], (2, (688, 170, 1888, 910)))
        self.probe.rect = (0, 0, 1280, 720)
        self.controller.tick()
        self.assertEqual(self.probe.placed[-1], (2, (48, 32, 1248, 688)))

    def test_macro_profiles_are_editable_and_permission_gated(self):
        self.api._session['permissions']['profiles'] = True
        profiles = self.bridge.macro_profiles()
        self.assertEqual(profiles, {'available': True, 'profiles': [
            {'id': 1, 'name': 'Practice', 'kind': 'single_edit', 'config': {'secret_bind': 'F'}, 'saved_at': 123}
        ]})
        self.api._session['permissions']['profiles'] = False
        self.assertEqual(self.bridge.macro_profiles(), {'available': False, 'profiles': []})
        self.assertFalse(any('macro_configure' in name or 'macro_enable' in name for name in dir(self.bridge)))

    def test_overlay_pages_exclude_main_app_only_tools(self):
        root = Path(__file__).resolve().parents[1] / 'web'
        markup = (root / 'overlay.html').read_text(encoding='utf-8')
        script = (root / 'overlay.js').read_text(encoding='utf-8')
        for page in ('home', 'macros', 'windows', 'appearance'):
            self.assertIn(f'data-page="{page}"', markup + script)
        for removed in ('performance', 'measurements', 'backups'):
            self.assertNotIn(f'data-page="{removed}"', markup + script)
        self.assertNotIn('preview_performance', dir(self.bridge))
        main_app = (root / 'app.js').read_text(encoding='utf-8')
        for retained in ("['performance','Performance'", "['measurements','Measurements'", "['backups','Backups & restore'"):
            self.assertIn(retained, main_app)


if __name__ == '__main__':
    unittest.main()
