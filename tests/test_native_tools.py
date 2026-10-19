from pathlib import Path
import tempfile
import time
import threading
from unittest.mock import patch
import unittest

from desktop.native import NativeTools, CpuSampler
from desktop.settings import SettingsManager


class FakePlatform:
    available = True
    error = None

    def __init__(self):
        self.held = set()
        self.focus = True
        self.pressed = threading.Event()
        self.released = threading.Event()

    def start(self, callback, interested):
        self.callback = callback

    def down(self, key):
        self.held.add(key)
        self.released.clear()
        self.pressed.set()

    def up(self, key):
        self.held.discard(key)
        if not self.held:
            self.released.set()

    def foreground(self):
        return self.focus

    def game_running(self):
        return False

    def close(self):
        pass


class NativeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.platform = FakePlatform()
        self.native = NativeTools(Path(self.temp.name), platform=self.platform)
        self.addCleanup(self.native.close)

    def authorize(self, permissions=None, enforced=None, duration=20):
        self.native.set_authorization(permissions or {'single_edit': True, 'drag': True, 'performance': True, 'measurements': True, 'themes': True}, enforced or {}, time.monotonic() + duration)

    def test_offline_only_safe_actions_are_allowed(self):
        for action in ('hardware', 'macro_status', 'backups', 'emergency_stop'):
            self.assertIsInstance(self.native.call(action), dict)
        for action in ('macro_enable', 'macro_configure', 'filter_apply', 'settings_preview', 'measurement_save'):
            with self.assertRaises(PermissionError):
                self.native.call(action, {})

    def test_appearance_stores_toggle_and_adjustable_palette(self):
        self.authorize()
        saved=self.native.call('theme',{'animations_enabled':False,'lightweight':True,
            'accent':'#123456','surface':'#202124','text_color':'#F0EFEA','muted_color':'#B0B1B5','reduced_motion':True})
        self.assertFalse(saved['animations_enabled'])
        self.assertEqual(saved['surface'],'#202124')
        self.assertEqual(saved['text_color'],'#F0EFEA')
        with self.assertRaises((ValueError,PermissionError)):
            self.native.call('theme',{'animations_enabled':False,'accent':'bad','surface':'#111318'})

    def test_workspace_pages_save_validated_data(self):
        with self.assertRaises(PermissionError):
            self.native.call('workspace_get', {'key': 'journal'})
        self.authorize()
        self.assertEqual(self.native.call('workspace_get', {'key': 'journal'})['value'], {})
        self.native.call('workspace_save', {'key': 'journal', 'value': {'entries': [{'title': 'Scrim', 'body': 'Rotate early'}]}})
        self.assertEqual(self.native.call('workspace_get', {'key': 'journal'})['value']['entries'][0]['title'], 'Scrim')
        for bad in ({'key': '../theme', 'value': {}}, {'key': 'journal', 'value': []}, {'key': 'journal', 'value': {'x': 'y' * 70000}}):
            with self.assertRaises(ValueError):
                self.native.call('workspace_save', bad)
        live = self.native.call('system_live', {})
        self.assertIn('cpu_usage_percent', live)

    def test_local_data_backup_round_trip_and_validation(self):
        self.authorize()
        self.native.call('workspace_save', {'key': 'journal', 'value': {'entries': [{'title': 'Win'}]}})
        bundle = self.native.call('data_bundle', {})
        self.assertEqual(bundle['workspace']['journal']['entries'][0]['title'], 'Win')
        self.native.call('workspace_save', {'key': 'journal', 'value': {}})
        restored = self.native.call('data_restore', {'bundle': bundle})['restored']
        self.assertIn('journal', restored)
        self.assertEqual(self.native.call('workspace_get', {'key': 'journal'})['value']['entries'][0]['title'], 'Win')
        for bad in ({'format': 'other'}, {**bundle, 'workspace': {'secrets': {}}}, {**bundle, 'theme': {'accent': 'javascript:'}}):
            with self.assertRaises(ValueError):
                self.native.call('data_restore', {'bundle': bad})
        extras = self.native.call('system_extras', {})
        self.assertEqual(set(extras), {'startup', 'heavy', 'display'})

    def test_appearance_stores_theme_preset_and_glass(self):
        self.authorize()
        saved=self.native.call('theme',{'animations_enabled':True,'lightweight':False,'accent':'#22D3EE',
            'surface':'#0B1719','text_color':'#E8FAFB','muted_color':'#9DBDC0','glass':True,'preset':'aqua'})
        self.assertTrue(saved['glass'])
        self.assertEqual(saved['preset'],'aqua')
        for bad in ({'glass':'yes'},{'preset':'<script>'}):
            with self.assertRaises(ValueError):
                self.native.call('theme',{'animations_enabled':True,'lightweight':False,'accent':'#22D3EE',**bad})

    def test_permission_and_enforced_value_bypass_rejected(self):
        self.authorize({'single_edit': True}, {'single_edit': {'repeat_ms': 250}})
        with self.assertRaises(PermissionError):
            self.native.call('macro_configure', {'kind': 'drag', 'config': {}})
        with self.assertRaises(PermissionError):
            self.native.call('macro_configure', {'kind': 'single_edit', 'config': {'repeat_ms': 150}})
        result = self.native.call('macro_configure', {'kind': 'single_edit', 'config': {'repeat_ms': 250}})
        self.assertEqual(result['config']['repeat_ms'], 250)

    def test_two_macro_configs_stay_enabled_when_compatible(self):
        self.authorize({'single_edit': True, 'pickup': True, 'quick_reset': True})
        self.native.call('macro_configure', {'kind': 'pickup', 'config': {'activation': 'G', 'toggle': 'F11'}})
        self.native.call('macro_configure', {'kind': 'quick_reset', 'config': {'activation': 'H', 'toggle': 'F12'}})
        self.native.call('macro_enable', {'kind': 'pickup', 'enabled': True})
        self.native.call('macro_enable', {'kind': 'quick_reset', 'enabled': True})
        status = self.native.call('macro_status')
        self.assertTrue(status['macros']['pickup']['enabled'])
        self.assertTrue(status['macros']['quick_reset']['enabled'])

    def test_newest_editing_conflict_policy(self):
        self.authorize({'single_edit': True, 'drag': True, 'double_edit': True})
        self.native.call('macro_configure', {'kind': 'drag', 'config': {'toggle': 'F10'}})
        self.native.call('macro_configure', {'kind': 'double_edit', 'config': {'activation': 'G', 'toggle': 'F18'}})
        self.native.call('macro_enable', {'kind': 'drag', 'enabled': True})
        self.native.call('macro_enable', {'kind': 'double_edit', 'enabled': True})
        status = self.native.call('macro_status')['macros']
        self.assertFalse(status['drag']['enabled'])
        self.assertTrue(status['double_edit']['enabled'])

    def test_drag_activation_reaches_game_while_toggle_is_consumed(self):
        self.authorize()
        self.native.call('macro_configure', {'kind': 'drag', 'config': {}})
        self.native.call('macro_enable', {'kind': 'drag', 'enabled': True})
        with self.native.lock:
            self.native.foreground = True
            self.native._update_interest()
        self.assertEqual(self.native._interested('E'), (True, False))
        self.assertEqual(self.native._interested('F10'), (True, True))

    def test_configured_emergency_key_reaches_input_worker(self):
        self.authorize()
        self.native.call('macro_configure', {'kind': 'drag', 'config': {'emergency': 'F7'}})
        with self.native.lock:
            self.native._update_interest()
        self.assertEqual(self.native._interested('F7'), (True, False))

    def test_macro_toggle_cannot_overlap_overlay_hotkey(self):
        self.authorize()
        with self.assertRaisesRegex(ValueError, 'overlay'):
            self.native.call('macro_configure', {'kind': 'drag', 'config': {'toggle': 'TAB'}})

    def test_loadout_saves_macro_configs_and_appearance_without_performance(self):
        self.authorize({'single_edit': True, 'drag': True, 'themes': True})
        self.native.set_account(42)
        self.native.call('macro_configure', {'kind': 'drag', 'config': {'edit': 'G'}})
        self.native.call('theme', {'accent': '#123456', 'animations_enabled': False})
        saved = self.native.call('loadout_save', {'name': 'Arena'})
        self.assertEqual(saved['name'], 'Arena')
        self.assertEqual(saved['macros']['drag']['edit'], 'G')
        self.assertEqual(saved['appearance']['accent'], '#123456')
        self.assertNotIn('performance', saved)
        self.native.call('macro_configure', {'kind': 'drag', 'config': {'edit': 'H'}})
        self.native.call('loadout_apply', {'id': saved['id']})
        self.assertEqual(self.native.call('macro_status')['macros']['drag']['config']['edit'], 'G')
        self.assertFalse(self.native.call('macro_status')['macros']['drag']['enabled'])

    def test_invalid_loadout_does_not_interrupt_running_macro(self):
        self.authorize({'single_edit': True, 'drag': True, 'themes': True})
        self.native.set_account(42)
        self.native.call('macro_configure', {'kind': 'drag', 'config': {}})
        self.native.call('macro_enable', {'kind': 'drag', 'enabled': True})
        saved = self.native.call('loadout_save', {'name': 'Arena'})
        path = Path(self.temp.name) / 'loadouts-42.json'
        data = __import__('json').loads(path.read_text())
        data[0]['macros']['drag']['edit'] = 'NOT_A_KEY'
        path.write_text(__import__('json').dumps(data))
        with self.assertRaises(ValueError):
            self.native.call('loadout_apply', {'id': saved['id']})
        self.assertTrue(self.native.call('macro_status')['macros']['drag']['enabled'])

    def test_loadout_without_base_config_does_not_change_appearance(self):
        self.authorize({'single_edit': True, 'themes': True})
        self.native.set_account(42)
        saved = self.native.call('loadout_save', {'name': 'Arena'})
        path = Path(self.temp.name) / 'loadouts-42.json'
        import json
        rows = json.loads(path.read_text())
        rows[0]['macros'].pop('single_edit')
        path.write_text(json.dumps(rows))
        with self.assertRaises(ValueError):
            self.native.call('loadout_apply', {'id': saved['id']})
        self.assertFalse((Path(self.temp.name) / 'theme.json').exists())

    def test_loadout_save_accepts_older_theme_without_motion_field(self):
        self.authorize({'single_edit': True, 'themes': True})
        self.native.set_account(42)
        (Path(self.temp.name) / 'theme.json').write_text('{"accent":"#123456","surface":"#111318","text_color":"#F2F0EA","muted_color":"#AAA9AD","animations_enabled":true,"lightweight":false}')
        saved = self.native.call('loadout_save', {'name': 'Old theme'})
        self.assertFalse(saved['appearance']['reduced_motion'])

    def test_macro_warning_is_acknowledged_once_per_account(self):
        self.authorize()
        self.native.set_account(42)
        self.assertFalse(self.native.call('macro_warning')['acknowledged'])
        self.assertTrue(self.native.call('macro_warning', {'acknowledge': True})['acknowledged'])
        self.native.set_account(43)
        self.assertFalse(self.native.call('macro_warning')['acknowledged'])
        self.native.set_account(42)
        self.assertTrue(self.native.call('macro_warning')['acknowledged'])

    def test_macro_configs_and_misc_preference_resume_disabled_after_sign_in(self):
        self.authorize({'single_edit': True, 'pickup': True})
        self.native.set_account(42)
        self.native.call('macro_configure', {'kind': 'pickup', 'config': {'activation': 'G'}})
        self.native.call('macro_preferences', {'editing_conflicts': 'allow_multiple'})
        self.native.call('macro_enable', {'kind': 'pickup', 'enabled': True})
        self.native.set_account(None)
        self.native.set_account(42)
        status = self.native.call('macro_status')
        self.assertEqual(status['macros']['pickup']['config']['activation'], 'G')
        self.assertEqual(status['editing_conflicts'], 'allow_multiple')
        self.assertFalse(status['macros']['pickup']['enabled'])

    def test_authorization_watchdog_stops_without_frontend_calls(self):
        # Startup can include the worker's 50 ms idle wait plus OS scheduling.
        # Observe activation first, then shorten the lease under test.
        self.authorize(duration=10)
        self.native.call('macro_configure', {'kind': 'drag', 'config': {}})
        self.native.call('macro_enable', {'enabled': True})
        self.platform.callback('E', True)
        self.assertTrue(self.platform.pressed.wait(2), 'Worker did not process activation')
        self.assertEqual(self.platform.held, {'MOUSE1'})
        self.authorize(duration=.08)
        # No frontend/native action is called while waiting for the watchdog.
        self.assertTrue(self.platform.released.wait(2), 'Watchdog did not release expired input')
        self.assertFalse(self.platform.held)
        self.assertFalse(self.native.call('macro_status')['enabled'])
        self.authorize()
        self.assertFalse(self.native.call('macro_status')['enabled'])

    def test_disconnection_clears_pending_events_and_never_resumes(self):
        self.authorize()
        self.native.call('macro_configure', {'kind': 'drag', 'config': {}})
        self.native.call('macro_enable', {'enabled': True})
        self.platform.callback('E', True)
        self.native.stop('Disconnected')
        self.authorize()
        time.sleep(.03)
        self.assertFalse(self.platform.held)
        self.assertFalse(self.native.call('macro_status')['enabled'])

    def test_partial_macro_config_is_checked_after_defaults(self):
        self.authorize(enforced={'single_edit': {'repeat_ms': 250}})
        with self.assertRaises(PermissionError):
            self.native.call('macro_configure', {'kind': 'single_edit', 'config': {}})

    def test_potato_cannot_bypass_performance_permission(self):
        self.authorize({'performance': True})
        with self.assertRaises(PermissionError):
            self.native.call('settings_preview', {'preset': 'potato', 'target_fps': 144})

    def test_measurements_are_manual_and_missing_metrics_stay_null(self):
        self.authorize()
        result = self.native.call('measurement_save', {'name': 'Before', 'fps': 120, 'notes': 'In-game counter'})
        self.assertEqual(result['source'], 'manual_observation')
        self.assertIsNone(result['frame_time_ms'])
        self.assertIsNone(result['gpu_usage_percent'])
        self.assertEqual(len(self.native.call('measurements')['measurements']), 1)

    def test_unknown_action_and_arbitrary_settings_uris_rejected(self):
        self.authorize()
        with self.assertRaises(ValueError):
            self.native.call('run_command', {'command': 'anything'})
        with self.assertRaises(ValueError):
            self.native.call('windows_settings', {'page': 'https://example.com'})

    def test_advanced_controls_require_permission_even_with_known_preset(self):
        self.authorize({'performance': True})
        with self.assertRaises(PermissionError):
            self.native.call('settings_preview', {'preset': 'performance', 'advanced': {'sg.ShadowQuality': 2}})

    def test_custom_preset_cannot_bypass_advanced_permission(self):
        self.authorize({'performance': True})
        with self.assertRaises(PermissionError):
            self.native.call('settings_preview', {'preset': 'custom', 'target_fps': 144})

    def test_advanced_permission_rechecked_at_apply_and_enforced_map_validated(self):
        config_path = Path(self.temp.name) / 'GameUserSettings.ini'
        original = b'[/Script/FortniteGame.FortGameUserSettings]\nFrameRateLimit=60.000000\nbUseVSync=True\n[ScalabilityGroups]\nsg.ShadowQuality=3\n'
        config_path.write_bytes(original)
        self.native.settings = SettingsManager(Path(self.temp.name), config_path, lambda: False)
        self.authorize({'performance': True, 'advanced': True})
        preview = self.native.call('settings_preview', {'preset': 'custom', 'target_fps': 144, 'advanced': {'FrameRateLimit': 144}})
        self.authorize({'performance': True})
        with self.assertRaises(PermissionError):
            self.native.call('settings_apply', {'plan_id': preview['plan_id']})
        self.assertEqual(config_path.read_bytes(), original)
        self.authorize({'performance': True, 'advanced': True}, {'advanced': {'advanced': {'bUseVSync': True}}})
        with self.assertRaises(PermissionError):
            self.native.call('settings_preview', {'preset': 'custom', 'advanced': {'bUseVSync': False}})

    def test_pending_settings_write_rejects_new_authorization_snapshot(self):
        config_path = Path(self.temp.name) / 'GameUserSettings.ini'
        original = b'[/Script/FortniteGame.FortGameUserSettings]\nFrameRateLimit=60.000000\nbUseVSync=True\n'
        config_path.write_bytes(original)
        self.native.settings = SettingsManager(Path(self.temp.name), config_path, lambda: False)
        self.authorize({'performance': True, 'advanced': True})
        plan = self.native.call('settings_preview', {'preset': 'custom', 'advanced': {'FrameRateLimit': 144}})
        create = self.native.settings.store.create
        def changed_during_backup(*args, **kwargs):
            result = create(*args, **kwargs)
            self.native.stop('Signed out')
            self.authorize({'performance': True})
            return result
        self.native.settings.store.create = changed_during_backup
        with self.assertRaises(PermissionError):
            self.native.call('settings_apply', {'plan_id': plan['plan_id']})
        self.assertEqual(config_path.read_bytes(), original)
        self.assertEqual(len(self.native.call('backups')['backups']), 1)

    def test_slow_settings_write_does_not_block_emergency_input_release(self):
        config_path = Path(self.temp.name) / 'GameUserSettings.ini'
        config_path.write_bytes(b'[/Script/FortniteGame.FortGameUserSettings]\nFrameRateLimit=60.000000\nbUseVSync=True\n')
        self.native.settings = SettingsManager(Path(self.temp.name), config_path, lambda: False)
        self.authorize()
        self.native.call('macro_configure', {'kind': 'drag', 'config': {}})
        self.native.call('macro_enable', {'enabled': True})
        with self.native.lock:
            self.native.engine.input('E', True, time.monotonic(), True)
        self.assertEqual(self.platform.held, {'MOUSE1'})
        plan = self.native.call('settings_preview', {'target_fps': 144})
        started, release, stopped = threading.Event(), threading.Event(), threading.Event()
        def slow_write(*args):
            started.set()
            release.wait(2)
        with patch('desktop.settings.replace_config', slow_write):
            worker = threading.Thread(target=lambda: self.native.call('settings_apply', {'plan_id': plan['plan_id']}))
            worker.start()
            self.assertTrue(started.wait(1))
            def emergency():
                self.native.call('emergency_stop')
                stopped.set()
            stopper = threading.Thread(target=emergency)
            stopper.start()
            try:
                self.assertTrue(stopped.wait(.3), 'Emergency stop waited for the settings write')
                self.assertFalse(self.platform.held)
            finally:
                release.set()
                worker.join(2)
                stopper.join(2)

    def test_offline_restore_remains_available(self):
        config_path = Path(self.temp.name) / 'GameUserSettings.ini'
        original = b'[/Script/FortniteGame.FortGameUserSettings]\nFrameRateLimit=60.000000\nbUseVSync=True\n'
        config_path.write_bytes(original)
        self.native.settings = SettingsManager(Path(self.temp.name), config_path, lambda: False)
        self.authorize({'performance': True})
        plan = self.native.call('settings_preview', {'target_fps': 144})
        changed = self.native.call('settings_apply', {'plan_id': plan['plan_id']})
        self.native.stop('License revoked')
        restored = self.native.call('restore', {'backup_id': changed['backup_id']})
        self.assertTrue(restored['success'])
        self.assertEqual(config_path.read_bytes(), original)


class CpuSamplingTests(unittest.TestCase):
    def test_nonblocking_cpu_sample_uses_real_counter_deltas(self):
        counters = iter([(100, 200, 200), (140, 250, 250)])
        sampler = CpuSampler(lambda: next(counters))
        self.assertIsNone(sampler.sample(10)['cpu_usage_percent'])
        result = sampler.sample(12)
        self.assertEqual(result['cpu_usage_percent'], 60)
        self.assertEqual(result['cpu_sample_seconds'], 2)


if __name__ == '__main__':
    unittest.main()
