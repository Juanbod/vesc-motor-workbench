import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_locked_probe import motor
from vesc_workbench.battery_return import BatteryReturnMonitor, audit_battery_return, require_battery_source
from vesc_workbench.synrm_pilot import build_pilot, stage_limits
from vesc_workbench.wire_config import patch_config, decode_config


def row(t, current=0, voltage=24.5):
    return dict(t=t, current_in_a=current, v_in=voltage)


class BatteryReturnTests(unittest.TestCase):
    def test_small_budget_and_positive_power_do_not_cancel_returned_energy(self):
        monitor = BatteryReturnMonitor()
        monitor.observe(row(0, -.01))
        monitor.observe(row(.1, -.01))
        monitor.observe(row(.2, .1))
        monitor.observe(row(.3, .1))
        self.assertAlmostEqual(monitor.energy_j, .049)

    def test_budget_trip_latches_but_allows_zero_current_recovery(self):
        monitor = BatteryReturnMonitor()
        monitor.observe(row(0, -.05))
        with self.assertRaisesRegex(ValueError, 'returned-energy'):
            monitor.observe(row(.3, -.05))
        monitor.observe(row(.4))
        self.assertTrue(monitor.exceeded)
        self.assertGreater(monitor.energy_j, .25)

    def test_voltage_current_nan_and_ordering_rejected(self):
        for bad in (row(1, voltage=24.9), row(1, voltage=20.9), row(1, -.11),
                    row(1, voltage=math.nan), row(0)):
            monitor = BatteryReturnMonitor()
            monitor.observe(row(0))
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                monitor.observe(bad)
            self.assertTrue(monitor.exceeded)

    def test_replay_includes_returned_energy_on_coast(self):
        monitor = BatteryReturnMonitor()
        rows = []
        for item in (row(0), row(.1, -.02), row(.2, -.02), row(.3)):
            rows.append(dict(item, returned_energy_j=monitor.observe(item)))
        self.assertAlmostEqual(audit_battery_return(rows), .147)
        rows[-1]['returned_energy_j'] = 0
        with self.assertRaises(ValueError):
            audit_battery_return(rows)

    def test_source_must_be_reviewed_battery_not_supply(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'battery.json'
            source = dict(schema='bench-battery-v1', source='battery', confirmed_by_user=True,
                          series_cells=6, parallel_cells=1, capacity_ah=4.5)
            path.write_text(json.dumps(source))
            with patch('vesc_workbench.battery_return.BATTERY_PATH', path):
                self.assertEqual(require_battery_source(), source)
                source['source'] = 'bench_supply'
                path.write_text(json.dumps(source))
                with self.assertRaises(ValueError):
                    require_battery_source()

    def test_short_probe_changes_only_reviewed_protections(self):
        baseline = patch_config(motor(), 'motor', dict(foc_encoder_ratio=2,
            foc_sl_erpm=4000, foc_motor_ld_lq_diff=14e-6, foc_motor_flux_linkage=-4.24e-5, l_max_vin=60))
        plan, candidate = build_pilot(baseline, 1.02, 175, 'speed_90rpm_2a_return_probe')
        values = decode_config(candidate, 'motor')
        self.assertAlmostEqual(values['l_in_current_min'], -.05)
        self.assertAlmostEqual(values['l_max_vin'], 24.9, places=4)
        self.assertEqual(values['l_current_max'], 2)
        self.assertEqual(values['l_abs_current_max'], 3)
        self.assertEqual(stage_limits('speed_90rpm_2a_return_probe')['powered_s'], 4)
        self.assertEqual(plan['bounds']['maximum_sampled_return_energy_j'], .25)

    def test_peak_margin_does_not_increase_command_or_slow_the_trip(self):
        original = stage_limits('speed_90rpm_2a_return_probe')
        revised = stage_limits('speed_90rpm_2a_return_margin')
        self.assertEqual({key: value for key, value in revised.items() if key != 'trip'},
                         {key: value for key, value in original.items() if key != 'trip'})
        self.assertEqual(revised['trip'], 4)

    def test_high_speed_return_stage_keeps_current_and_speed_envelope(self):
        original = stage_limits('speed_2700rpm_6a_counter')
        revised = stage_limits('speed_2700rpm_6a_counter_return')
        for key in original:
            self.assertEqual(revised[key], original[key])
        self.assertEqual(revised['return_current_a'], .05)
        self.assertEqual(revised['maximum_voltage'], 24.9)
