from dataclasses import replace
from unittest import TestCase
from vesc_workbench.native_probe_client import NativePacketProjector
from vesc_workbench.native_counter_snapshot import f32
from vesc_workbench.uart import VescValues


class NativeProjectorTests(TestCase):
    def setUp(self):
        import math
        self.config = dict(si_wheel_diameter=f32(.083), si_motor_poles=14, si_gear_ratio=1)
        self.scale = f32(self.config['si_wheel_diameter']*math.pi/42)
        self.values = VescValues(27, -50, 0, 0, 0, 0, 0, 0, 24.3, 0, 551843, 565225)
        self.clock = dict(tick_hz_lower=10036, tick_hz_upper=10043)

    def snapshot(self, delta=0, t=10, ticks=1000):
        return dict(distance=f32((551843+delta)*self.scale), distance_abs=f32((565225+delta)*self.scale),
                    position_deg=41, nonce=1, encoder_error_rate=0,
                    host_request_s=t, host_received_s=t+.016, start_tick=ticks, end_tick=ticks+2)

    def test_quiet_calibration_then_moving_counters(self):
        p = NativePacketProjector(self.config, self.clock, 6820)
        v, metadata = p.project(self.values, self.snapshot(), 9.999, self.values)
        self.assertEqual(v.tachometer, self.values.tachometer)
        self.assertEqual(metadata['native_elapsed_ticks'], 0)
        v, metadata = p.project(self.values, self.snapshot(delta=6, t=10.02, ticks=1201), 10.019)
        self.assertEqual(v.tachometer, self.values.tachometer+6)
        self.assertEqual(metadata['native_elapsed_ticks'], 201)
        self.assertEqual(v.current_motor_a, self.values.current_motor_a)

    def test_nonquiet_or_moving_calibration_and_counter_mismatch_rejected(self):
        for confirmation in (None, replace(self.values, current_motor_a=1), replace(self.values, tachometer=551844)):
            with self.assertRaises(ValueError):
                NativePacketProjector(self.config, self.clock, 6820).project(self.values, self.snapshot(), 9.999, confirmation)
        p = NativePacketProjector(self.config, self.clock, 6820)
        p.project(self.values, self.snapshot(), 9.999, self.values)
        with self.assertRaises(ValueError):
            p.project(self.values, self.snapshot(delta=200, t=10.02, ticks=1201), 10.019)

    def test_clock_drift_rejected(self):
        p = NativePacketProjector(self.config, self.clock, 6820)
        p.project(self.values, self.snapshot(), 9.999, self.values)
        with self.assertRaisesRegex(ValueError, 'drift'):
            p.project(self.values, self.snapshot(t=70, ticks=701000), 69.999)
