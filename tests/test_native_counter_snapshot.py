from unittest import TestCase
from vesc_workbench.native_counter_snapshot import DistanceCounterDecoder, NativeCounterClock, f32, snapshot_expression


class NativeCounterSnapshotTests(TestCase):
    def setUp(self):
        self.config = dict(si_wheel_diameter=f32(.083), si_motor_poles=14, si_gear_ratio=1)
        import math
        self.scale = f32(self.config['si_wheel_diameter']*math.pi/42)
        self.snapshot = dict(distance=f32(551843*self.scale), distance_abs=f32(565225*self.scale),
                             position_deg=41, start_tick=100, end_tick=102)
        self.decoder = DistanceCounterDecoder(self.config, self.snapshot, 551843, 565225)

    def test_exact_sector_counter_recovery_for_current_and_future_counts(self):
        for count in (551843, 565225, 600000, 1000000, -551843):
            self.assertEqual(self.decoder.recover(f32(count*self.scale)), count)

    def test_wrong_scale_and_out_of_precision_envelope_fail(self):
        with self.assertRaises(ValueError):
            DistanceCounterDecoder(self.config, self.snapshot, 551000, 565225)
        with self.assertRaises(ValueError):
            self.decoder.recover(f32(2**24*self.scale))
        with self.assertRaises(ValueError):
            self.decoder.recover(float('nan'))

    def test_tick_quantization_brackets_include_one_complete_tick(self):
        clock = NativeCounterClock()
        row = clock.row(self.snapshot, self.decoder)
        self.assertEqual(row['latency_s'], .0003)
        self.assertEqual(row['t'], .0001)
        row = clock.row(dict(self.snapshot, start_tick=200, end_tick=201), self.decoder)
        self.assertEqual(row['t'], .01)
        self.assertEqual(row['latency_s'], .0002)
        with self.assertRaises(ValueError):
            clock.row(dict(self.snapshot, start_tick=200, end_tick=201), self.decoder)

    def test_expression_is_bounded_and_has_no_actuator_or_persistent_writes(self):
        expression = snapshot_expression(100)
        self.assertLess(len(expression)+2, 512)
        for forbidden in (b'set-current', b'set-duty', b'set-rpm', b'conf-set', b'spawn', b'loop', b'eeprom'):
            self.assertNotIn(forbidden, expression)
