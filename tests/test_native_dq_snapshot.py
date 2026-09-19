import json
from pathlib import Path
from struct import pack
import tempfile
from unittest import TestCase
from unittest.mock import Mock, patch

from vesc_workbench.native_counter_snapshot import (
    DQ_SNAPSHOT_METHOD, SNAPSHOT_METHOD, prepared_expression, read_counter_snapshot,
    validate_dq_record,
)
from vesc_workbench.synrm_pilot import stage_limits, timing_stage, build_pilot
from vesc_workbench.synrm_pilot_runner import verify_native_runtime, higher_speed_reference


class NativeDqSnapshotTests(TestCase):
    def packet(self, vd=-.5, end=105):
        return bytes((36,))+pack('>IIIfffIfffffI', 6820, 123, 100, 2., 3., 10., 102,
                                0., vd, -.12, -7., 7., end)

    def read(self, payload, **options):
        client = Mock()
        client.read_response.return_value = payload
        return read_counter_snapshot(client, 123, clock=iter((1., 1.01)).__next__, **options)

    def test_readonly_expression_fits_existing_repl_bound(self):
        expression = prepared_expression('wbcs123456789abc', dq=True)
        self.assertLess(len(expression), 512)
        for token in (b'get-vd', b'get-vq', b'get-id', b'get-iq', b'array-create 52'):
            self.assertIn(token, expression)
        for token in (b'set-current', b'set-duty', b'set-rpm', b'spawn', b'loop', b'flash'):
            self.assertNotIn(token, expression)

    def test_v2_decode_and_legacy_reject_are_separate(self):
        row = self.read(self.packet(), dq=True)
        self.assertEqual(row['dq_vd_v'], -.5)
        self.assertEqual(row['dq_id_a'], -7)
        self.assertEqual(row['dq_end_tick'], 105)
        self.assertEqual(row['end_tick'], 102)
        self.assertEqual(row['raw_payload_hex'], self.packet().hex())
        with self.assertRaises(ValueError):
            self.read(self.packet())
        legacy = bytes((36,))+pack('>IIIfffIf', 6817, 123, 100, 2., 3., 10., 102, 0.)
        self.assertEqual(self.read(legacy)['end_tick'], 102)
        with self.assertRaises(ValueError):
            self.read(legacy, dq=True)

    def test_bad_native_diagnostics_are_rejected(self):
        for payload in (self.packet(float('nan')), self.packet(end=203), self.packet()[:-1]):
            with self.assertRaises(ValueError):
                self.read(payload, dq=True)
        row = dict(native_end_tick=0xfffffffe, native_dq_end_tick=2,
                   native_dq_vd_v=.1, native_dq_vq_v=-.1, native_dq_id_a=-7, native_dq_iq_a=7)
        validate_dq_record(row)
        for changes in (dict(native_dq_end_tick=101), dict(native_dq_vd_v=float('inf')),
                        dict(native_dq_end_tick=2.), dict(native_dq_iq_a=None)):
            with self.assertRaises(ValueError):
                validate_dq_record(dict(row, **changes))

    def test_runtime_version_must_match_expected_stage(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'native-runtime.json'
            for method, dq in ((SNAPSHOT_METHOD, False), (DQ_SNAPSHOT_METHOD, True)):
                path.write_text(json.dumps(dict(method=method, installed=True, removed=True, flash_writes=False)))
                verify_native_runtime(temp, dq=dq)
                with self.assertRaises(ValueError):
                    verify_native_runtime(temp, dq=not dq)

    def test_diagnostic_stages_preserve_motor_configuration_and_predecessors(self):
        from test_counter_runner import CounterClient
        from vesc_workbench.wire_config import patch_config
        client = CounterClient([0.0])
        baseline = patch_config(client.original, 'motor', {'l_max_vin': 60})
        for stage, prior in (('speed_8200rpm_10a_dq', 'speed_8200rpm_10a_native60'),
                             ('speed_8700rpm_10a_dq', 'speed_8200rpm_10a_dq')):
            limits = stage_limits(stage)
            old_stage = stage.replace('_dq', '_native60')
            self.assertEqual({k:v for k,v in limits.items() if k != 'native_dq'}, stage_limits(old_stage))
            self.assertEqual(build_pilot(baseline, 1.02, 207.2, stage)[1],
                             build_pilot(baseline, 1.02, 207.2, old_stage)[1])
            with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
                higher_speed_reference('prior', baseline, stage)
                audit.assert_called_once_with('prior', baseline, prior)
        self.assertEqual(timing_stage('speed_8200rpm_10a_dq'), 'speed_8200rpm_10a_dq')
        self.assertEqual(timing_stage('speed_8700rpm_10a_dq'), 'speed_8200rpm_10a_dq')

    def test_small_return_diagnostic_keeps_independent_battery_guard(self):
        from test_counter_runner import CounterClient
        from vesc_workbench.wire_config import patch_config, decode_config
        from vesc_workbench.battery_return import BatteryReturnMonitor
        baseline = patch_config(CounterClient([0.0]).original, 'motor', {'l_max_vin': 60})
        stage = 'speed_8700rpm_10a_dq_return075'
        plan, candidate = build_pilot(baseline, 1.02, 207.2, stage)
        old = decode_config(build_pilot(baseline, 1.02, 207.2, 'speed_8700rpm_10a_dq')[1], 'motor')
        new = decode_config(candidate, 'motor')
        self.assertEqual({k for k in old if old[k] != new[k]}, {'l_in_current_min'})
        self.assertAlmostEqual(new['l_in_current_min'], -.075)
        self.assertEqual(plan['bounds']['maximum_sampled_return_current_a'], .1)
        self.assertEqual(plan['bounds']['maximum_sampled_return_energy_j'], .25)
        for row in (dict(t=1, v_in=24, current_in_a=-.101), dict(t=1, v_in=25, current_in_a=0)):
            with self.assertRaises(ValueError):
                BatteryReturnMonitor().observe(row)
        with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
            higher_speed_reference('prior', baseline, stage)
            audit.assert_called_once_with('prior', baseline, 'speed_8200rpm_10a_dq')
        self.assertEqual(timing_stage(stage), 'speed_8200rpm_10a_dq')

    def test_next_return_stage_keeps_electrical_limits(self):
        stage = 'speed_9200rpm_10a_dq_return075'
        old = stage_limits('speed_8700rpm_10a_dq_return075')
        new = stage_limits(stage)
        changes = {k: v for k,v in new.items() if old[k] != v}
        self.assertEqual(changes, dict(taper_start_rpm=8800, cutoff_rpm=9200,
                                      maximum_rpm=10120, minimum_finish_rpm=8750,
                                      travel=3643200, full_travel=9472320))
        with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
            higher_speed_reference('prior', b'baseline', stage)
            audit.assert_called_once_with('prior', b'baseline', 'speed_8700rpm_10a_dq_return075')

    def test_same_speed_small_current_step_keeps_speed_and_battery_bounds(self):
        stage = 'speed_9200rpm_10p5a_dq_return075'
        old = stage_limits('speed_9200rpm_10a_dq_return075')
        new = stage_limits(stage)
        self.assertEqual({k:v for k,v in new.items() if old[k] != v},
                         dict(current=10.5, observed_current=12.6, trip=14, i2t=6615, energy=661.5))
        self.assertEqual(new['i2t'], new['current']**2*new['powered_s'])
        with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
            higher_speed_reference('prior', b'baseline', stage)
            audit.assert_called_once_with('prior', b'baseline', 'speed_8700rpm_10a_dq_return075')
        self.assertEqual(timing_stage(stage), 'speed_9200rpm_10a_dq_return075')
