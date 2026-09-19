from unittest import TestCase
from vesc_workbench.native_counter_tracker import NativeCounterAngle
from vesc_workbench.native_counter_snapshot import f32
from vesc_workbench.counter_angle import guard_speed


class NativeCounterTrackerTests(TestCase):
    def row(self, i):
        count = 550000+12*i
        scale = f32(.006208386)
        return dict(t=100+i*.02, latency_s=.016, position_deg=40,
                    tachometer=count, tachometer_abs=count,
                    native_start_tick=1000+100*i, native_end_tick=1002+100*i,
                    native_elapsed_ticks=100*i, native_tick_hz_lower=10000,
                    native_tick_hz_upper=10005, native_distance_scale=scale,
                    native_distance=f32(count*scale), native_distance_abs=f32(count*scale))

    def test_device_clock_not_usb_delivery_determines_speed(self):
        tracker = NativeCounterAngle(7370)
        for i in range(30):
            evidence = tracker.update(self.row(i))
        self.assertAlmostEqual(evidence['counter_rpm'], 6001.5, places=6)
        self.assertLess(evidence['counter_rpm_lower'], 6000)
        self.assertGreater(evidence['counter_rpm_upper'], 6003)
        guard_speed(evidence, 7370)
        with self.assertRaises(ValueError):
            guard_speed(evidence, 6001)

    def test_missing_metadata_scale_changes_or_clock_reset_fail(self):
        for changes in (dict(native_distance=123), dict(native_tick_hz_upper=11000),
                        dict(native_end_tick=3), dict(native_elapsed_ticks=150)):
            tracker = NativeCounterAngle(7370)
            tracker.update(self.row(0))
            with self.assertRaises(ValueError):
                tracker.update(dict(self.row(1), **changes))
        with self.assertRaises(ValueError):
            NativeCounterAngle(7370).update({})

    def test_coast_cannot_enable_skipped_captures(self):
        with self.assertRaises(ValueError):
            NativeCounterAngle(7370).update_coast(self.row(0), allow_defer=True)
