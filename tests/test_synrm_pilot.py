import math
import unittest

from test_locked_probe import motor
from vesc_workbench.synrm_pilot import build_pilot, mtpa_targets, validate_observation, encoder_policy, fresh_adc_changes
from vesc_workbench.synrm_pilot import rotation_current, stage_limits
from vesc_workbench.synrm_pilot import adjacent_speed_evidence, speed_stability
from vesc_workbench.wire_config import decode_config, patch_config


class SynrmPilotTests(unittest.TestCase):
    def test_fourth_500rpm_increment_keeps_hold_budgets(self):
        stage = 'speed_2700rpm_5a_hold'
        previous, limits = stage_limits('speed_2200rpm_5a_hold'), stage_limits(stage)
        _, old = build_pilot(self.baseline(), 1.02, 207, 'speed_2200rpm_5a_hold')
        _, candidate = build_pilot(self.baseline(), 1.02, 207, stage)
        a, b = decode_config(old, 'motor'), decode_config(candidate, 'motor')
        self.assertEqual({k for k in a if a[k] != b[k]}, {'l_max_erpm', 'l_min_erpm'})
        self.assertEqual(b['l_max_erpm'], 5940)
        encoder_policy(candidate, stage)
        self.assertEqual(limits['cutoff_rpm']-previous['cutoff_rpm'], 500)
        for key in ('current', 'observed_current', 'trip', 'energy', 'i2t', 'powered_s'):
            self.assertEqual(limits[key], previous[key])
        self.assertLess(2*limits['telemetry_gap_s']*6*limits['maximum_rpm'], 180)
        self.assertEqual(rotation_current(5, 2700, .003, 30, stage), 0)
        for args in ((5, 2970, .003, 30), (5, 2300, .0051, 30)):
            with self.assertRaises(ValueError):
                rotation_current(*args, stage)

    def test_longer_hold_keeps_current_speed_limits_and_stability_criteria(self):
        stage = 'speed_2200rpm_5a_hold'
        previous = stage_limits('speed_2200rpm_5a_smooth')
        limits = stage_limits(stage)
        _, old = build_pilot(self.baseline(), 1.02, 207, 'speed_2200rpm_5a_smooth')
        _, candidate = build_pilot(self.baseline(), 1.02, 207, stage)
        self.assertEqual(candidate, old)
        for key in ('current', 'observed_current', 'input_current', 'trip', 'maximum_rpm',
                    'cutoff_rpm', 'telemetry_gap_s', 'stability_span_rpm', 'stability_slope_rpm_s'):
            self.assertEqual(limits[key], previous[key])
        self.assertEqual((limits['powered_s'], limits['energy'], limits['i2t']), (40, 96, 1000))
        self.assertLess(limits['coast_sample_interval_s'], limits['telemetry_gap_s']/2)
        self.assertEqual(rotation_current(5, 2200, .003, 39, stage), 0)
        with self.assertRaises(ValueError):
            rotation_current(5, 1800, .003, 40, stage)

    def test_third_500rpm_increment_sampling_and_config(self):
        stage = 'speed_2200rpm_5a_smooth'
        previous = stage_limits('speed_1700rpm_5a_smooth')
        limits = stage_limits(stage)
        _, old = build_pilot(self.baseline(), 1.02, 207, 'speed_1700rpm_5a_smooth')
        _, candidate = build_pilot(self.baseline(), 1.02, 207, stage)
        a, b = decode_config(old, 'motor'), decode_config(candidate, 'motor')
        self.assertEqual({k for k in a if a[k] != b[k]}, {'l_max_erpm', 'l_min_erpm'})
        self.assertEqual(b['l_max_erpm'], 4840)
        self.assertEqual(limits['sample_interval_s'], 0)
        encoder_policy(candidate, stage)
        self.assertEqual(limits['cutoff_rpm']-previous['cutoff_rpm'], 500)
        for key in ('current', 'observed_current', 'trip', 'energy', 'i2t', 'powered_s'):
            self.assertEqual(limits[key], previous[key])
        self.assertLess(2*limits['telemetry_gap_s']*6*limits['maximum_rpm'], 180)
        self.assertEqual(rotation_current(5, 2200, .003, 10, stage), 0)
        for args in ((5, 2420, .003, 10), (5, 1800, .0061, 10)):
            with self.assertRaises(ValueError):
                rotation_current(*args, stage)

    def test_second_500rpm_increment_has_unchanged_current_energy_bounds(self):
        stage = 'speed_1700rpm_5a_smooth'
        old_limits, limits = stage_limits('speed_1200rpm_5a_smooth'), stage_limits(stage)
        _, old = build_pilot(self.baseline(), 1.02, 207, 'speed_1200rpm_5a_smooth')
        _, candidate = build_pilot(self.baseline(), 1.02, 207, stage)
        a, b = decode_config(old, 'motor'), decode_config(candidate, 'motor')
        self.assertEqual({k for k in a if a[k] != b[k]}, {'l_max_erpm', 'l_min_erpm'})
        self.assertEqual(b['l_max_erpm'], 3740)
        encoder_policy(candidate, stage)
        self.assertEqual(limits['cutoff_rpm']-old_limits['cutoff_rpm'], 500)
        for key in ('current', 'observed_current', 'trip', 'energy', 'i2t', 'powered_s'):
            self.assertEqual(limits[key], old_limits[key])
        self.assertLess(2*limits['telemetry_gap_s']*6*limits['maximum_rpm'], 180)
        self.assertEqual(rotation_current(5, 1700, .005, 10, stage), 0)
        for args in ((5, 1870, .005, 10), (5, 1400, .0071, 10)):
            with self.assertRaises(ValueError):
                rotation_current(*args, stage)

    def test_500rpm_increment_retains_energy_and_tightens_timing(self):
        stage = 'speed_1200rpm_5a_smooth'
        _, old = build_pilot(self.baseline(), 1.02, 207, 'speed_700rpm_5a_upper')
        _, candidate = build_pilot(self.baseline(), 1.02, 207, stage)
        a, b = decode_config(old, 'motor'), decode_config(candidate, 'motor')
        self.assertEqual({k for k in a if a[k] != b[k]}, {'l_max_erpm', 'l_min_erpm'})
        self.assertEqual(b['l_max_erpm'], 2640)
        encoder_policy(candidate, stage)
        limits = stage_limits(stage)
        previous = stage_limits('speed_700rpm_5a_upper')
        self.assertEqual(limits['cutoff_rpm']-previous['cutoff_rpm'], 500)
        for key in ('current', 'observed_current', 'input_current', 'trip', 'i2t', 'energy', 'powered_s'):
            self.assertEqual(limits[key], previous[key])
        self.assertLess(limits['maximum_rpm']*6*2*limits['telemetry_gap_s'], 180)
        self.assertEqual(rotation_current(5, 1200, .005, 10, stage), 0)
        for args in ((5, 1320, .005, 10), (5, 1000, .0101, 10)):
            with self.assertRaises(ValueError):
                rotation_current(*args, stage)
        row = dict(self.observation(), encoder_rpm=1050, travel_deg=90000,
                   latency_s=.005, encoder_age_s=.005)
        validate_observation(row, 2, dict(source='encoder', age_s=0), True, stage)
        for change in (dict(encoder_rpm=1320), dict(latency_s=.0101),
                       dict(encoder_age_s=.0101), dict(input_energy_j=72), dict(i2t_a2s=600)):
            with self.assertRaises(ValueError):
                validate_observation(dict(row, **change), 2, dict(source='encoder', age_s=0), True, stage)

    def test_next_passport_speed_point_keeps_current_and_hard_bounds(self):
        before, a = build_pilot(self.baseline(), 1.02, 207, 'speed_540rpm_5a_smooth')
        after, b = build_pilot(self.baseline(), 1.02, 207, 'speed_600rpm_5a_smooth')
        self.assertEqual(a, b)
        self.assertEqual(before['bounds'], after['bounds'])
        self.assertEqual(after['rotation_supervisor']['taper_starts_rpm'], 450)
        self.assertEqual(after['rotation_supervisor']['zero_current_rpm'], 600)
        self.assertEqual(rotation_current(5, 600, .01, 10, 'speed_600rpm_5a_smooth'), 0)
        latest, c = build_pilot(self.baseline(), 1.02, 207, 'speed_660rpm_5a_smooth')
        self.assertEqual(b, c)
        self.assertEqual(after['bounds'], latest['bounds'])
        self.assertEqual(latest['rotation_supervisor']['zero_current_rpm'], 660)
        self.assertEqual(rotation_current(5, 660, .01, 10, 'speed_660rpm_5a_smooth'), 0)
        final, d = build_pilot(self.baseline(), 1.02, 207, 'speed_700rpm_5a_smooth')
        self.assertEqual(c, d)
        self.assertEqual(latest['bounds'], final['bounds'])
        self.assertEqual(rotation_current(5, 700, .01, 10, 'speed_700rpm_5a_smooth'), 0)
        upper, e = build_pilot(self.baseline(), 1.02, 207, 'speed_700rpm_5a_upper')
        self.assertEqual(d, e)
        self.assertEqual(final['bounds'], upper['bounds'])
        self.assertEqual(upper['rotation_supervisor']['taper_starts_rpm'], 600)
        self.assertEqual(rotation_current(5, 700, .01, 10, 'speed_700rpm_5a_upper'), 0)

    def test_smooth_stage_keeps_config_and_bounds_but_reduces_current_earlier(self):
        old_plan, old = build_pilot(self.baseline(), 1.02, 207, 'speed_540rpm_5a')
        plan, new = build_pilot(self.baseline(), 1.02, 207, 'speed_540rpm_5a_smooth')
        self.assertEqual(old, new)
        self.assertEqual(old_plan['bounds'], plan['bounds'])
        self.assertEqual(plan['rotation_supervisor']['taper_starts_rpm'], 400)
        self.assertTrue(plan['rotation_supervisor']['cutoff_ends_trial'])
        self.assertEqual(rotation_current(5, 450, .01, 4, 'speed_540rpm_5a'), 5)
        self.assertAlmostEqual(rotation_current(5, 450, .01, 4, 'speed_540rpm_5a_smooth'), 4.97)
        self.assertEqual(rotation_current(5, 540, .01, 4, 'speed_540rpm_5a_smooth'), 0)

    def test_stability_requires_duration_continuity_and_small_speed_change(self):
        stage = 'speed_540rpm_5a_smooth'
        tail = [(i*.01, 460+.1*(i % 3)) for i in range(501)]
        self.assertTrue(speed_stability(tail, stage)['verified'])
        for invalid in (tail[:50], tail[:100]+tail[120:],
                        [(t, 419) for t, _ in tail],
                        [(t, 460+3*t) for t, _ in tail],
                        [(t, 460+11*math.sin(3*t)) for t, _ in tail]):
            self.assertFalse(speed_stability(invalid, stage)['verified'])
        for invalid in ([], [(0, math.nan)], [(1, 460), (0, 460)]):
            with self.assertRaises(ValueError):
                speed_stability(invalid, stage)

    def test_adjacent_speed_evidence_keeps_uncertainty_visible(self):
        evidence = adjacent_speed_evidence(37.617188-2.702636, .0060548, .0054433, .0005629)
        self.assertAlmostEqual(evidence['apparent_rpm'], 961.070886, places=4)
        self.assertLess(evidence['minimum_abs_average_rpm'], 720)
        self.assertGreater(evidence['maximum_abs_average_rpm'], 720)
        fast = adjacent_speed_evidence(60, .01, .0001, .0001)
        self.assertGreater(fast['minimum_abs_average_rpm'], 720)
        self.assertIsNone(adjacent_speed_evidence(1, .01, .001, .02)['maximum_abs_average_rpm'])
        for args in ((1, 0, 0, 0), (math.nan, .01, 0, 0), (1, .01, -.1, 0)):
            with self.assertRaises(ValueError):
                adjacent_speed_evidence(*args)

    def test_five_amp_stage_changes_only_reviewed_current_bounds(self):
        stage = 'speed_540rpm_5a'
        old_plan, old = build_pilot(self.baseline(), 1.02, 207, 'speed_540rpm_3a')
        plan, candidate = build_pilot(self.baseline(), 1.02, 207, stage)
        a, b = decode_config(old, 'motor'), decode_config(candidate, 'motor')
        self.assertEqual({k for k in a if a[k] != b[k]},
                         {'l_current_max', 'l_current_min', 'l_abs_current_max'})
        self.assertEqual((b['l_current_max'], b['l_current_min'], b['l_abs_current_max']), (5, -5, 8))
        before, after = stage_limits('speed_540rpm_3a'), stage_limits(stage)
        self.assertEqual({k for k in before if before[k] != after[k]},
                         {'current', 'observed_current', 'trip', 'i2t'})
        self.assertAlmostEqual(plan['bounds']['ramp_s'], 5/3)
        self.assertEqual(plan['bounds']['maximum_mechanical_rpm'], old_plan['bounds']['maximum_mechanical_rpm'])
        encoder_policy(candidate, stage)

    def test_five_amp_supervisor_keeps_slew_cutoff_and_timing_guards(self):
        stage = 'speed_540rpm_5a'
        self.assertAlmostEqual(rotation_current(3, 400, .01, 2, stage), 3.03)
        self.assertEqual(rotation_current(5, 500, .01, 2, stage), 5)
        self.assertAlmostEqual(rotation_current(5, 530, .01, 2, stage), 4.97)
        self.assertEqual(rotation_current(5, 540, .01, 2, stage), 0)
        self.assertEqual(rotation_current(5, 0, .01, 1, stage), 3)
        for args in ((5.01, 0, .01, 2), (5, 720, .01, 2), (5, 0, .021, 2),
                     (5, 0, .01, 24), (5, -6, .01, 2)):
            with self.assertRaises(ValueError):
                rotation_current(*args, stage)
        with self.assertRaises(ValueError):
            rotation_current(5, 0, .01, 2, 'speed_540rpm_3a')
        with self.assertRaises(ValueError):
            stage_limits('speed_540rpm_60a')

    def test_five_amp_observation_bounds_and_tracking(self):
        stage = 'speed_540rpm_5a'
        row = dict(self.observation(), id_a=-5/math.sqrt(2), iq_a=5/math.sqrt(2),
                   current_motor_a=5, encoder_rpm=500, elapsed_s=23, travel_deg=30000,
                   i2t_a2s=570, input_energy_j=60, latency_s=.005, encoder_age_s=.005)
        source = dict(source='encoder', age_s=0)
        validate_observation(row, 5, source, True, stage)
        for change in (dict(i2t_a2s=600), dict(input_energy_j=72), dict(current_motor_a=6.01),
                       dict(id_a=0), dict(iq_a=0), dict(current_in_a=2.21), dict(encoder_rpm=720),
                       dict(latency_s=.021), dict(fault_code=1), dict(temp_mos_c=51)):
            with self.assertRaises(ValueError):
                validate_observation(dict(row, **change), 5, source, True, stage)

    def observation(self):
        return dict(id_a=-math.sqrt(2), iq_a=math.sqrt(2), current_motor_a=2,
                    current_in_a=.1, v_in=25, duty=.03, encoder_rpm=10,
                    encoder_age_s=.02, travel_deg=2, temp_mos_c=27, fault_code=0,
                    elapsed_s=2, i2t_a2s=5, input_energy_j=2, latency_s=.02)

    def baseline(self, **changes):
        return patch_config(motor(), 'motor', dict(foc_encoder_ratio=2, foc_sl_erpm=4000,
                            foc_motor_ld_lq_diff=14e-6, foc_motor_flux_linkage=-4.24e-5, **changes))

    def test_zero_flux_both_directions_and_zero(self):
        for command in (0, .01, .5, 1, 2, -.5, -2):
            result = mtpa_targets(command, 0, 14e-6)
            self.assertAlmostEqual(result['id_a'], -abs(command)/math.sqrt(2))
            self.assertAlmostEqual(result['iq_a'], command/math.sqrt(2))
            self.assertAlmostEqual(math.hypot(*result.values()), abs(command))

    def test_positive_flux_matches_pinned_formula(self):
        for command in (.01, .5, 2, -2):
            flux, diff = 4e-5, 14e-6
            expected = (flux-math.sqrt(flux**2+8*(diff*command)**2))/(4*diff)
            self.assertAlmostEqual(mtpa_targets(command, flux, diff)['id_a'], expected)

    def test_invalid_math_inputs_rejected(self):
        for values in ((1, -4e-5, 14e-6), (1, 0, 0), (1, 0, -1), (math.nan, 0, 1)):
            with self.assertRaises(ValueError):
                mtpa_targets(*values)

    def test_only_requested_fields_change_and_not_armed(self):
        baseline = self.baseline()
        plan, candidate = build_pilot(baseline, 1.02, 207.2)
        before, after = decode_config(baseline, 'motor'), decode_config(candidate, 'motor')
        for key, value in before.items():
            if key not in plan['changes']:
                self.assertEqual(after[key], value)
        self.assertEqual(after['foc_motor_flux_linkage'], 0)
        self.assertEqual(after['foc_mtpa_mode'], 1)
        self.assertEqual(after['l_abs_current_max'], 3)
        self.assertFalse(plan['auto_apply_allowed'])
        self.assertTrue(plan['live_runner_ready'])
        self.assertFalse(plan['observer_transition']['encoder_only_guaranteed'])

    def test_reference_bound_does_not_raise_motor_speed_limit(self):
        _, candidate = build_pilot(self.baseline(), 1, 207)
        policy = encoder_policy(candidate)
        self.assertEqual(policy['fast_estimator_bound_erpm'], 300000)
        self.assertGreater(policy['enter_encoder_below_erpm'], policy['fast_estimator_bound_erpm'])
        for change in (dict(foc_sl_erpm=4000), dict(foc_f_zv=60000), dict(l_max_erpm=10000)):
            with self.assertRaises(ValueError):
                encoder_policy(patch_config(candidate, 'motor', change))

    def test_power_cycle_only_allows_adc_changes(self):
        baseline = self.baseline()
        current = patch_config(baseline, 'motor', {'foc_offsets_current[0]': 2048.125})
        self.assertEqual(set(fresh_adc_changes(baseline, current)), {'foc_offsets_current[0]'})
        with self.assertRaises(ValueError):
            fresh_adc_changes(baseline, patch_config(current, 'motor', dict(foc_encoder_offset=12)))

    def test_unreviewed_encoder_and_inductance_rejected(self):
        for changes in (dict(foc_encoder_inverted=1), dict(foc_motor_l=1e-6),
                        dict(foc_current_kp=1), dict(foc_sl_erpm=300)):
            with self.assertRaises(ValueError):
                build_pilot(patch_config(self.baseline(), 'motor', changes), 1, 207)
        with self.assertRaises(ValueError):
            build_pilot(self.baseline(), math.nan, 207)

    def test_source_must_be_explicit_and_fresh(self):
        for source in (None, {}, dict(source='observer', age_s=0),
                       dict(source='encoder', age_s=.2)):
            with self.assertRaises(ValueError):
                validate_observation(self.observation(), 2, source, True)
        validate_observation(self.observation(), 2, dict(source='encoder', age_s=.01), True)

    def test_pilot_bounds_and_missing_current(self):
        for changes in (dict(id_a=0), dict(iq_a=0), dict(fault_code=1),
                        dict(travel_deg=10), dict(encoder_rpm=-6), dict(elapsed_s=4),
                        dict(i2t_a2s=16), dict(input_energy_j=8), dict(latency_s=.2),
                        dict(v_in=31), dict(duty=.2), dict(id_a=math.nan)):
            with self.assertRaises(ValueError):
                validate_observation({**self.observation(), **changes}, 2,
                                     dict(source='encoder', age_s=.01), True)

    def test_extension_3a_limits_are_explicit_not_arbitrary_escalation(self):
        plan, candidate = build_pilot(self.baseline(), 1, 207, 'extension_3a')
        decoded = decode_config(candidate, 'motor')
        self.assertEqual(decoded['l_current_max'], 3)
        self.assertEqual(decoded['l_abs_current_max'], 5)
        self.assertEqual(decoded['l_max_erpm'], 120)
        row = {**self.observation(), 'id_a': -3/math.sqrt(2), 'iq_a': 3/math.sqrt(2),
               'current_motor_a': 3, 'travel_deg': 30, 'i2t_a2s': 20}
        validate_observation(row, 3, dict(source='encoder', age_s=0), True, 'extension_3a')
        for changes in (dict(travel_deg=90), dict(id_a=4), dict(i2t_a2s=36)):
            with self.assertRaises(ValueError):
                validate_observation({**row, **changes}, 3, dict(source='encoder', age_s=0), True, 'extension_3a')
        with self.assertRaises(ValueError):
            build_pilot(self.baseline(), 1, 207, 'extension_15a')

    def test_rotation_keeps_current_speed_and_energy_caps(self):
        plan, candidate = build_pilot(self.baseline(), 1, 117, 'rotation_3a')
        _, old = build_pilot(self.baseline(), 1, 117, 'extension_3a')
        self.assertEqual(candidate, old)
        self.assertEqual(plan['bounds']['maximum_powered_s'], 4)
        self.assertEqual(plan['bounds']['maximum_full_event_travel_deg'], 4320)
        row = dict(self.observation(), travel_deg=380)
        validate_observation(row, 2, dict(source='encoder', age_s=0), True, 'rotation_3a')
        for change in (dict(encoder_rpm=60), dict(travel_deg=1440), dict(elapsed_s=4), dict(i2t_a2s=36)):
            with self.assertRaises(ValueError):
                validate_observation(dict(row, **change), 2, dict(source='encoder', age_s=0), True, 'rotation_3a')

    def test_rotation_supervisor_slew_taper_and_priority_cutoff(self):
        self.assertAlmostEqual(rotation_current(0, 0, .02, .02), .06)
        self.assertAlmostEqual(rotation_current(3, 30, .02, 2), 2.94)
        self.assertEqual(rotation_current(3, 35, .02, 2), 0)
        self.assertEqual(rotation_current(3, 59, .02, 2), 0)
        for args in ((0, 0, .2, 1), (4, 0, .02, 1), (0, math.nan, .02, 1),
                     (0, 60, .02, 1), (0, -6, .02, 1), (0, 0, .02, 4)):
            with self.assertRaises(ValueError):
                rotation_current(*args)

    def test_speed_step_changes_speed_not_current_caps(self):
        _, old = build_pilot(self.baseline(), 1.02, 207, 'rotation_3a')
        plan, candidate = build_pilot(self.baseline(), 1.02, 207, 'speed_90rpm_3a')
        a, b = decode_config(old, 'motor'), decode_config(candidate, 'motor')
        self.assertEqual({k for k in a if a[k] != b[k]}, {'l_max_erpm', 'l_min_erpm'})
        self.assertEqual(b['l_max_erpm'], 240)
        self.assertEqual(b['l_current_max'], 3)
        self.assertEqual(b['l_abs_current_max'], 5)
        self.assertEqual(b['l_max_duty'], a['l_max_duty'])
        self.assertEqual(plan['bounds']['maximum_powered_s'], 6)
        encoder_policy(candidate, 'speed_90rpm_3a')
        with self.assertRaises(ValueError):
            encoder_policy(candidate)
        self.assertEqual(rotation_current(3, 50, .02, 5, 'speed_90rpm_3a'), 3)
        self.assertEqual(rotation_current(3, 90, .02, 5, 'speed_90rpm_3a'), 0)
        row = dict(self.observation(), encoder_rpm=80, elapsed_s=5, travel_deg=800)
        validate_observation(row, 2, dict(source='encoder', age_s=0), True, 'speed_90rpm_3a')
        for change in (dict(encoder_rpm=120), dict(elapsed_s=6), dict(i2t_a2s=54), dict(input_energy_j=18), dict(travel_deg=4320)):
            with self.assertRaises(ValueError):
                validate_observation(dict(row, **change), 2, dict(source='encoder', age_s=0), True, 'speed_90rpm_3a')

    def test_second_speed_step_keeps_current_caps_and_tightens_acquisition(self):
        plan, candidate = build_pilot(self.baseline(), 1.02, 207, 'speed_180rpm_3a')
        c = decode_config(candidate, 'motor')
        self.assertEqual(c['l_current_max'], 3)
        self.assertEqual(c['l_abs_current_max'], 5)
        self.assertEqual(c['l_max_erpm'], 480)
        self.assertEqual(plan['bounds']['maximum_telemetry_gap_s'], .05)
        encoder_policy(candidate, 'speed_180rpm_3a')
        self.assertEqual(rotation_current(3, 180, .02, 7, 'speed_180rpm_3a'), 0)
        for args in ((3, 240, .02, 7), (3, 150, .06, 7), (3, 150, .02, 8)):
            with self.assertRaises(ValueError):
                rotation_current(*args, 'speed_180rpm_3a')
        row = dict(self.observation(), encoder_rpm=170, elapsed_s=7, travel_deg=4000)
        validate_observation(row, 2, dict(source='encoder', age_s=0), True, 'speed_180rpm_3a')
        for change in (dict(latency_s=.06), dict(encoder_rpm=240), dict(elapsed_s=8), dict(i2t_a2s=72)):
            with self.assertRaises(ValueError):
                validate_observation(dict(row, **change), 2, dict(source='encoder', age_s=0), True, 'speed_180rpm_3a')

    def test_third_speed_step_has_bounded_unambiguous_sampling(self):
        plan, candidate = build_pilot(self.baseline(), 1.02, 207, 'speed_360rpm_3a')
        decoded = decode_config(candidate, 'motor')
        self.assertEqual(decoded['l_current_max'], 3)
        self.assertEqual(decoded['l_abs_current_max'], 5)
        self.assertEqual(decoded['l_max_erpm'], 960)
        bounds = plan['bounds']
        self.assertLess(bounds['maximum_mechanical_rpm']*6*bounds['maximum_telemetry_gap_s'], 180)
        self.assertEqual(bounds['maximum_powered_s'], 12)
        self.assertEqual(bounds['maximum_recovery_s'], 24)
        encoder_policy(candidate, 'speed_360rpm_3a')
        self.assertEqual(rotation_current(3, 360, .02, 11, 'speed_360rpm_3a'), 0)
        row = dict(self.observation(), encoder_rpm=350, elapsed_s=11, travel_deg=8000)
        validate_observation(row, 2, dict(source='encoder', age_s=0), True, 'speed_360rpm_3a')
        for change in (dict(latency_s=.05), dict(encoder_age_s=.05), dict(encoder_rpm=480),
                       dict(elapsed_s=12), dict(i2t_a2s=108), dict(input_energy_j=36)):
            with self.assertRaises(ValueError):
                validate_observation(dict(row, **change), 2, dict(source='encoder', age_s=0), True, 'speed_360rpm_3a')
        with self.assertRaises(ValueError):
            rotation_current(3, 350, .05, 11, 'speed_360rpm_3a')

    def test_fourth_speed_step_requires_faster_sampling_without_raising_current(self):
        plan, candidate = build_pilot(self.baseline(), 1.02, 207, 'speed_540rpm_3a')
        c = decode_config(candidate, 'motor')
        self.assertEqual(c['l_current_max'], 3)
        self.assertEqual(c['l_abs_current_max'], 5)
        self.assertEqual(c['l_max_erpm'], 1440)
        self.assertEqual(plan['bounds']['requested_sample_pause_s'], .005)
        self.assertLess(720*6*plan['bounds']['maximum_telemetry_gap_s'], 180)
        encoder_policy(candidate, 'speed_540rpm_3a')
        row = dict(self.observation(), encoder_rpm=500, elapsed_s=23, travel_deg=30000,
                   latency_s=.005, encoder_age_s=.005)
        validate_observation(row, 2, dict(source='encoder', age_s=0), True, 'speed_540rpm_3a')
        for change in (dict(latency_s=.021), dict(encoder_rpm=720), dict(elapsed_s=24),
                       dict(i2t_a2s=216), dict(input_energy_j=72)):
            with self.assertRaises(ValueError):
                validate_observation(dict(row, **change), 2, dict(source='encoder', age_s=0), True, 'speed_540rpm_3a')
        with self.assertRaises(ValueError):
            rotation_current(3, 500, .025, 23, 'speed_540rpm_3a')
