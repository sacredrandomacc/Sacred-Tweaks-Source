import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from desktop.settings import SettingsManager, FilterKeysManager


CONFIG = ('; untouched comment\r\n[/Script/FortniteGame.FortGameUserSettings]\r\n'
          'Version=5\r\nFrameRateLimit=60.000000\r\nbUseVSync=True\r\n'
          'Unrelated=leave-me\r\n[ScalabilityGroups]\r\nsg.ResolutionQuality=100.000000\r\n'
          'sg.ShadowQuality=3\r\nsg.TextureQuality=3\r\n')


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'GameUserSettings.ini'
        self.config.write_bytes(CONFIG.encode())
        self.running = False
        self.manager = SettingsManager(self.root / 'data', self.config, lambda: self.running)

    def preview(self, preset='performance'):
        return self.manager.preview(preset, 144)

    def test_preview_does_not_write_and_only_existing_allowed_keys(self):
        result = self.preview()
        self.assertEqual(self.config.read_bytes(), CONFIG.encode())
        names = {item['key'] for item in result['changes']}
        self.assertIn('FrameRateLimit', names)
        self.assertNotIn('Unrelated', names)
        self.assertNotIn('sg.EffectsQuality', names)

    def test_apply_preserves_comments_unknown_values_and_line_endings(self):
        plan = self.preview()
        result = self.manager.apply(plan['plan_id'])
        raw = self.config.read_bytes()
        self.assertIn(b'FrameRateLimit=144.000000\r\n', raw)
        self.assertIn(b'Unrelated=leave-me\r\n', raw)
        self.assertTrue(raw.startswith(b'; untouched comment\r\n'))
        self.assertTrue(result['backup_id'])
        self.assertEqual(len(self.manager.backups()), 1)

    def test_restore_preserves_later_changes_and_reports_conflicts(self):
        result = self.manager.apply(self.preview()['plan_id'])
        raw = self.config.read_bytes().replace(b'FrameRateLimit=144.000000', b'FrameRateLimit=165.000000').replace(b'Unrelated=leave-me', b'Unrelated=new')
        self.config.write_bytes(raw)
        restored = self.manager.restore(result['backup_id'])
        self.assertTrue(restored['conflicts'])
        self.assertIn(b'FrameRateLimit=165.000000', self.config.read_bytes())
        self.assertIn(b'bUseVSync=True', self.config.read_bytes())
        self.assertIn(b'Unrelated=new', self.config.read_bytes())

    def test_stale_preview_rejected_without_writing(self):
        plan = self.preview()
        self.config.write_bytes(CONFIG.encode() + b'New=1\r\n')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.manager.apply(plan['plan_id'])
        self.assertTrue(self.config.read_bytes().endswith(b'New=1\r\n'))

    def test_running_game_blocks_apply_and_restore(self):
        plan = self.preview()
        self.running = True
        with self.assertRaisesRegex(ValueError, 'Close Fortnite'):
            self.manager.apply(plan['plan_id'])
        self.running = False
        result = self.manager.apply(plan['plan_id'])
        self.running = True
        with self.assertRaisesRegex(ValueError, 'Close Fortnite'):
            self.manager.restore(result['backup_id'])

    def test_ambiguous_duplicate_key_refuses_edit(self):
        self.config.write_bytes(CONFIG.replace('Version=5', 'Version=5\r\nFrameRateLimit=99').encode())
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.preview()

    def test_missing_file_and_unsupported_values_are_not_fabricated(self):
        self.config.unlink()
        with self.assertRaises(FileNotFoundError):
            self.preview()
        self.config.write_bytes(CONFIG.replace('sg.ShadowQuality=3', 'sg.ShadowQuality=99').encode())
        result = self.preview()
        self.assertIn('sg.ShadowQuality', ' '.join(result['skipped']))
        self.assertNotIn('sg.ShadowQuality', {x['key'] for x in result['changes']})

    def test_write_failure_reports_backup_and_preserves_original(self):
        plan = self.preview()
        with patch('desktop.settings.replace_config', side_effect=OSError('disk full')):
            result = self.manager.apply(plan['plan_id'])
        self.assertFalse(result['success'])
        self.assertIn('disk full', result['errors'][0])
        self.assertTrue(result['backup_id'])
        self.assertEqual(self.config.read_bytes(), CONFIG.encode())

    def test_potato_is_separate_preset(self):
        core = self.preview()
        plus = self.preview('potato')
        self.assertEqual(core['feature'], 'performance')
        self.assertEqual(plus['feature'], 'potato')
        self.assertIn('sg.ResolutionQuality', {x['key'] for x in plus['changes']})

    def test_backup_id_cannot_read_arbitrary_paths(self):
        with self.assertRaises(ValueError):
            self.manager.restore('../GameUserSettings.ini')

    def test_custom_advanced_only_changes_selected_observed_keys(self):
        plan = self.manager.preview('custom', 144, {'FrameRateLimit': 144, 'sg.ShadowQuality': 2})
        self.assertTrue(plan['requires_advanced'])
        self.assertEqual({x['key'] for x in plan['changes']}, {'FrameRateLimit', 'sg.ShadowQuality'})
        self.manager.apply(plan['plan_id'])
        self.assertIn(b'bUseVSync=True', self.config.read_bytes())

    def test_advanced_rejects_hidden_keys_invalid_types_and_fps_conflicts(self):
        for values in ({'r.HiddenSetting': 1}, {'sg.ShadowQuality': 5}, {'bUseVSync': 'False'},
                       {'FrameRateLimit': 500}, {'sg.ResolutionQuality': 10}):
            with self.assertRaises(ValueError):
                self.manager.preview('custom', 144, values)

    def test_custom_requires_explicit_selected_controls(self):
        with self.assertRaises(ValueError):
            self.manager.preview('custom', 144)

    def test_lease_rechecked_after_backup_before_settings_write(self):
        calls = []
        def denied():
            calls.append(True)
            raise PermissionError('Expired during backup')
        manager = SettingsManager(self.root / 'secure', self.config, lambda: False, authorize=denied)
        plan = manager.preview('performance', 144)
        with self.assertRaises(PermissionError):
            manager.apply(plan['plan_id'])
        self.assertEqual(self.config.read_bytes(), CONFIG.encode())
        self.assertEqual(len(calls), 1)


