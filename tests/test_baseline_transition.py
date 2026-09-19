from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from test_synrm_pilot_runner import FakePilotClient
from vesc_workbench.baseline_transition import adc_transition, transfer_pose, transfer_counter_evidence
from vesc_workbench.synrm_pilot import stage_limits
from vesc_workbench.synrm_pilot_runner import higher_speed_reference
from vesc_workbench.wire_config import patch_config, decode_config


class BaselineTransitionTests(TestCase):
    def setUp(self):
        self.old = patch_config(FakePilotClient([0.]).original, 'motor',
                                {f'foc_offsets_current[{i}]':2048 for i in range(3)})
        self.values = decode_config(self.old, 'motor')
        self.new = patch_config(self.old, 'motor', {'foc_offsets_current[0]': self.values['foc_offsets_current[0]']+.5})

    def test_adc_only_transfer_preserves_original_provenance(self):
        transition = adc_transition(self.old, self.new)
        pose = dict(baseline_sha256=transition['reference_sha256'], offset_deg=1.02)
        result = transfer_pose(pose, self.old, self.new)
        self.assertEqual(result['offset_deg'], pose['offset_deg'])
        self.assertEqual(result['baseline_transition'], transition)
        self.assertEqual(result['baseline_sha256'], transition['actual_sha256'])
        self.assertNotEqual(pose['baseline_sha256'], result['baseline_sha256'])
        with self.assertRaises(ValueError):
            transfer_pose(dict(pose, baseline_sha256='wrong'), self.old, self.new)

    def test_large_adc_or_any_motor_setting_change_rejected(self):
        for changes in ({'foc_offsets_current[0]': self.values['foc_offsets_current[0]']+3},
                        {'foc_offsets_voltage[0]': .1}, {'foc_encoder_offset': 90},
                        {'si_motor_poles': 4}, {'l_current_max': 70}):
            with self.assertRaises(ValueError):
                adc_transition(self.old, patch_config(self.old, 'motor', changes))

    def test_speed_reference_audits_original_not_relabelled_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/'mcconf-before.bin').write_bytes(self.old)
            with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run', return_value={'source':temp}) as audit:
                result = higher_speed_reference(temp, self.new, 'speed_540rpm_5a_restart')
                audit.assert_called_once_with(temp, self.old, 'speed_9200rpm_10p5a_dq_return075')
                self.assertIn('baseline_transition', result)
            with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run', side_effect=ValueError('failed run')):
                with self.assertRaises(ValueError):
                    higher_speed_reference(temp, self.new, 'speed_540rpm_5a_restart')

    def test_counter_reference_is_replayed_before_transfer(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/'mcconf-before.bin').write_bytes(self.old)
            with patch('vesc_workbench.counter_angle.audit_counter_reference', return_value={'measurement_agreement_verified':True}) as audit:
                result = transfer_counter_evidence(temp, self.new)
                audit.assert_called_once_with(temp, self.old)
                self.assertTrue(result['measurement_agreement_verified'])
                self.assertIn('baseline_transition', result)

    def test_restart_stage_is_the_previously_tested_low_speed_envelope(self):
        self.assertEqual(stage_limits('speed_540rpm_5a_restart'), stage_limits('speed_540rpm_5a_smooth'))
        old = stage_limits('speed_540rpm_5a_restart')
        new = stage_limits('speed_540rpm_5a_restart_return075')
        self.assertEqual({k:v for k,v in new.items() if old.get(k) != v},
                         dict(return_current_a=.075, minimum_voltage=21, maximum_voltage=24.9))
