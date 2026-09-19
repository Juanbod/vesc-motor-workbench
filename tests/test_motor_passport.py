import hashlib
import tempfile
import unittest
from pathlib import Path

from test_locked_probe import motor
from vesc_workbench.motor_passport import build_passport, render_markdown, dc_window_statistics, speed_limit_assessment


class PassportTests(unittest.TestCase):
    def test_governed_plateau_is_not_claimed_as_maximum(self):
        rows = [dict(t=t, v_in=24, current_in_a=.04, encoder_rpm=564, command_a=3) for t in (0, 1, 2)]
        result = speed_limit_assessment(rows, 'speed_660rpm_5a_smooth')
        self.assertEqual(result['classification'], 'host_taper_limited')
        self.assertFalse(result['maximum_speed_established'])
        self.assertIsNone(result['mechanical_rating_rpm'])
        for row in rows:
            row['command_a'] = 5
        result = speed_limit_assessment(rows, 'speed_660rpm_5a_smooth')
        self.assertFalse(result['maximum_speed_established'])
        self.assertEqual(result['classification'], 'maximum_not_established')

    def test_dc_power_averages_products_with_time_weights(self):
        rows = [dict(t=t, v_in=v, current_in_a=i, encoder_rpm=r)
                for t, v, i, r in ((0, 10, 1, 100), (1, 10, 2, 200), (3, 20, 3, 300))]
        result = dc_window_statistics(rows)
        self.assertAlmostEqual(result['mean_input_power_w_estimate'], 140/3)
        self.assertAlmostEqual(result['mean_rpm'], 800/3)
        self.assertNotAlmostEqual(result['mean_input_power_w_estimate'], result['mean_voltage_v']*result['mean_input_current_a'])
        self.assertFalse(result['external_calibration'])
        self.assertIsNone(result['shaft_power_w'])

    def test_dc_power_retains_sign_and_rejects_bad_samples(self):
        rows = [dict(t=t, v_in=24, current_in_a=-.1, encoder_rpm=100) for t in (0, 1)]
        self.assertAlmostEqual(dc_window_statistics(rows)['mean_input_power_w_estimate'], -2.4)
        for invalid in ([], rows[:1], [rows[0], rows[0]], [rows[0], dict(rows[1], v_in=float('nan'))]):
            with self.assertRaises(ValueError):
                dc_window_statistics(invalid)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        raw = motor()
        (self.root/'baseline.bin').write_bytes(raw)
        self.manifest = dict(schema='motor-passport-input-v1', specimen='test', revision='test',
                             baseline='baseline.bin', baseline_sha256=hashlib.sha256(raw).hexdigest(),
                             user_reported=['delta'], engineering_interpretation=['provisional'], runs=[])

    def test_missing_ratings_are_null_not_copied_from_controller(self):
        data = build_passport(self.manifest, self.root)
        for key in ('rated_voltage_v', 'rated_current_a', 'rated_power_w', 'rated_torque_nm',
                    'rated_speed_rpm', 'maximum_permitted_rpm', 'motor_efficiency', 'duty_type'):
            self.assertIsNone(data[key])
        self.assertFalse(data['automatic_excitation'])
        self.assertEqual(data['verified_runs'], [])
        text = render_markdown(data)
        self.assertIn('НЕ ЗАВЕРШЁН', text)
        self.assertIn('не определены', text)

    def test_missing_run_is_listed_not_accepted_or_silently_ignored(self):
        self.manifest['runs'] = [dict(path='not-run', stage='speed_600rpm_5a_smooth')]
        data = build_passport(self.manifest, self.root)
        self.assertEqual(data['verified_runs'], [])
        self.assertEqual(len(data['excluded_runs']), 1)
        self.assertIn('not-run', render_markdown(data))

    def test_wrong_baseline_is_rejected(self):
        self.manifest['baseline_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'digest'):
            build_passport(self.manifest, self.root)