class FakeFilterAPI:
    def __init__(self):
        self.value = {'enabled': False, 'wait_ms': 0, 'delay_ms': 1000, 'repeat_ms': 500, 'bounce_ms': 0, 'flags': 6}

    def get(self):
        return self.value.copy()

    def set(self, value):
        self.value = value.copy()


class FilterKeysTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = FakeFilterAPI()
        self.manager = FilterKeysManager(Path(self.temp.name), self.api)

    def test_apply_backs_up_and_restore_preserves_unrelated_flags(self):
        result = self.manager.apply({'enabled': True, 'wait_ms': 0, 'delay_ms': 500, 'repeat_ms': 50, 'bounce_ms': 0})
        self.assertTrue(self.api.value['enabled'])
        self.api.value['flags'] |= 64
        restored = self.manager.restore(result['backup_id'])
        self.assertFalse(self.api.value['enabled'])
        self.assertTrue(self.api.value['flags'] & 64)
        self.assertFalse(restored['conflicts'])

    def test_bounce_keys_cannot_be_combined_with_repeat_or_acceptance(self):
        with self.assertRaises(ValueError):
            self.manager.apply({'enabled': True, 'wait_ms': 1, 'delay_ms': 1, 'repeat_ms': 1, 'bounce_ms': 50})

    def test_restore_reports_user_modified_fields(self):
        result = self.manager.apply({'enabled': True, 'wait_ms': 0, 'delay_ms': 500, 'repeat_ms': 50, 'bounce_ms': 0})
        self.api.value['repeat_ms'] = 100
        restored = self.manager.restore(result['backup_id'])
        self.assertEqual(self.api.value['repeat_ms'], 100)
        self.assertIn('repeat_ms', restored['conflicts'])


if __name__ == '__main__':
    unittest.main()
