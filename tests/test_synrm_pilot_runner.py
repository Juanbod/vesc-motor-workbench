import hashlib
import json
import math
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_locked_probe import motor, app
from vesc_workbench.fixture import FixtureInterlock
from vesc_workbench.synrm_pilot_runner import run_pilot, check_encoder, rotation_reference
from vesc_workbench.synrm_pilot import build_pilot
from vesc_workbench.uart import VescFirmwareVersion, VescValues
from vesc_workbench.wire_config import patch_config


class FakePilotClient:
    def __init__(self, clock, failure=''):
        self.clock, self.failure = clock, failure
        self.serial = SimpleNamespace(timeout=.1)
        self.motor = patch_config(motor(), 'motor', dict(foc_encoder_ratio=2,
            foc_sl_erpm=4000, foc_motor_ld_lq_diff=14e-6, foc_motor_flux_linkage=-4.24e-5))
        self.app = app()
        self.original = self.motor
        if failure == 'power_cycle':
            self.motor = patch_config(self.motor, 'motor', {'foc_offsets_current[0]': 2048.125})
        self.entry = self.motor
        self.pid_position = 207.2
        self.current = 0
        self.was_powered = False
        self.commands = []
        self.writes = 0
        self.coast_samples = 0
        self.rpm = 0.0
        self.last_sample_t = clock[0]

    def fw_version(self):
        return VescFirmwareVersion(6, 2, 'MKSESC_84_100_HP')

    def get_raw_config(self, kind):
        if kind == 'motor' and self.failure == 'mismatch' and self.writes == 1:
            return patch_config(self.motor, 'motor', dict(l_current_max=4))
        return self.motor if kind == 'motor' else self.app

    def set_raw_config(self, kind, data):
        self.writes += 1
        self.motor = data

    def read_response(self, code):
        return bytes([code])

    def set_app_config_temporary(self, data):
        self.app = data

    def set_current(self, value):
        self.commands.append(value)
        self.current = value
        self.was_powered |= value > 0

    def get_values(self):
        self.clock[0] += getattr(self, 'read_latency_s', .002)
        dt = self.clock[0]-self.last_sample_t
        self.last_sample_t = self.clock[0]
        if self.was_powered and self.failure in ('disconnect', 'permanent_disconnect'):
            if self.failure == 'disconnect':
                self.failure = ''
            raise TimeoutError('Injected telemetry loss')
        if self.failure in ('quadratic_rotation', 'higher_quadratic_rotation'):
            # Hypothetical plants exercise logic; neither predicts the real motor.
            gain = 12 if self.failure == 'higher_quadratic_rotation' else 7.5
            self.rpm = max(0, self.rpm+(gain*self.current**2-.13*self.rpm-5)*dt)
            self.pid_position = (self.pid_position+6*self.rpm*dt) % 360
        elif self.failure in ('rotation', 'overspeed', 'speed_rotation', 'speed_overspeed', 'higher_rotation', 'third_rotation', 'fourth_rotation', 'fifth_rotation'):
            gain = {'fifth_rotation': 150, 'fourth_rotation': 350, 'third_rotation': 250, 'higher_rotation': 165, 'speed_rotation': 65}.get(self.failure, 25)
            self.rpm = max(0, self.rpm+(gain*self.current-1.5*self.rpm)*dt)
            if self.failure in ('overspeed', 'speed_overspeed') and self.current > 1:
                self.rpm = 160 if self.failure == 'speed_overspeed' else 100
            self.pid_position = (self.pid_position+6*self.rpm*dt) % 360
        elif self.current and self.failure != 'stall':
            self.pid_position += -.3 if self.failure == 'reverse' else .12
        if self.was_powered and not self.current and self.failure == 'coast':
            self.coast_samples += 1
            if self.coast_samples <= 30:
                self.pid_position += .3
        id_a = -self.current/math.sqrt(2)
        if self.failure == 'no_id':
            id_a = 0
        return VescValues(temp_mos_c=26, temp_motor_c=-50, current_motor_a=self.current,
                          current_in_a=.05 if self.current else 0, id_a=id_a,
                          iq_a=self.current/math.sqrt(2), duty=.02 if self.current else 0,
                          erpm=9999, v_in=25, fault_code=0)


class PilotRunnerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fixture = self.root/'fixture.json'
        self.fixture.write_text(json.dumps(dict(schema='vesc-fixture-v1', rotor='free', confirmed_by_user=True)))
        p = patch('vesc_workbench.fixture.FIXTURE_PATH', self.fixture)
        p.start()
        self.addCleanup(p.stop)

    def execute(self, failure='', stage='pilot'):
        clock = [0.0]
        c = FakePilotClient(clock, failure)
        pose = dict(encoder_deg=207.2, offset_deg=1.02,
                    baseline_sha256=hashlib.sha256(c.original).hexdigest())
        def pause(seconds):
            clock[0] += seconds
            if failure == 'stop_file':
                (self.root/'run'/'STOP').touch(exist_ok=True)
        with patch('vesc_workbench.synrm_pilot_runner.check_encoder', return_value='SPI error rate: 0.000 %'), \
             patch('vesc_workbench.synrm_pilot_runner.extension_reference', return_value=dict(starting_pose_deg=207.2)), \
             patch('vesc_workbench.synrm_pilot_runner.rotation_reference', return_value=dict(starting_pose_deg=207.2)):
            result = run_pilot(c, c.original, pose, self.root/'run',
                               clock=lambda: clock[0], pause=pause, stage=stage,
                               prior_run='mock-prior' if stage != 'pilot' else None)
        return result, c

    def test_one_local_motion_trial_restores_and_does_not_use_observer_erpm(self):
        result, c = self.execute()
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['motion_observed'])
        self.assertEqual(c.motor, c.original)
        self.assertEqual(c.commands[-1], 0)
        self.assertLessEqual(max(c.commands), 2)
        self.assertFalse(result['offset_calibrated'])
        self.assertTrue((self.root/'run'/'observations.jsonl').exists())

    def test_stall_is_not_success(self):
        result, c = self.execute('stall')
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'no_verified_motion')
        self.assertTrue(result['baseline_restored'])
        self.assertEqual(c.commands[-1], 0)

    def test_extension_reaches_3a_and_observes_longer_without_speed_command(self):
        result, c = self.execute(stage='extension_3a')
        self.assertTrue(result['ok'], result)
        self.assertEqual(max(c.commands), 3)
        self.assertGreater(result['powered_s'], 3)
        self.assertLess(result['powered_s'], 4)
        self.assertEqual(c.commands[-1], 0)

    def test_coast_envelope_is_not_reported_as_qualified(self):
        result, c = self.execute('coast')
        self.assertFalse(result['ok'])
        self.assertTrue(result['motion_observed'])
        self.assertEqual(result['status'], 'travel_envelope_exceeded')
        self.assertGreater(result['coast_travel_deg'], 8)
        self.assertTrue(result['baseline_restored'])

    def test_extension_without_prior_evidence_is_refused(self):
        c = FakePilotClient([0.0])
        with self.assertRaises(ValueError):
            run_pilot(c, c.original, {}, self.root/'no-prior', stage='extension_3a')
        self.assertEqual(c.commands, [])

    def test_rotation_supervisor_completes_turn_across_angle_wrap(self):
        result, c = self.execute('rotation', stage='rotation_3a')
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['status'], 'bounded_rotation_observed')
        self.assertGreaterEqual(result['travel_deg'], 360)
        self.assertGreater(result['powered_s'], 3.5)
        self.assertLess(result['powered_s'], 4)
        self.assertLessEqual(max(c.commands), 3)
        rows = [json.loads(line) for line in (self.root/'run'/'observations.jsonl').read_text().splitlines()]
        self.assertTrue(any(b['command_a'] < a['command_a'] for a, b in zip(rows, rows[1:])))
        self.assertGreater(result['coast_travel_deg'], 5)
        self.assertEqual(c.motor, c.original)
        self.assertEqual(c.commands[-1], 0)

    def test_rotation_small_motion_does_not_qualify_full_turn(self):
        result, c = self.execute(stage='rotation_3a')
        self.assertTrue(result['encoder_displacement_detected'])
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'rotation_criterion_not_met')
        self.assertEqual(c.commands[-1], 0)

    def test_rotation_overspeed_stops_and_is_not_success(self):
        result, c = self.execute('overspeed', stage='rotation_3a')
        self.assertFalse(result['ok'])
        self.assertTrue(result['errors'])
        self.assertEqual(c.commands[-1], 0)
        self.assertTrue(result['zero_current_verified'])

    def test_rotation_disconnect_and_stall_do_not_qualify(self):
        for failure in ('disconnect', 'stall'):
            with self.subTest(failure=failure):
                old_root = self.root
                self.root = old_root/failure
                self.root.mkdir()
                result, c = self.execute(failure, stage='rotation_3a')
                self.root = old_root
                self.assertFalse(result['ok'])
                self.assertTrue(result['baseline_restored'])
                self.assertEqual(c.commands[-1], 0)

    def test_rotation_reference_only_accepts_reviewed_recovered_travel_stop(self):
        c = FakePilotClient([0.0])
        plan, candidate = build_pilot(c.original, 1.02, 207.2, 'extension_3a')
        prior = dict(status='travel_envelope_exceeded', plan=plan,
                     errors=['Stale encoder, unexpected direction, travel or speed limit'],
                     excitation_sent=True, zero_current_verified=True,
                     baseline_restored=True, no_faults=True, app_isolated=True)
        quiet = [dict(t=i*.03, position_deg=117, current_motor_a=0, id_a=0, iq_a=0,
                      duty=0, fault_code=0) for i in range(12)]
        final = dict(read_only=True, zero_current_verified=True, app_isolated=True,
                     baseline_restored=True, baseline_sha256=plan['baseline_sha256'], samples=quiet)
        rows = [dict(command_a=3, elapsed_s=1+i*.03, id_a=-3/math.sqrt(2), iq_a=3/math.sqrt(2),
                     current_motor_a=3, current_in_a=.04, v_in=25, duty=.02, encoder_rpm=34,
                     encoder_age_s=0, latency_s=.002, travel_deg=10+i*9, temp_mos_c=26,
                     fault_code=0, i2t_a2s=8, input_energy_j=1) for i in range(10)]
        folder = self.root/'prior'
        folder.mkdir()
        (folder/'mcconf-before.bin').write_bytes(c.original)
        (folder/'mcconf-candidate.bin').write_bytes(candidate)
        (folder/'result.json').write_text(json.dumps(prior))
        (folder/'final-readback.json').write_text(json.dumps(final))
        (folder/'observations.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
        self.assertEqual(rotation_reference(folder, c.original)['starting_pose_deg'], 117)
        for change in (dict(status='aborted'), dict(no_faults=False), dict(baseline_restored=False),
                       dict(errors=['different fault']), dict(plan=dict(plan, stage='rotation_3a'))):
            (folder/'result.json').write_text(json.dumps(dict(prior, **change)))
            with self.assertRaises(ValueError):
                rotation_reference(folder, c.original)
        (folder/'result.json').write_text(json.dumps(prior))
        rows[-1]['encoder_rpm'] = 61
        (folder/'observations.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
        with self.assertRaises(ValueError):
            rotation_reference(folder, c.original)

    def test_power_cycle_restores_fresh_calibration_not_old_bytes(self):
        result, c = self.execute('power_cycle')
        self.assertTrue(result['ok'], result)
        self.assertIn('foc_offsets_current[0]', result['fresh_adc_changes'])
        self.assertEqual(c.motor, c.entry)
        self.assertNotEqual(c.motor, c.original)

    def test_reverse_current_mismatch_disconnect_and_config_failure_stop(self):
        for failure in ('reverse', 'no_id', 'disconnect', 'mismatch'):
            with self.subTest(failure=failure):
                old_root = self.root
                self.root = old_root/failure
                self.root.mkdir()
                result, c = self.execute(failure)
                self.root = old_root
                self.assertFalse(result['ok'])
                self.assertTrue(result['errors'])
                self.assertTrue(result['baseline_restored'])
                self.assertEqual(c.commands[-1], 0)
                if failure in ('reverse', 'no_id'):
                    self.assertIn('last_powered_observation', result)
                    self.assertEqual(result['travel_deg'], result['last_powered_observation']['travel_deg'])
                if failure == 'mismatch':
                    self.assertFalse(result['excitation_sent'])

    def test_no_rollback_without_fresh_quiet_data(self):
        result, c = self.execute('permanent_disconnect')
        self.assertEqual(result['status'], 'recovery_required')
        self.assertFalse(result['baseline_restored'])
        self.assertEqual(c.writes, 1)
        self.assertEqual(c.commands[-1], 0)

    def test_stop_file_prevents_excitation(self):
        result, c = self.execute('stop_file')
        self.assertFalse(result['excitation_sent'])
        self.assertEqual(c.writes, 0)
        self.assertTrue(result['zero_current_verified'])

    def test_locked_fixture_rejected_before_client_access(self):
        self.fixture.write_text(json.dumps(dict(schema='vesc-fixture-v1', rotor='locked', confirmed_by_user=True)))
        with self.assertRaises(FixtureInterlock):
            run_pilot(None, b'', {}, self.root/'forbidden')
        self.assertFalse((self.root/'forbidden').exists())

    def test_cli_locked_fixture_never_opens_serial(self):
        self.fixture.write_text(json.dumps(dict(schema='vesc-fixture-v1', rotor='locked', confirmed_by_user=True)))
        script = Path(__file__).resolve().parents[1]/'scripts'/'run-synrm-pilot.py'
        argv = [str(script), '--armed-free-rotor', '--baseline', 'absent.bin',
                '--hfi-summary', 'absent.json', '--output', str(self.root/'cli')]
        with patch('sys.argv', argv), patch('vesc_workbench.locked_probe.ProbeClient') as factory:
            with self.assertRaises(FixtureInterlock):
                runpy.run_path(str(script), run_name='__main__')
            factory.assert_not_called()

    def test_encoder_diagnostic_failure_is_not_ignored(self):
        for line in ('SPI encoder value: 42, errors: 0, error rate: 0.000 %',
                     'SPI encoder value: 42, errors: 1, error rate: 1.000 %', 'No encoder debug info available.'):
            replies = iter([b'\x15'+line.encode(), b'\x15 '])
            c = SimpleNamespace(send_payload=lambda p: None, read_response=lambda n: next(replies))
            if '0.000' in line:
                self.assertIn('SPI', check_encoder(c))
            else:
                with self.assertRaises(ValueError):
                    check_encoder(c)
