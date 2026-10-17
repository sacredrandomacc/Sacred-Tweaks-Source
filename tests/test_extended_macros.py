import unittest
from desktop.macros import MacroEngine, validate_config
from test_native_macros import Sink

class ExtendedMacros(unittest.TestCase):
    def setup_engine(self, kind, **config):
        self.sink = Sink()
        self.engine = MacroEngine(self.sink)
        try:
            self.engine.configure(kind, config)
        except ValueError as exc:
            self.fail(f'{kind} is not implemented: {exc}')
        self.engine.set_authorization(True, 20)
        self.engine.enable(True, 0)

    def test_pickup_repeats_only_while_held_and_does_not_catch_up(self):
        self.setup_engine('pickup', activation='F', interact='E', repeat_ms=50)
        self.engine.input('F', True, 0, True)
        self.engine.tick(1, True)
        self.assertEqual(self.sink.events, [('E', True), ('E', False)] * 2)
        self.engine.input('F', False, 1.01, True)
        self.engine.tick(2, True)
        self.assertEqual(len(self.sink.events), 4)

    def test_sequences_are_one_shot_and_preserve_action_order(self):
        for kind, keys in {'prefire':['MOUSE1','Q','K'], 'wall_replace':['1','MOUSE1','Q','K'],
                           'quick_reset':['E','MOUSE2','E'], 'floor_cone':['X','K','C','K']}.items():
            with self.subTest(kind=kind):
                self.setup_engine(kind, step_delay_ms=20)
                self.engine.input('F', True, 0, True)
                for t in (.1,.2,.3,.4,1,2): self.engine.tick(t, True)
                self.assertEqual([k for k,d in self.sink.events if d], keys)
                self.engine.input('F', False, 3, True)
                self.assertFalse(self.sink.held)

    def test_mantle_release_stops_repetition(self):
        self.setup_engine('mantle', jump='SPACE')
        self.engine.input('F', True, 0, True)
        self.engine.input('F', False, .01, True)
        self.engine.tick(1, True)
        self.assertEqual(self.sink.events, [('SPACE',True),('SPACE',False)])

    def test_build_shared_place_survives_overlapping_piece_keys(self):
        self.setup_engine('auto_build', place='K')
        self.engine.input('Q', True, 0, True)
        self.engine.input('X', True, .1, True)
        self.engine.input('Q', False, .2, True)
        self.assertEqual(self.sink.held, {'K'})
        self.engine.input('X', False, .3, True)
        self.assertFalse(self.sink.held)
        self.assertEqual(self.sink.events, [('K',True),('K',False)])

    def test_safety_stop_cancels_all_extended_macros(self):
        for kind in ('prefire','pickup','wall_replace','auto_build','mantle','quick_reset','floor_cone'):
            for cause in ('focus','expiry','emergency'):
                with self.subTest(kind=kind,cause=cause):
                    self.setup_engine(kind)
                    self.engine.input('Q' if kind=='auto_build' else 'F', True, 0, True)
                    if cause=='emergency': self.engine.input('F8', True,.001,True)
                    else: self.engine.tick(21 if cause=='expiry' else .001,cause!='focus')
                    n=len(self.sink.events)
                    self.engine.tick(22,True)
                    self.assertFalse(self.sink.held)
                    self.assertFalse(self.engine.enabled)
                    self.assertEqual(len(self.sink.events),n)

    def test_conflicting_build_keys_and_nonfinite_timing_rejected(self):
        for values in ({'wall':'X'}, {'place':'Q'}, {'emergency':'C'}, {'step_delay_ms':float('nan')}):
            with self.assertRaises(ValueError): validate_config('auto_build', values)
