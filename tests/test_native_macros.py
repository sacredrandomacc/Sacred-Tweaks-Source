import unittest

from desktop.macros import MacroEngine


class Sink:
    def __init__(self):
        self.events = []
        self.held = set()

    def down(self, key):
        self.held.add(key)
        self.events.append((key, True))

    def up(self, key):
        self.held.discard(key)
        self.events.append((key, False))


class MacroTests(unittest.TestCase):
    def setUp(self):
        self.sink = Sink()
        self.engine = MacroEngine(self.sink)
        self.engine.set_authorization(True, 10.0)

    def enable(self, kind='single_edit', **config):
        self.engine.configure(kind, config)
        self.engine.enable(True, 0)

    def test_disabled_until_explicit_enable(self):
        self.engine.input('F', True, 0, True)
        self.engine.tick(1, True)
        self.assertEqual(self.sink.events, [])

    def test_tap_completes_one_edit_select_confirm_cycle(self):
        self.enable(step_delay_ms=20)
        self.engine.input('F', True, 0, True)
        self.engine.input('F', False, .001, True)
        self.engine.tick(.02, True)
        self.engine.tick(.04, True)
        self.engine.tick(1, True)
        self.assertEqual(self.sink.events, [('E', True), ('E', False), ('MOUSE1', True), ('MOUSE1', False), ('E', True), ('E', False)])

    def test_hold_repeats_without_catching_up_a_delayed_tick(self):
        self.enable(step_delay_ms=10, repeat_ms=100)
        self.engine.input('F', True, 0, True)
        self.engine.tick(.01, True)
        self.engine.tick(.02, True)
        self.engine.tick(.11, True)
        self.engine.tick(2, True)
        self.assertLessEqual(len(self.sink.events), 10)
        self.engine.input('F', False, 2, True)
        self.engine.tick(2.1, True)
        self.engine.tick(3, True)
        self.engine.tick(3.1, True)
        self.assertEqual(len(self.sink.events), 12)

    def test_drag_releases_and_auto_confirms(self):
        self.enable('drag', edit='E', confirm='G', confirm_mode='auto')
        self.engine.input('E', True, 0, True)
        self.assertEqual(self.sink.held, {'MOUSE1'})
        self.engine.input('E', False, .1, True)
        self.engine.tick(.12, True)
        self.assertEqual(self.sink.events[-3:], [('MOUSE1', False), ('G', True), ('G', False)])
        self.assertFalse(self.sink.held)

    def test_manual_confirm_never_sends_confirm(self):
        self.enable('drag', confirm_mode='manual', game_auto_confirm=True)
        self.engine.input('E', True, 0, True)
        self.engine.input('E', False, .1, True)
        self.assertEqual(self.sink.events, [('MOUSE1', True), ('MOUSE1', False)])

    def test_focus_loss_releases_and_requires_reenable(self):
        self.enable('drag')
        self.engine.input('E', True, 0, True)
        self.engine.tick(.01, False)
        self.assertFalse(self.sink.held)
        self.assertFalse(self.engine.enabled)
        self.engine.input('E', True, .02, True)
        self.assertFalse(self.sink.held)

    def test_deadline_expires_even_while_held(self):
        self.enable('drag')
        self.engine.input('E', True, 0, True)
        self.engine.tick(10, True)
        self.assertFalse(self.sink.held)
        self.assertFalse(self.engine.enabled)
        self.engine.set_authorization(True, 30)
        self.assertFalse(self.engine.enabled)

    def test_configuration_change_releases_before_loading(self):
        self.enable('drag')
        self.engine.input('E', True, 0, True)
        self.engine.configure('single_edit', {'activation': 'R'})
        self.assertFalse(self.sink.held)
        self.assertFalse(self.engine.enabled)
        self.assertEqual(self.engine.config['activation'], 'R')

    def test_emergency_stop_cancels_remaining_single_steps(self):
        self.enable()
        self.engine.input('F', True, 0, True)
        self.engine.input('F8', True, .001, True)
        self.engine.tick(1, True)
        self.assertEqual(len(self.sink.events), 2)
        self.assertFalse(self.engine.enabled)

    def test_injected_overlap_never_recurses(self):
        self.enable(activation='E')
        self.engine.input('E', True, 0, True, injected=True)
        self.assertEqual(self.sink.events, [])
        self.engine.input('E', True, 0, True)
        self.engine.input('E', True, .001, True, injected=True)
        self.engine.tick(.02, True)
        self.assertEqual(self.sink.events.count(('E', True)), 1)

    def test_rapid_second_press_does_not_overlap_pending_key_release(self):
        self.enable()
        self.engine.input('F', True, 0, True)
        self.engine.input('F', False, .001, True)
        self.engine.input('F', True, .002, True)
        self.assertEqual(self.sink.events.count(('E', True)), 1)
        self.engine.tick(.02, True)
        self.assertNotIn('E', self.sink.held)

    def test_unrelated_input_not_retained_or_recorded(self):
        self.enable()
        for key in ('A', 'B', 'C', 'ENTER'):
            self.engine.input(key, True, 0, True)
        self.assertEqual(self.sink.events, [])
        self.assertFalse(self.engine.pressed)

    def test_conflicts_and_duplicate_confirmation_rejected(self):
        for config in ({'emergency': 'E'}, {'select': 'E'}, {'activation': 'MOUSE1'}):
            with self.assertRaises(ValueError):
                self.engine.configure('single_edit', config)
        with self.assertRaises(ValueError):
            self.engine.configure('drag', {'confirm_mode': 'auto', 'game_auto_confirm': True})

    def test_transient_release_failure_is_retried_without_reenabling(self):
        self.enable('drag')
        self.engine.input('E', True, 0, True)
        original_up = self.sink.up
        def failed_release(key):
            raise OSError('temporary rejection')
        self.sink.up = failed_release
        self.engine.stop('Emergency stop')
        self.assertEqual(self.sink.held, {'MOUSE1'})
        self.assertTrue(self.engine.release_errors)
        self.sink.up = original_up
        self.engine.tick(.1, True)
        self.assertFalse(self.sink.held)
        self.assertFalse(self.engine.enabled)


if __name__ == '__main__':
    unittest.main()
