from unittest import TestCase
from vesc_workbench.native_clock_calibration import calibrate_clock


class NativeClockTests(TestCase):
    def rows(self, rate=10040):
        return [dict(host_request_s=i*.02, host_received_s=i*.02+.002,
                     end_tick=round((i*.02+.001)*rate)) for i in range(3001)]

    def test_bounds_contain_actual_rate_not_nominal_assumption(self):
        result = calibrate_clock(self.rows())
        self.assertLessEqual(result['tick_hz_lower'], 10040)
        self.assertGreaterEqual(result['tick_hz_upper'], 10040)
        self.assertFalse(result['nominal_10000hz_consistent'])

    def test_short_invalid_or_reset_data_rejected(self):
        with self.assertRaises(ValueError):
            calibrate_clock(self.rows()[:100])
        rows = self.rows()
        rows[100]['end_tick'] = 0
        with self.assertRaises(ValueError):
            calibrate_clock(rows)

    def test_inconsistent_rate_drift_rejected(self):
        rows = self.rows()
        for i in range(1500, len(rows)):
            rows[i]['end_tick'] += (i-1500)*2
        with self.assertRaises(ValueError):
            calibrate_clock(rows)
