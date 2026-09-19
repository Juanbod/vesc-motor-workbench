import math
import unittest

from vesc_workbench.hfi_audit import audit_run, synthetic_axis
from vesc_workbench.hfi_capture import analyze_dft
from vesc_workbench.locked_rotor import axial_delta


class AuditTests(unittest.TestCase):
    def capture(self, noisy=False):
        points = []
        for i in range(100):
            for g, value in enumerate((math.radians(i*19 if noisy else 43), 0, 10, 1, 40)):
                if g == 0:
                    value = (value+math.pi) % (2*math.pi)-math.pi
                points.append(dict(t=i*.004+g*.00001, index=i, graph=g, generation=1, value=value))
        report = dict(plot_mode=1, excitation_sent=True, baseline_restored=True,
                      zero_current_verified=True, app_unchanged=True, no_faults=True,
                      errors=[], dispatch_t=0, measurement_response=dict(t=.4), duty=.1,
                      analysis=analyze_dft(points, 207, 2, False, 0))
        return report, points

    def test_tensor_dft_mapping_and_approximation(self):
        for i in range(1800):
            angle = i/10
            self.assertLess(abs(axial_delta(synthetic_axis(angle), angle)), 1e-8)
            self.assertLess(abs(axial_delta(synthetic_axis(angle, True), angle)), .3)

    def test_constant_axis_survives_windows(self):
        r = audit_run(*self.capture())
        self.assertTrue(r['qualified'])
        self.assertEqual(len(r['diagnostic_variants']), 6)
        self.assertLess(r['max_sensitivity_deg'], 1e-8)
        self.assertFalse(r['calibration_validated'])

    def test_rejected_capture_cannot_become_calibration(self):
        r = audit_run(*self.capture(True))
        self.assertFalse(r['qualified'])
        self.assertFalse(r['offset_applied'])

    def test_failed_recovery_and_status_mismatch_rejected(self):
        report, points = self.capture()
        report['baseline_restored'] = False
        with self.assertRaises(ValueError):
            audit_run(report, points)
        report['baseline_restored'] = True
        report['analysis']['status'] = 'invented'
        with self.assertRaises(ValueError):
            audit_run(report, points)
