import importlib.util
import math
import unittest

from vesc_workbench.offset_comparison import fit_hypothesis, match_pose, mean_angle, compare


class ComparisonTests(unittest.TestCase):
    def test_pose_match_is_not_symmetry_fold(self):
        row = dict(encoder_deg=195, offset_deg=1)
        r = match_pose(row, [dict(encoder_deg=285, offset_deg=-2, source='HFI')])
        self.assertFalse(r['same_pose'])
        self.assertIsNone(r['measured_method_difference_deg'])

    def test_same_pose_match_wrap(self):
        r = match_pose(dict(encoder_deg=.1, offset_deg=1),
                       [dict(encoder_deg=359.9, offset_deg=179, source='HFI')])
        self.assertTrue(r['same_pose'])
        self.assertAlmostEqual(r['measured_method_difference_deg'], 2)
        self.assertLess(min(mean_angle([359.9, .1]), 360-mean_angle([359.9, .1])), .001)

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'NumPy analysis-runtime test')
    def test_fit_known_harmonic_is_never_auto_applied(self):
        rows = [dict(encoder_deg=a, offset_deg=-4+6*math.cos(math.radians(4*a)), source=str(a))
                for a in (3, 15, 29, 47, 66, 81)]
        m = fit_hypothesis(rows)
        self.assertLess(m['training_rms_deg'], 1e-9)
        self.assertLess(m['leave_one_pose_out_max_abs_deg'], 1e-9)
        self.assertFalse(m['correction_validated'])
        r = compare(rows, [], [dict(encoder_deg=120, offset_deg=2)])
        self.assertFalse(r['calibration_validated'])
        self.assertFalse(r['motor_commands_sent'])

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'NumPy analysis-runtime test')
    def test_duplicate_and_aliased_poses_rejected(self):
        for angles in ((3, 3, 29, 47), (0, 90, 180, 270)):
            with self.assertRaises(ValueError):
                fit_hypothesis([dict(encoder_deg=a, offset_deg=0) for a in angles])

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'NumPy analysis-runtime test')
    def test_training_fit_does_not_hide_cross_validation_error(self):
        rows = [dict(encoder_deg=a, offset_deg=o) for a, o in
                [(307.6026, -9.7347), (286.5885, -2.0419), (263.4135, .6325), (212.7883, -9.2331)]]
        r = fit_hypothesis(rows)
        self.assertLess(r['training_rms_deg'], .5)
        self.assertGreater(r['leave_one_pose_out_max_abs_deg'], 6)
        self.assertFalse(r['auto_apply_allowed'])
