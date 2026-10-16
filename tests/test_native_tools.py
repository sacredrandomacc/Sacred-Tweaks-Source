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

    def test_permission_and_enforced_value_bypass_rejected(self):
        self.authorize({'single_edit': True}, {'single_edit': {'repeat_ms': 250}})
        with self.assertRaises(PermissionError):
            self.native.call('macro_configure', {'kind': 'drag', 'config': {}})
        with self.assertRaises(PermissionError):
            self.native.call('macro_configure', {'kind': 'single_edit', 'config': {'repeat_ms': 150}})
        result = self.native.call('macro_configure', {'kind': 'single_edit', 'config': {'repeat_ms': 250}})
        self.assertEqual(result['config']['repeat_ms'], 250)

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
