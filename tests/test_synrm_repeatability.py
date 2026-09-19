from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from test_synrm_pilot_runner import FakePilotClient
from vesc_workbench.fixture import FixtureInterlock
from vesc_workbench.synrm_pilot import build_pilot
from vesc_workbench.synrm_pilot_runner import repeatability_reference, speed_reference, higher_speed_reference, run_pilot
from vesc_workbench.synrm_repeatability import read_quiet_baseline, run_repeatability
from vesc_workbench.motor_passport import summarize_run
from vesc_workbench.wire_config import patch_config


class RepeatabilityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fixture = self.root/'fixture.json'
        self.fixture.write_text(json.dumps(dict(schema='vesc-fixture-v1', rotor='free', confirmed_by_user=True)))
        fixture_patch = patch('vesc_workbench.fixture.FIXTURE_PATH', self.fixture)
        fixture_patch.start()
        self.addCleanup(fixture_patch.stop)
        encoder_patch = patch('vesc_workbench.synrm_pilot_runner.check_encoder', return_value='SPI error rate: 0.000 %')
        encoder_patch.start()
        self.addCleanup(encoder_patch.stop)
        self.time = [0.0]
        self.clock = lambda: self.time[0]
        self.pause = lambda seconds: self.time.__setitem__(0, self.time[0]+seconds)
        self.client = FakePilotClient(self.time, 'rotation')
        self.baseline = self.client.original
        self.pose = dict(encoder_deg=207.2, offset_deg=1.02,
                         baseline_sha256=hashlib.sha256(self.baseline).hexdigest())

    def seed(self):
        folder = self.root/'seed'
        with patch('vesc_workbench.synrm_pilot_runner.rotation_reference', return_value=dict(starting_pose_deg=207.2)):
            report = run_pilot(self.client, self.baseline, self.pose, folder,
                               clock=self.clock, pause=self.pause, stage='rotation_3a', prior_run='mock')
        self.assertTrue(report['ok'], report)
        final = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        (folder/'final-readback.json').write_text(json.dumps(final))
        return folder

    def test_repeat_plan_keeps_exact_rotation_candidate(self):
        _, rotation = build_pilot(self.baseline, 1.02, 207.2, 'rotation_3a')
        plan, repeat = build_pilot(self.baseline, 1.02, 207.2, 'repeatability_3a')
        self.assertEqual(rotation, repeat)
        self.assertEqual(plan['repeatability']['maximum_repeats'], 3)

    def test_three_distinct_starts_then_no_fourth(self):
        seed = self.seed()
        events = []
        result = run_repeatability(lambda: nullcontext(self.client), self.baseline, self.pose,
                                   self.root/'series', seed, clock=self.clock, pause=self.pause,
                                   progress=events.append)
        self.assertTrue(result['ok'], result)
        self.assertEqual(len(result['trials']), 3)
        self.assertLess(result['total_powered_s'], 12)
        self.assertLess(result['total_i2t_a2s'], 108)
        self.assertTrue(all(r['independent_zero_verified'] for r in result['trials']))
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        self.assertLessEqual(max(self.client.commands), 3)
        self.assertEqual(sum(e['event'] == 'starting' for e in events), 3)
        with self.assertRaises(ValueError):
            repeatability_reference(self.root/'series'/'trial-03', self.baseline)

    def test_speed_step_after_three_starts_preserves_protections(self):
        seed = self.seed()
        series = run_repeatability(lambda: nullcontext(self.client), self.baseline, self.pose,
                                   self.root/'series', seed, clock=self.clock, pause=self.pause)
        self.assertTrue(series['ok'], series)
        prior = self.root/'series'/'trial-03'
        self.assertIn('Completed', speed_reference(prior, self.baseline)['interpretation'])
        with self.assertRaises(ValueError):
            speed_reference(seed, self.baseline)
        self.client.failure = 'speed_rotation'
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        result = run_pilot(self.client, self.baseline, self.pose, self.root/'speed',
                           stage='speed_90rpm_3a', prior_run=prior, entry_readback=entry,
                           clock=self.clock, pause=self.pause)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['status'], 'bounded_speed_increase_observed')
        self.assertGreater(result['powered_s'], 5.5)
        self.assertLess(result['powered_s'], 6)
        self.assertGreater(result['last_powered_observation']['encoder_rpm'], 60)
        self.assertEqual(self.client.motor, self.baseline)
        self.assertLessEqual(max(self.client.commands), 3)
        self.assertEqual(self.client.commands[-1], 0)
        with self.assertRaises(ValueError):
            speed_reference(self.root/'speed', self.baseline)
        final = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        (self.root/'speed'/'final-readback.json').write_text(json.dumps(final))
        higher_speed_reference(self.root/'speed', self.baseline)
        with self.assertRaises(ValueError):
            higher_speed_reference(prior, self.baseline)
        self.client.failure = 'higher_rotation'
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        high = run_pilot(self.client, self.baseline, self.pose, self.root/'higher',
                         stage='speed_180rpm_3a', prior_run=self.root/'speed', entry_readback=entry,
                         clock=self.clock, pause=self.pause)
        self.assertTrue(high['ok'], high)
        self.assertGreater(high['last_powered_observation']['encoder_rpm'], 120)
        self.assertGreater(high['powered_s'], 7.5)
        self.assertLess(high['powered_s'], 8)
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        self.assertLessEqual(max(self.client.commands), 3)
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'higher', self.baseline)
        final = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        (self.root/'higher'/'final-readback.json').write_text(json.dumps(final))
        higher_speed_reference(self.root/'higher', self.baseline, 'speed_360rpm_3a')
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'speed', self.baseline, 'speed_360rpm_3a')
        self.client.failure = 'third_rotation'
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        third = run_pilot(self.client, self.baseline, self.pose, self.root/'third',
                          stage='speed_360rpm_3a', prior_run=self.root/'higher', entry_readback=entry,
                          clock=self.clock, pause=self.pause)
        self.assertTrue(third['ok'], third)
        self.assertGreater(third['last_powered_observation']['encoder_rpm'], 240)
        self.assertGreater(third['powered_s'], 11.5)
        self.assertLess(third['powered_s'], 12)
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'third', self.baseline, 'speed_720rpm_3a')
        final = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        (self.root/'third'/'final-readback.json').write_text(json.dumps(final))
        higher_speed_reference(self.root/'third', self.baseline, 'speed_540rpm_3a')
        self.client.failure = 'fourth_rotation'
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        fourth = run_pilot(self.client, self.baseline, self.pose, self.root/'fourth',
                           stage='speed_540rpm_3a', prior_run=self.root/'third', entry_readback=entry,
                           clock=self.clock, pause=self.pause)
        self.assertTrue(fourth['ok'], fourth)
        self.assertGreater(fourth['last_powered_observation']['encoder_rpm'], 420)
        self.assertGreater(fourth['powered_s'], 23.5)
        self.assertLess(fourth['powered_s'], 24)
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        self.assertLessEqual(max(self.client.commands), 3)
        final = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        (self.root/'fourth'/'final-readback.json').write_text(json.dumps(final))
        higher_speed_reference(self.root/'fourth', self.baseline, 'speed_540rpm_5a')
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'third', self.baseline, 'speed_540rpm_5a')
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        fifth = run_pilot(self.client, self.baseline, self.pose, self.root/'fifth',
                         stage='speed_540rpm_5a', prior_run=self.root/'fourth', entry_readback=entry,
                         clock=self.clock, pause=self.pause)
        # A high-gain plant can oscillate under the simple cutoff supervisor.
        self.assertFalse(fifth['ok'], fifth)
        self.assertEqual(fifth['status'], 'rotation_criterion_not_met')
        self.assertTrue(fifth['zero_current_verified'])
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        self.client.failure = 'fifth_rotation'
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        fifth = run_pilot(self.client, self.baseline, self.pose, self.root/'fifth-stable',
                         stage='speed_540rpm_5a', prior_run=self.root/'fourth', entry_readback=entry,
                         clock=self.clock, pause=self.pause)
        self.assertTrue(fifth['ok'], fifth)
        self.assertGreater(fifth['last_powered_observation']['encoder_rpm'], 420)
        self.assertEqual(max(self.client.commands), 5)
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        self.assertTrue(fifth['zero_current_verified'])
        self.assertLess(fifth['i2t_a2s'], 600)
        self.assertLess(fifth['input_energy_j'], 72)
        # The failed 5 A comparison is not a successful predecessor.
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'fifth', self.baseline, 'speed_540rpm_5a_smooth')
        higher_speed_reference(self.root/'fourth', self.baseline, 'speed_540rpm_5a_smooth')
        self.client.failure = 'fourth_rotation'
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        smooth = run_pilot(self.client, self.baseline, self.pose, self.root/'smooth',
                          stage='speed_540rpm_5a_smooth', prior_run=self.root/'fourth', entry_readback=entry,
                          clock=self.clock, pause=self.pause)
        self.assertFalse(smooth['ok'])
        self.assertTrue(any('Speed cutoff reached' in e for e in smooth['errors']), smooth)
        self.assertTrue(smooth['zero_current_verified'])
        self.assertEqual(self.client.motor, self.baseline)
        # An illustrative quadratic-current plant, not a calibrated motor model.
        self.client.failure = 'quadratic_rotation'
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        smooth = run_pilot(self.client, self.baseline, self.pose, self.root/'smooth-quadratic',
                          stage='speed_540rpm_5a_smooth', prior_run=self.root/'fourth', entry_readback=entry,
                          clock=self.clock, pause=self.pause)
        self.assertTrue(smooth['ok'], smooth)
        self.assertTrue(smooth['speed_stability']['verified'])
        self.assertLess(smooth['speed_stability']['span_rpm'], 20)
        self.assertEqual(max(self.client.commands), 5)
        self.assertTrue(smooth['zero_current_verified'])
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        final = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        (self.root/'smooth-quadratic'/'final-readback.json').write_text(json.dumps(final))
        passport_row = summarize_run(self.root/'smooth-quadratic', self.baseline, 'speed_540rpm_5a_smooth')
        self.assertTrue(passport_row['evidence_verified'])
        self.assertIn('observations.jsonl', passport_row['hashes'])
        higher_speed_reference(self.root/'smooth-quadratic', self.baseline, 'speed_600rpm_5a_smooth')
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'fourth', self.baseline, 'speed_600rpm_5a_smooth')
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        higher = run_pilot(self.client, self.baseline, self.pose, self.root/'passport-next',
                          stage='speed_600rpm_5a_smooth', prior_run=self.root/'smooth-quadratic', entry_readback=entry,
                          clock=self.clock, pause=self.pause)
        self.assertTrue(higher['ok'], higher)
        self.assertTrue(higher['speed_stability']['verified'])
        self.assertGreater(higher['speed_stability']['minimum_rpm'], 480)
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        final = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        (self.root/'passport-next'/'final-readback.json').write_text(json.dumps(final))
        higher_speed_reference(self.root/'passport-next', self.baseline, 'speed_660rpm_5a_smooth')
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'smooth-quadratic', self.baseline, 'speed_660rpm_5a_smooth')
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        latest = run_pilot(self.client, self.baseline, self.pose, self.root/'passport-660',
                          stage='speed_660rpm_5a_smooth', prior_run=self.root/'passport-next', entry_readback=entry,
                          clock=self.clock, pause=self.pause)
        self.assertTrue(latest['ok'], latest)
        self.assertTrue(latest['speed_stability']['verified'])
        self.assertGreater(latest['speed_stability']['minimum_rpm'], 530)
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        final = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        (self.root/'passport-660'/'final-readback.json').write_text(json.dumps(final))
        higher_speed_reference(self.root/'passport-660', self.baseline, 'speed_700rpm_5a_smooth')
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'passport-next', self.baseline, 'speed_700rpm_5a_smooth')
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        upper = run_pilot(self.client, self.baseline, self.pose, self.root/'passport-700',
                         stage='speed_700rpm_5a_smooth', prior_run=self.root/'passport-660', entry_readback=entry,
                         clock=self.clock, pause=self.pause)
        self.assertTrue(upper['ok'], upper)
        self.assertTrue(upper['speed_stability']['verified'])
        self.assertGreater(upper['speed_stability']['minimum_rpm'], 560)
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        final = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        (self.root/'passport-700'/'final-readback.json').write_text(json.dumps(final))
        higher_speed_reference(self.root/'passport-700', self.baseline, 'speed_700rpm_5a_upper')
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'passport-660', self.baseline, 'speed_700rpm_5a_upper')
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        last = run_pilot(self.client, self.baseline, self.pose, self.root/'passport-upper',
                        stage='speed_700rpm_5a_upper', prior_run=self.root/'passport-700', entry_readback=entry,
                        clock=self.clock, pause=self.pause)
        self.assertTrue(last['ok'], last)
        self.assertTrue(last['speed_stability']['verified'])
        self.assertGreater(last['speed_stability']['minimum_rpm'], 600)
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        final = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        (self.root/'passport-upper'/'final-readback.json').write_text(json.dumps(final))
        higher_speed_reference(self.root/'passport-upper', self.baseline, 'speed_1200rpm_5a_smooth')
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'passport-700', self.baseline, 'speed_1200rpm_5a_smooth')
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        increment = run_pilot(self.client, self.baseline, self.pose, self.root/'passport-1200',
                              stage='speed_1200rpm_5a_smooth', prior_run=self.root/'passport-upper',
                              entry_readback=entry, clock=self.clock, pause=self.pause)
        self.assertTrue(increment['ok'], increment)
        self.assertTrue(increment['speed_stability']['verified'])
        self.assertGreater(increment['speed_stability']['minimum_rpm'], 1000)
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        self.assertLessEqual(max(self.client.commands), 5)
        final = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        (self.root/'passport-1200'/'final-readback.json').write_text(json.dumps(final))
        higher_speed_reference(self.root/'passport-1200', self.baseline, 'speed_1700rpm_5a_smooth')
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'passport-upper', self.baseline, 'speed_1700rpm_5a_smooth')
        self.client.failure = 'higher_quadratic_rotation'
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        next_step = run_pilot(self.client, self.baseline, self.pose, self.root/'passport-1700',
                             stage='speed_1700rpm_5a_smooth', prior_run=self.root/'passport-1200',
                             entry_readback=entry, clock=self.clock, pause=self.pause)
        self.assertTrue(next_step['ok'], next_step)
        self.assertTrue(next_step['speed_stability']['verified'])
        self.assertGreater(next_step['speed_stability']['minimum_rpm'], 1400)
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        self.assertLessEqual(max(self.client.commands), 5)
        final = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        (self.root/'passport-1700'/'final-readback.json').write_text(json.dumps(final))
        higher_speed_reference(self.root/'passport-1700', self.baseline, 'speed_2200rpm_5a_smooth')
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'passport-1200', self.baseline, 'speed_2200rpm_5a_smooth')
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        last_step = run_pilot(self.client, self.baseline, self.pose, self.root/'passport-2200',
                             stage='speed_2200rpm_5a_smooth', prior_run=self.root/'passport-1700',
                             entry_readback=entry, clock=self.clock, pause=self.pause)
        self.assertTrue(last_step['ok'], last_step)
        self.assertTrue(last_step['speed_stability']['verified'])
        self.assertGreater(last_step['speed_stability']['minimum_rpm'], 1750)
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        self.assertLessEqual(max(self.client.commands), 5)
        higher_speed_reference(self.root/'passport-1700', self.baseline, 'speed_2200rpm_5a_hold')
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'passport-1200', self.baseline, 'speed_2200rpm_5a_hold')
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        hold = run_pilot(self.client, self.baseline, self.pose, self.root/'passport-2200-hold',
                         stage='speed_2200rpm_5a_hold', prior_run=self.root/'passport-1700',
                         entry_readback=entry, clock=self.clock, pause=self.pause)
        self.assertTrue(hold['ok'], hold)
        self.assertTrue(hold['speed_stability']['verified'])
        self.assertGreater(hold['powered_s'], 39.5)
        self.assertLess(hold['powered_s'], 40)
        self.assertTrue(hold['zero_current_verified'])
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        final = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        (self.root/'passport-2200-hold'/'final-readback.json').write_text(json.dumps(final))
        higher_speed_reference(self.root/'passport-2200-hold', self.baseline, 'speed_2700rpm_5a_hold')
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'passport-1700', self.baseline, 'speed_2700rpm_5a_hold')
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        higher_hold = run_pilot(self.client, self.baseline, self.pose, self.root/'passport-2700-hold',
                                stage='speed_2700rpm_5a_hold', prior_run=self.root/'passport-2200-hold',
                                entry_readback=entry, clock=self.clock, pause=self.pause)
        # This slower hypothetical plant is still accelerating at the deadline.
        self.assertFalse(higher_hold['ok'], higher_hold)
        self.assertFalse(higher_hold['speed_stability']['verified'])
        self.assertGreater(higher_hold['speed_stability']['minimum_rpm'], 1900)
        self.assertTrue(higher_hold['zero_current_verified'])
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        (self.root/'smooth-quadratic'/'result.json').write_text(json.dumps(dict(smooth, speed_stability=dict(verified=False))))
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'smooth-quadratic', self.baseline, 'speed_600rpm_5a_smooth')

    def test_fast_sampling_uses_quiet_window_not_first_noisy_difference(self):
        self.client.failure = 'higher_quadratic_rotation'
        original = self.client.get_values
        injected = []
        def noisy_first_sample():
            row = original()
            if self.client.current > 0 and not injected:
                self.client.pid_position = (self.client.pid_position-.044) % 360
                injected.append(True)
            return row
        self.client.get_values = noisy_first_sample
        with patch('vesc_workbench.synrm_pilot_runner.higher_speed_reference',
                   return_value=dict(starting_pose_deg=self.client.pid_position)):
            entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
            result = run_pilot(self.client, self.baseline, self.pose, self.root/'startup-noise',
                               stage='speed_2200rpm_5a_smooth', prior_run='mock', entry_readback=entry,
                               clock=self.clock, pause=self.pause)
        self.assertTrue(injected)
        self.assertTrue(result['ok'], result)
        self.assertGreaterEqual(result['initial_speed_window_s'], .1)
        self.assertTrue(result['zero_current_verified'])
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)

    def test_fast_sampling_still_rejects_reverse_motion(self):
        self.client.failure = 'reverse'
        with patch('vesc_workbench.synrm_pilot_runner.higher_speed_reference',
                   return_value=dict(starting_pose_deg=self.client.pid_position)):
            entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
            result = run_pilot(self.client, self.baseline, self.pose, self.root/'startup-reverse',
                               stage='speed_2200rpm_5a_smooth', prior_run='mock', entry_readback=entry,
                               clock=self.clock, pause=self.pause)
        self.assertFalse(result['ok'])
        self.assertTrue(result['zero_current_verified'])
        self.assertLess(max(self.client.commands), .2)
        self.assertEqual(self.client.commands[-1], 0)

    def test_timing_violation_sends_zero_before_more_positive_commands(self):
        original = self.client.get_values
        injected = []
        def delayed_sample():
            row = original()
            if self.client.current > 1 and not injected:
                self.pause(.028)
                injected.append(len(self.client.commands))
            return row
        self.client.get_values = delayed_sample
        with patch('vesc_workbench.synrm_pilot_runner.higher_speed_reference',
                   return_value=dict(starting_pose_deg=self.client.pid_position)):
            entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
            result = run_pilot(self.client, self.baseline, self.pose, self.root/'timing-abort',
                               stage='speed_1200rpm_5a_smooth', prior_run='mock', entry_readback=entry,
                               clock=self.clock, pause=self.pause)
        self.assertFalse(result['ok'])
        self.assertGreater(result['timing_abort']['latency_s'], .01)
        self.assertTrue(result['zero_current_verified'])
        self.assertEqual(self.client.motor, self.baseline)
        self.assertTrue(injected)
        self.assertTrue(all(c == 0 for c in self.client.commands[injected[0]:]))
        with self.assertRaises(ValueError):
            higher_speed_reference(self.root/'timing-abort', self.baseline, 'speed_1200rpm_5a_smooth')

    def test_smooth_stage_latches_cutoff_and_keeps_coast_guard(self):
        self.client.failure = 'fourth_rotation'
        get_values = self.client.get_values
        coast_spike = [False]
        def overspeed_sample():
            if self.client.current > 1:
                self.client.rpm = 560
            row = get_values()
            if self.client.was_powered and not self.client.current and not coast_spike[0]:
                self.client.pid_position = (self.client.pid_position+20) % 360
                coast_spike[0] = True
            return row
        self.client.get_values = overspeed_sample
        with patch('vesc_workbench.synrm_pilot_runner.higher_speed_reference',
                   return_value=dict(starting_pose_deg=self.client.pid_position)):
            entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
            result = run_pilot(self.client, self.baseline, self.pose, self.root/'smooth-cutoff',
                               stage='speed_540rpm_5a_smooth', prior_run='mock', entry_readback=entry,
                               clock=self.clock, pause=self.pause)
        self.assertFalse(result['ok'])
        self.assertTrue(any('Speed cutoff reached' in e for e in result['errors']), result)
        self.assertTrue(result['zero_current_verified'])
        self.assertTrue(result['coast_guard_exceeded'])
        self.assertTrue(result['coast_timing_events'])
        self.assertGreater(result['coast_timing_events'][0]['apparent_rpm'], 720)
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)

    def test_five_amp_stage_stall_recovers_without_retry(self):
        self.client.failure = 'stall'
        with patch('vesc_workbench.synrm_pilot_runner.higher_speed_reference',
                   return_value=dict(starting_pose_deg=self.client.pid_position)):
            entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
            result = run_pilot(self.client, self.baseline, self.pose, self.root/'five-stall',
                               stage='speed_540rpm_5a', prior_run='mock', entry_readback=entry,
                               clock=self.clock, pause=self.pause)
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'rotation_criterion_not_met')
        self.assertTrue(result['zero_current_verified'])
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)
        self.assertEqual(max(self.client.commands), 5)

    def test_speed_step_overspeed_and_stale_entry_are_refused(self):
        seed = self.seed()
        # Test the safety path without manufacturing a successful series record.
        with patch('vesc_workbench.synrm_pilot_runner.speed_reference',
                   return_value=dict(starting_pose_deg=self.client.pid_position)):
            entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
            self.client.failure = 'speed_overspeed'
            result = run_pilot(self.client, self.baseline, self.pose, self.root/'overspeed',
                               stage='speed_90rpm_3a', prior_run=seed, entry_readback=entry,
                               clock=self.clock, pause=self.pause)
            self.assertFalse(result['ok'])
            self.assertTrue(result['errors'])
            self.assertTrue(result['zero_current_verified'])
            self.assertEqual(self.client.motor, self.baseline)
            self.assertEqual(self.client.commands[-1], 0)
            self.pause(2)
            with self.assertRaisesRegex(ValueError, 'stale'):
                run_pilot(None, self.baseline, self.pose, self.root/'stale-speed',
                          stage='speed_90rpm_3a', prior_run=seed, entry_readback=entry,
                          clock=self.clock, pause=self.pause)

    def test_stall_stops_series_without_retry(self):
        seed = self.seed()
        self.client.failure = 'stall'
        result = run_repeatability(lambda: nullcontext(self.client), self.baseline, self.pose,
                                   self.root/'series', seed, clock=self.clock, pause=self.pause)
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['trials']), 1)
        self.assertEqual(result['trials'][0]['status'], 'rotation_criterion_not_met')
        self.assertTrue(result['trials'][0]['independent_zero_verified'])
        self.assertEqual(self.client.commands[-1], 0)
        self.assertFalse((self.root/'series'/'trial-02').exists())

    def test_independent_readback_failure_prevents_next_start(self):
        seed = self.seed()
        calls = [0]
        def readback(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 2:
                raise ValueError('injected readback failure')
            return read_quiet_baseline(*args, **kwargs)
        with patch('vesc_workbench.synrm_repeatability.read_quiet_baseline', side_effect=readback):
            result = run_repeatability(lambda: nullcontext(self.client), self.baseline, self.pose,
                                       self.root/'series', seed, clock=self.clock, pause=self.pause)
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['trials']), 1)
        self.assertFalse((self.root/'series'/'trial-02').exists())
        self.assertEqual(self.client.motor, self.baseline)
        self.assertEqual(self.client.commands[-1], 0)

    def test_fresh_start_is_recorded_without_rewriting_historical_pose(self):
        seed = self.seed()
        historical = (seed/'final-readback.json').read_bytes()
        old_pose = json.loads(historical)['samples'][-1]['position_deg']
        self.client.pid_position = (self.client.pid_position+2) % 360
        result = run_repeatability(lambda: nullcontext(self.client), self.baseline, self.pose,
                                   self.root/'series', seed, clock=self.clock, pause=self.pause)
        self.assertTrue(result['trials'][0]['ok'], result)
        first = json.loads((self.root/'series'/'trial-01'/'result.json').read_text())
        self.assertEqual(first['starting_pose_reference']['previous_quiet_deg'], old_pose)
        self.assertGreater(first['starting_pose_reference']['change_from_prior_deg'], 1.5)
        self.assertEqual((seed/'final-readback.json').read_bytes(), historical)

    def test_stale_entry_is_refused_before_any_client_access(self):
        seed = self.seed()
        entry = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        self.pause(2)
        with self.assertRaisesRegex(ValueError, 'stale'):
            run_pilot(None, self.baseline, self.pose, self.root/'stale',
                      clock=self.clock, pause=self.pause, stage='repeatability_3a',
                      prior_run=seed, entry_readback=entry)
        self.assertFalse((self.root/'stale').exists())

    def test_motion_during_preparation_still_refuses_excitation(self):
        seed = self.seed()
        move = [False]
        def progress(event):
            if event['event'] == 'starting':
                move[0] = True
        def pause(seconds):
            self.pause(seconds)
            if move[0]:
                self.client.pid_position = (self.client.pid_position+.8) % 360
                move[0] = False
        result = run_repeatability(lambda: nullcontext(self.client), self.baseline, self.pose,
                                   self.root/'series', seed, clock=self.clock, pause=pause, progress=progress)
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['trials']), 1)
        self.assertFalse(result['trials'][0]['excitation_sent'])
        self.assertEqual(self.client.commands[-1], 0)

    def test_root_stop_file_is_seen_inside_powered_trial(self):
        seed = self.seed()
        events = []
        enabled = [False]
        def progress(event):
            events.append(event)
            if event['event'] == 'starting':
                enabled[0] = True
        def pause(seconds):
            self.pause(seconds)
            if enabled[0] and self.client.current > .5:
                (self.root/'series'/'STOP').touch()
        result = run_repeatability(lambda: nullcontext(self.client), self.baseline, self.pose,
                                   self.root/'series', seed, clock=self.clock, pause=pause, progress=progress)
        self.assertFalse(result['ok'])
        self.assertEqual(len(result['trials']), 1)
        report = json.loads((self.root/'series'/'trial-01'/'result.json').read_text())
        self.assertIn('STOP requested', report['errors'])
        self.assertEqual(self.client.commands[-1], 0)

    def test_reference_rejects_failed_run_and_close_start_pose(self):
        seed = self.seed()
        result = json.loads((seed/'result.json').read_text())
        for change in (dict(ok=False), dict(status='aborted'), dict(coast_guard_exceeded=True)):
            (seed/'result.json').write_text(json.dumps(dict(result, **change)))
            with self.assertRaises(ValueError):
                repeatability_reference(seed, self.baseline)
        (seed/'result.json').write_text(json.dumps(result))
        final = json.loads((seed/'final-readback.json').read_text())
        for row in final['samples']:
            row['position_deg'] = 207.2
        (seed/'final-readback.json').write_text(json.dumps(final))
        with self.assertRaisesRegex(ValueError, 'within 10 degrees'):
            repeatability_reference(seed, self.baseline)

    def test_readback_is_read_only_and_rejects_nonzero_or_config_changes(self):
        self.client.app = patch_config(self.client.app, 'app', dict(app_to_use=0, timeout_msec=300, timeout_brake_current=0))
        report = read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        self.assertTrue(report['zero_current_verified'])
        self.assertEqual(self.client.commands, [])
        self.assertEqual(self.client.writes, 0)
        self.client.current = 1
        with self.assertRaises(FixtureInterlock):
            read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)
        self.client.current = 0
        self.client.motor = patch_config(self.baseline, 'motor', dict(foc_encoder_offset=77))
        with self.assertRaises(ValueError):
            read_quiet_baseline(self.client, self.baseline, clock=self.clock, pause=self.pause)

    def test_locked_cli_never_opens_serial(self):
        self.fixture.write_text(json.dumps(dict(schema='vesc-fixture-v1', rotor='locked', confirmed_by_user=True)))
        script = Path(__file__).resolve().parents[1]/'scripts'/'run-synrm-repeatability.py'
        argv = [str(script), '--armed-free-rotor', '--baseline', 'absent.bin',
                '--hfi-summary', 'absent.json', '--prior-run', 'absent', '--output', str(self.root/'series')]
        with patch('sys.argv', argv), patch('vesc_workbench.locked_probe.ProbeClient') as factory:
            with self.assertRaises(FixtureInterlock):
                runpy.run_path(str(script), run_name='__main__')
            factory.assert_not_called()
