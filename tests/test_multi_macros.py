import unittest

from desktop.macros import MacroCoordinator
from test_native_macros import Sink


class MultiMacroTests(unittest.TestCase):
    def setUp(self):
        self.sink = Sink()
        self.engine = MacroCoordinator(self.sink)
        self.engine.set_authorization({'pickup': True, 'quick_reset': True, 'drag': True, 'double_edit': True}, 30)

    def test_independent_macros_can_be_enabled_and_triggered(self):
        self.engine.configure('pickup', {'activation': 'G', 'interact': 'E', 'toggle': 'F11'})
        self.engine.configure('quick_reset', {'activation': 'H', 'toggle': 'F12', 'edit': 'R', 'confirm': 'R'})
        self.engine.enable('pickup', True, 0)
        self.engine.enable('quick_reset', True, 0)
        self.engine.input('G', True, 0, True)
        self.engine.input('G', False, .01, True)
        self.engine.input('H', True, .02, True)
        for t in (.1, .2, .3):
            self.engine.tick(t, True)
        self.assertTrue(self.engine.status()['macros']['pickup']['enabled'])
        self.assertTrue(self.engine.status()['macros']['quick_reset']['enabled'])
        self.assertIn(('E', True), self.sink.events)
        self.assertIn(('MOUSE2', True), self.sink.events)

    def test_new_editing_macro_disables_previous_when_preference_set(self):
        self.engine.configure('drag', {'edit': 'E', 'activation': 'E', 'toggle': 'F10'})
        self.engine.configure('double_edit', {'activation': 'G', 'toggle': 'F18'})
        self.engine.enable('drag', True, 0)
        self.engine.enable('double_edit', True, 0)
        status = self.engine.status()['macros']
        self.assertFalse(status['drag']['enabled'])
        self.assertTrue(status['double_edit']['enabled'])

    def test_toggle_key_changes_only_its_macro(self):
        self.engine.configure('pickup', {'activation': 'G', 'toggle': 'F11'})
        self.engine.configure('quick_reset', {'activation': 'H', 'toggle': 'F12'})
        self.engine.input('F11', True, 0, True)
        self.assertTrue(self.engine.status()['macros']['pickup']['enabled'])
        self.assertFalse(self.engine.status()['macros']['quick_reset']['enabled'])
        self.engine.input('F11', False, .01, True)
        self.engine.input('F11', True, .02, True)
        self.assertFalse(self.engine.status()['macros']['pickup']['enabled'])

    def test_duplicate_activation_is_rejected_without_disabling_existing_macro(self):
        self.engine.configure('pickup', {'activation': 'G'})
        self.engine.configure('quick_reset', {'activation': 'G'})
        self.engine.enable('pickup', True, 0)
        with self.assertRaisesRegex(ValueError, 'activation'):
            self.engine.enable('quick_reset', True, 0)
        self.assertTrue(self.engine.status()['macros']['pickup']['enabled'])

    def test_double_edit_places_then_edits_both(self):
        self.engine.configure('double_edit', {'activation': 'G', 'toggle': 'F18', 'floor': 'X', 'cone': 'C', 'place': 'K', 'edit': 'E', 'select': 'MOUSE1', 'confirm': 'E'})
        self.engine.enable('double_edit', True, 0)
        self.engine.input('G', True, 0, True)
        for i in range(1, 19):
            self.engine.tick(i * .1, True)
        self.assertEqual([k for k, down in self.sink.events if down], ['X', 'K', 'C', 'K', 'E', 'MOUSE1', 'E', 'E', 'MOUSE1', 'E'])

    def test_double_edit_holds_select_during_configured_mouse_paths(self):
        self.sink.move = lambda dx, dy: self.sink.events.append((dx, dy))
        self.engine.configure('double_edit', {'activation': 'G', 'first_dx': 35, 'first_dy': -12,
                                               'second_dx': -18, 'second_dy': 20})
        self.engine.enable('double_edit', True, 0)
        self.engine.input('G', True, 0, True)
        for i in range(1, 20):
            self.engine.tick(i * .1, True)
        events = self.sink.events
        self.assertLess(events.index(('MOUSE1', True)), events.index((35, -12)))
        self.assertLess(events.index((35, -12)), events.index(('MOUSE1', False)))
        self.assertLess(events.index((35, -12)), events.index((-18, 20)))

    def test_emergency_releases_all_held_inputs(self):
        self.engine.configure('drag', {'edit': 'E', 'toggle': 'F10'})
        self.engine.configure('pickup', {'activation': 'G', 'toggle': 'F11'})
        self.engine.enable('drag', True, 0)
        self.engine.enable('pickup', True, 0)
        self.engine.input('E', True, 0, True)
        self.engine.input('F8', True, .01, True)
        self.assertFalse(self.sink.held)
        self.assertFalse(any(m['enabled'] for m in self.engine.status()['macros'].values()))

    def test_weapon_pullout_follows_completed_edit_only_when_enabled(self):
        self.engine.set_authorization({'single_edit': True, 'drag': True, 'gun_pullout': True}, 30)
        self.engine.configure('drag', {'edit': 'E'})
        self.engine.configure('gun_pullout', {'weapon': '3'})
        self.engine.enable('drag', True, 0)
        self.engine.enable('gun_pullout', True, 0)
        self.engine.input('E', True, 0, True)
        self.engine.input('E', False, .1, True)
        self.engine.tick(.2, True)
        self.assertIn(('3', True), self.sink.events)

    def test_gun_pullout_can_run_with_default_single_edit_bind(self):
        self.engine.set_authorization({'single_edit': True, 'gun_pullout': True}, 30)
        self.engine.configure('gun_pullout', {'weapon': '3'})
        self.engine.enable('single_edit', True, 0)
        self.engine.enable('gun_pullout', True, 0)
        self.assertTrue(self.engine.status()['macros']['gun_pullout']['enabled'])

    def test_pending_weapon_pullout_is_canceled_on_focus_loss(self):
        self.engine.set_authorization({'single_edit': True, 'drag': True, 'gun_pullout': True}, 30)
        self.engine.configure('drag', {'edit': 'E'})
        self.engine.configure('gun_pullout', {'weapon': '3'})
        self.engine.enable('drag', True, 0)
        self.engine.enable('gun_pullout', True, 0)
        self.engine.input('E', True, 0, True)
        self.engine.input('E', False, .01, True)
        self.engine.tick(.02, False)
        self.engine.tick(.5, True)
        self.assertNotIn(('3', True), self.sink.events)

    def test_double_edit_hold_release_cancels_sequence_and_keeps_toggle_enabled(self):
        self.engine.configure('double_edit', {'activation': 'G', 'trigger_mode': 'hold'})
        self.engine.enable('double_edit', True, 0)
        self.engine.input('G', True, 0, True)
        self.engine.tick(.1, True)
        self.engine.input('G', False, .11, True)
        before = len(self.sink.events)
        self.engine.tick(2, True)
        self.assertEqual(len(self.sink.events), before)
        self.assertTrue(self.engine.status()['macros']['double_edit']['enabled'])

    def test_canceled_double_edit_does_not_pull_weapon(self):
        self.engine.set_authorization({'single_edit': True, 'double_edit': True, 'gun_pullout': True}, 30)
        self.engine.configure('double_edit', {'activation': 'G', 'trigger_mode': 'hold'})
        self.engine.configure('gun_pullout', {'weapon': '3'})
        self.engine.enable('double_edit', True, 0)
        self.engine.enable('gun_pullout', True, 0)
        self.engine.input('G', True, 0, True)
        self.engine.input('G', False, .01, True)
        for i in range(1, 15):
            self.engine.tick(i * .1, True)
        self.assertNotIn(('3', True), self.sink.events)

    def test_completed_double_edit_pulls_weapon_after_second_confirm(self):
        self.engine.set_authorization({'single_edit': True, 'double_edit': True, 'gun_pullout': True}, 30)
        self.engine.configure('double_edit', {'activation': 'G'})
        self.engine.configure('gun_pullout', {'weapon': '3'})
        self.engine.enable('double_edit', True, 0)
        self.engine.enable('gun_pullout', True, 0)
        self.engine.input('G', True, 0, True)
        self.engine.input('G', False, .01, True)
        for i in range(1, 25):
            self.engine.tick(i * .1, True)
        pressed = [key for key, down in self.sink.events if down]
        self.assertEqual(pressed[-2:], ['E', '3'])

    def test_configured_press_duration_keeps_key_down_until_later_tick(self):
        self.engine.configure('quick_reset', {'activation': 'G', 'press_ms': 15})
        self.engine.enable('quick_reset', True, 0)
        self.engine.input('G', True, 0, True)
        self.assertIn('E', self.sink.held)
        self.engine.tick(.01, True)
        self.assertIn('E', self.sink.held)
        self.engine.tick(.02, True)
        self.assertNotIn('E', self.sink.held)

    def test_partial_synthetic_press_is_released_on_emergency_stop(self):
        self.engine.configure('quick_reset', {'activation': 'G'})
        self.engine.enable('quick_reset', True, 0)
        old_down = self.sink.down
        def uncertain_down(key):
            old_down(key)
            raise OSError('uncertain Windows input result')
        self.sink.down = uncertain_down
        with self.assertRaises(OSError):
            self.engine.input('G', True, 0, True)
        self.engine.stop('Emergency stop')
        self.assertFalse(self.sink.held)


if __name__ == '__main__':
    unittest.main()
