import math
import unittest

from vesc_workbench.counter_angle import CounterAngle, signed_delta, guard_speed


def sample(t, angle, latency=.0005):
    count = math.floor(angle/30)
    return dict(t=t, position_deg=angle % 360, latency_s=latency,
                tachometer=count, tachometer_abs=abs(count))


class CounterAngleTests(unittest.TestCase):
    def test_6270_envelope_rejects_two_millisecond_capture_brackets(self):
        tracker = CounterAngle(6270)
        with self.assertRaisesRegex(ValueError, 'temporally ambiguous'):
            tracker.update(sample(0, 0, .002))
        tracker = CounterAngle(6270)
        tracker.update(sample(0, 0))
        tracker.update(sample(.004, 0, .002))
        with self.assertRaisesRegex(ValueError, 'temporally ambiguous'):
            tracker.update(sample(.008, 0, .002))

    def test_single_zero_current_ambiguous_capture_keeps_anchor_and_turns(self):
        tracker = CounterAngle(5170, .1, .5)
        tracker.update(sample(0, 0))
        row = dict(sample(.05, 4337*6*.05, .006), current_motor_a=0, id_a=0, iq_a=0, duty=0, fault_code=0)
        self.assertTrue(tracker.update_coast(row, allow_defer=True)['counter_capture_deferred'])
        self.assertEqual(tracker.previous['t'], 0)
        self.assertEqual(tracker.travel, 0)
        evidence = tracker.update_coast(sample(.06, 4337*6*.06), allow_defer=True)
        self.assertAlmostEqual(evidence['counter_travel_deg'], 4337*6*.06)
        self.assertGreater(evidence['counter_step_deg'], 4*360)
        with self.assertRaises(ValueError):
            tracker.update_coast(dict(row, t=.08), allow_defer=True)

    def test_capture_defer_never_applies_to_powered_or_invalid_data(self):
        row = dict(sample(.05, 700, .006), current_motor_a=0, id_a=0, iq_a=0, duty=0, fault_code=0)
        for change in ({'current_motor_a': .2}, {'id_a': .3}, {'duty': .01}, {'fault_code': 4},
                       {'tachometer': 10000}, {'tachometer_abs': -1}, {'t': .101}):
            tracker = CounterAngle(5170, .1, .5)
            tracker.update(sample(0, 0))
            with self.subTest(change=change), self.assertRaises(ValueError):
                tracker.update_coast(dict(row, **change), allow_defer=True)
        tracker = CounterAngle(5170, .1, .5)
        tracker.update(sample(0, 0))
        with self.assertRaises(ValueError):
            tracker.update(row)
        with self.assertRaises(ValueError):
            tracker.update_coast(row)
        tracker.update_coast(row, allow_defer=True)
        with self.assertRaises(ValueError):
            tracker.update_coast(sample(.11, 800), allow_defer=True)

    def test_coast_transition_preserves_turns_across_long_host_gap(self):
        tracker = CounterAngle(2970)
        for i in range(41):
            t = i*.01
            tracker.update(sample(t, 2355*6*t))
        origin = tracker.travel
        tracker.configure_timing(.1, .5)
        for gap in (.05, .099, .049):
            t += gap
            evidence = tracker.update(sample(t, 2355*6*t))
            guard_speed(evidence, 2970)
        self.assertGreater(tracker.travel-origin, 360*7)
        self.assertAlmostEqual(tracker.travel, 2355*6*t)
        self.assertAlmostEqual(evidence['counter_rpm'], 2355)

    def test_coast_window_does_not_waive_bad_counters_or_slow_rpc(self):
        for change in ({'latency_s': .02}, {'tachometer': 0}, {'tachometer_abs': -1}, {'t': .101}):
            tracker = CounterAngle(2970)
            tracker.update(sample(0, 0))
            tracker.configure_timing(.1, .5)
            row = sample(.05, 800)
            row.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                tracker.update(row)
        tracker = CounterAngle(2970)
        tracker.update(sample(0, 0))
        with self.assertRaisesRegex(ValueError, 'gap'):
            tracker.update(sample(.05, 700))
        with self.assertRaises(ValueError):
            tracker.configure_timing(.1, .25)
        self.assertEqual(tracker.gap_s, .025)

    def test_signed_counter_wrap(self):
        self.assertEqual(signed_delta(-2147483648, 2147483647), 1)
        self.assertEqual(signed_delta(2147483647, -2147483648), -1)
        for value in (None, 0.0, True, 2**31):
            with self.assertRaises(ValueError):
                signed_delta(value, 0)

    def test_more_than_one_turn_between_requests(self):
        tracker = CounterAngle(2970)
        for index in range(30):
            t = index*.024
            result = tracker.update(sample(t, 2600*6*t))
        self.assertAlmostEqual(result['counter_rpm'], 2600)
        self.assertLess(result['counter_rpm_lower'], 2600)
        self.assertGreater(result['counter_rpm_upper'], 2600)
        self.assertAlmostEqual(tracker.travel, 2600*6*t)

    def test_request_jitter_bounds_contain_true_speed(self):
        tracker = CounterAngle(2970)
        for index in range(100):
            latency = .003 if index % 3 else .0004
            capture = index*.01
            result = tracker.update(sample(capture + latency, 2200*6*capture, latency))
            if result['counter_window_s'] >= .09:
                self.assertLessEqual(result['counter_rpm_lower'], 2200)
                self.assertGreaterEqual(result['counter_rpm_upper'], 2200)

    def test_missing_corrupt_reset_or_stale_data_rejected(self):
        cases = [dict(t=.026), dict(t=.001, latency_s=.006),
                 dict(tachometer=None), dict(tachometer=100),
                 dict(tachometer=3), dict(tachometer_abs=-1),
                 dict(position_deg=math.nan), dict(t=0)]
        for changes in cases:
            tracker = CounterAngle(2970)
            tracker.update(sample(0, 0, .004))
            row = sample(.01, 0)
            row.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                tracker.update(row)

    def test_reverse_and_overspeed_bounds_stop(self):
        with self.assertRaises(ValueError):
            guard_speed(dict(counter_rpm_lower=-6, counter_rpm_upper=-4), 2970)
        with self.assertRaises(ValueError):
            guard_speed(dict(counter_rpm_lower=2960, counter_rpm_upper=2971), 2970)
        guard_speed(dict(counter_rpm_lower=-.5, counter_rpm_upper=.5), 2970)

    def test_counter_reset_that_looks_like_complete_turn_rejected(self):
        tracker = CounterAngle(2970)
        tracker.update(sample(0, 360))
        with self.assertRaises(ValueError):
            tracker.update(sample(.002, 0))

    def test_frozen_counter_rejected_even_when_each_small_step_looks_plausible(self):
        tracker = CounterAngle(2420)
        tracker.update(sample(0, 0))
        with self.assertRaisesRegex(ValueError, 'Cumulative sector'):
            for index in range(1, 40):
                row = sample(index*.003, index*2)
                row.update(tachometer=0, tachometer_abs=0)
                tracker.update(row)
