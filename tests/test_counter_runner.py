from dataclasses import replace
from contextlib import nullcontext
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_synrm_pilot_runner import FakePilotClient
from vesc_workbench.synrm_pilot_runner import run_pilot, audit_speed_run
from vesc_workbench.synrm_repeatability import read_quiet_baseline
from vesc_workbench.synrm_pilot import stage_limits, build_pilot, timing_stage
from vesc_workbench.wire_config import patch_config
from vesc_workbench.native_counter_snapshot import f32


class CounterClient(FakePilotClient):
    def __init__(self, clock, fault=''):
        super().__init__(clock, 'higher_quadratic_rotation')
        self.angle = self.pid_position
        self.inject = fault

    def get_values(self):
        previous = self.pid_position
        result = super().get_values()
        self.angle += (self.pid_position-previous+180) % 360-180
        count = math.floor(self.angle/30)
        if self.current == 0 and 100 < self.rpm < 300 and self.inject in ('coast_latency', 'coast_latency_twice'):
            self.clock[0] += .006
            self.inject = 'coast_latency' if self.inject == 'coast_latency_twice' else ''
        if self.current > 2 and self.inject in ('counter', 'gap', 'reverse'):
            fault, self.inject = self.inject, ''
            if fault == 'counter':
                count += 120
            elif fault == 'gap':
                self.clock[0] += .03
            elif fault == 'reverse':
                self.pid_position = (self.pid_position-50) % 360
                self.angle -= 50
                count = math.floor(self.angle/30)
        if getattr(self, 'emit_native', False):
            tick = round(self.clock[0]*10000)
            scale = f32(.006208386)
            self.native_counter_record = dict(native_start_tick=tick-1, native_end_tick=tick,
                native_elapsed_ticks=tick, native_tick_hz_lower=10000, native_tick_hz_upper=10000,
                native_distance_scale=scale, native_distance=f32(count*scale),
                native_distance_abs=f32(abs(count)*scale))
        return replace(result, tachometer=count, tachometer_abs=abs(count))


class CounterRunnerTests(unittest.TestCase):
    def execute(self, fault='', stage='speed_2200rpm_5a_counter', slow_prior=False, read_latency_s=.002,
                synchronous_logs=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        fixture = root/'fixture.json'
        fixture.write_text(json.dumps(dict(schema='vesc-fixture-v1', rotor='free', confirmed_by_user=True)))
        clock = [0.0]
        client = CounterClient(clock, fault)
        client.read_latency_s = read_latency_s
        if stage_limits(stage).get('native_counter'):
            client.emit_native = True
            client.native_clock_reference = dict(path='mock-clock', verified=True, tick_hz_lower=10000,
                                                tick_hz_upper=10000, distance_scale=f32(.006208386))
        if stage_limits(stage).get('return_current_a'):
            client.motor = patch_config(client.motor, 'motor', dict(l_max_vin=60))
            client.original = client.entry = client.motor
        now = lambda: clock[0]
        def pause(seconds):
            if (client.inject == 'coast_gap' and client.current == 0
                    and 100 < client.rpm < 300 and any(i > 0 for i in client.commands)):
                client.inject = ''
                client.coast_command_index = len(client.commands)
                seconds += .05
            clock[0] += seconds
        baseline = client.original
        digest = hashlib.sha256(baseline).hexdigest()
        evidence = dict(measurement_agreement_verified=True, baseline_sha256=digest)
        pose = dict(encoder_deg=207.2, offset_deg=1.02, baseline_sha256=digest)
        def prior(*args):
            if slow_prior:
                clock[0] += 2
            return dict(starting_pose_deg=207.2)
        # Fast virtual-time plants can outrun a real disk worker by orders of magnitude.
        log_context = (patch('vesc_workbench.synrm_pilot_runner.open_trial_log',
                             side_effect=lambda path, queued, **kwargs: path.open('x', encoding='utf-8'))
                       if synchronous_logs else nullcontext())
        with patch('vesc_workbench.fixture.FIXTURE_PATH', fixture), \
             patch('vesc_workbench.synrm_pilot_runner.check_encoder', return_value='SPI error rate: 0.000 %'), \
             patch('vesc_workbench.synrm_pilot_runner.higher_speed_reference', side_effect=prior), log_context:
            def entry():
                return read_quiet_baseline(client, baseline, clock=now, pause=pause)
            report = run_pilot(client, baseline, pose, root/'run', stage=stage,
                               prior_run='mock-prior', clock=now, pause=pause,
                               entry_reader=entry, counter_evidence=evidence)
            self.assertTrue(report['baseline_restored'], report['errors'])
            final = read_quiet_baseline(client, baseline, clock=now, pause=pause)
        (root/'run'/'final-readback.json').write_text(json.dumps(final))
        return root/'run', report, client

    def test_six_amp_step_retains_speed_trip_and_duration_caps(self):
        five = stage_limits('speed_2700rpm_5a_counter')
        six = stage_limits('speed_2700rpm_6a_counter')
        for key in ('trip', 'input_current', 'maximum_rpm', 'powered_s', 'telemetry_gap_s'):
            self.assertEqual(five[key], six[key])
        self.assertEqual(six['current'], 6)
        self.assertEqual(six['trip'], 8)
        self.assertEqual(six['i2t'], 1440)
        self.assertEqual(six['energy'], 144)
        self.assertEqual(timing_stage('speed_2700rpm_6a_counter'), 'speed_2700rpm_5a_counter')
        _, report, client = self.execute(stage='speed_2700rpm_6a_counter')
        self.assertLessEqual(max(client.commands), 6)
        self.assertTrue(report['zero_current_verified'], report)
        self.assertTrue(report['baseline_restored'], report)
        self.assertFalse(report['errors'], report)
        _, candidate = build_pilot(client.original, 1.02, 207.2, 'speed_2700rpm_6a_counter')
        self.assertEqual(report['plan']['candidate_sha256'], hashlib.sha256(candidate).hexdigest())

    def test_complete_counter_run_and_offline_replay(self):
        folder, report, client = self.execute()
        self.assertTrue(report['ok'], report)
        self.assertEqual(client.motor, client.original)
        self.assertEqual(client.commands[-1], 0)
        self.assertLessEqual(max(client.commands), 5)
        audit_speed_run(folder, client.original, 'speed_2200rpm_5a_counter')
        lines = (folder/'observations.jsonl').read_text().splitlines()
        row = json.loads(lines[-1])
        row['encoder_rpm'] += 1
        lines[-1] = json.dumps(row)
        (folder/'observations.jsonl').write_text('\n'.join(lines)+'\n')
        with self.assertRaisesRegex(ValueError, 'observation mismatch'):
            audit_speed_run(folder, client.original, 'speed_2200rpm_5a_counter')

    def test_counter_corruption_gap_and_reverse_stop_and_recover(self):
        for fault in ('counter', 'gap', 'reverse'):
            with self.subTest(fault=fault):
                _, report, client = self.execute(fault)
                self.assertFalse(report['ok'])
                self.assertTrue(report['telemetry_guard_exceeded'])
                self.assertTrue(report['zero_current_verified'], report)
                self.assertTrue(report['baseline_restored'], report)
                self.assertEqual(client.commands[-1], 0)

    def test_small_battery_return_probe_runs_and_replays_without_speed_escalation(self):
        original = CounterClient.get_values
        def battery_values(client):
            return replace(original(client), v_in=24.5)
        with patch.object(CounterClient, 'get_values', battery_values):
            folder, report, client = self.execute(stage='speed_90rpm_2a_return_probe')
        self.assertTrue(report['ok'], report)
        self.assertLessEqual(max(client.commands), 2)
        self.assertEqual(report['returned_energy_j'], 0)
        self.assertTrue(report['zero_current_verified'])
        self.assertEqual(client.motor, client.original)
        audit_speed_run(folder, client.original, 'speed_90rpm_2a_return_probe')

    def test_high_speed_return_stage_combines_both_measurement_guards(self):
        original = CounterClient.get_values
        def battery_values(client):
            return replace(original(client), v_in=24.5)
        with patch.object(CounterClient, 'get_values', battery_values):
            folder, report, client = self.execute(stage='speed_2700rpm_6a_counter_return')
        self.assertEqual(report['measurement_method'], 'sector_assisted_encoder_request_brackets_v1')
        self.assertEqual(report['returned_energy_j'], 0)
        self.assertFalse(report['errors'], report)
        self.assertTrue(report['zero_current_verified'], report)
        self.assertTrue(report['baseline_restored'], report)
        self.assertLessEqual(max(client.commands), 6)

    def test_separate_coast_window_and_powered_abort(self):
        stage = 'speed_2700rpm_6a_counter_return_coast'
        limits = stage_limits(stage)
        original_limits = stage_limits('speed_2700rpm_6a_counter_return')
        self.assertEqual({k: v for k, v in limits.items() if k in original_limits}, original_limits)
        self.assertEqual(timing_stage(stage), stage)
        self.assertEqual(timing_stage(stage, coast=True), stage)
        original = CounterClient.get_values
        def battery_values(client):
            return replace(original(client), v_in=24.5)
        with patch.object(CounterClient, 'get_values', battery_values):
            folder, report, client = self.execute('coast_gap', stage)
            _, failed, failed_client = self.execute('gap', stage)
        self.assertFalse(report.get('telemetry_guard_exceeded'), report)
        self.assertFalse(report.get('coast_guard_exceeded'), report)
        self.assertTrue(report['zero_current_verified'], report)
        self.assertTrue(report['baseline_restored'], report)
        self.assertTrue(all(i == 0 for i in client.commands[client.coast_command_index:]))
        from vesc_workbench.counter_angle import replay_counter_run
        samples = [json.loads(line) for line in (folder/'samples.jsonl').read_text().splitlines()]
        observations = [json.loads(line) for line in (folder/'observations.jsonl').read_text().splitlines()]
        replay_counter_run(samples, observations, 2970, coast_gap_s=.1, coast_window_s=.5)
        with self.assertRaises(ValueError):
            replay_counter_run(samples, observations, 2970)
        self.assertFalse(failed['ok'])
        self.assertTrue(failed['telemetry_guard_exceeded'])
        self.assertEqual(failed['counter_errors'][0]['stage'], 'powered')
        self.assertTrue(failed['zero_current_verified'])
        self.assertEqual(failed_client.commands[-1], 0)

    def test_log_failure_stops_torque_without_blocking_quiet_recovery(self):
        class BrokenLog:
            def __init__(self, path):
                self.stream = path.open('x', encoding='utf-8')
            def write(self, text):
                if '"stage": "powered"' in text:
                    raise OSError('injected disk error')
                return self.stream.write(text)
            def flush(self):
                self.stream.flush()
            def close(self):
                self.stream.close()
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                self.close()
        original = CounterClient.get_values
        def battery_values(client):
            return replace(original(client), v_in=24.5)
        with patch.object(CounterClient, 'get_values', battery_values), \
             patch('vesc_workbench.synrm_pilot_runner.open_trial_log', side_effect=lambda path, queued, **kwargs: BrokenLog(path)):
            _, report, client = self.execute(stage='speed_2700rpm_6a_counter_return_coast')
        self.assertFalse(report['ok'])
        self.assertTrue(report['logging_failed'])
        self.assertTrue(report['zero_current_verified'], report)
        self.assertTrue(report['baseline_restored'], report)
        self.assertFalse(report['logs_drained'])
        self.assertEqual(client.commands[-1], 0)

    def test_next_500rpm_step_requires_qualified_2350_point_and_caps_current(self):
        stage = 'speed_3200rpm_7a_counter_return_coast'
        limits = stage_limits(stage)
        prior = stage_limits('speed_2700rpm_6a_counter_return_coast')
        self.assertEqual(limits['taper_start_rpm']-prior['taper_start_rpm'], 500)
        self.assertEqual(limits['cutoff_rpm']-prior['cutoff_rpm'], 500)
        for key in ('powered_s', 'telemetry_gap_s', 'coast_telemetry_gap_s', 'return_current_a', 'input_current'):
            self.assertEqual(limits[key], prior[key])
        original = CounterClient.get_values
        def battery_values(client):
            return replace(original(client), v_in=24.5)
        with patch.object(CounterClient, 'get_values', battery_values):
            folder, report, client = self.execute(stage=stage, slow_prior=True)
        self.assertFalse(report['errors'], report)
        self.assertTrue(report['zero_current_verified'], report)
        self.assertTrue(report['baseline_restored'], report)
        self.assertLessEqual(max(client.commands), 7)
        self.assertEqual(report['plan']['changes']['l_abs_current_max'], 10)
        from vesc_workbench.synrm_pilot_runner import higher_speed_reference
        with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
            higher_speed_reference(folder, client.original, stage)
        self.assertEqual(audit.call_args.args[2], 'speed_2700rpm_6a_counter_return_coast')

    def check_seven_amp_speed_step(self, stage, predecessor):
        prior = stage_limits(predecessor)
        limits = stage_limits(stage)
        changed = {k for k in limits if limits[k] != prior[k]}
        self.assertEqual(changed, {'taper_start_rpm', 'cutoff_rpm', 'maximum_rpm', 'minimum_finish_rpm', 'travel', 'full_travel'})
        from vesc_workbench.synrm_pilot_runner import higher_speed_reference
        with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
            higher_speed_reference('prior', b'baseline', stage)
        self.assertEqual(audit.call_args.args[2], predecessor)
        original = CounterClient.get_values
        def battery_values(client):
            return replace(original(client), v_in=24.5)
        with patch.object(CounterClient, 'get_values', battery_values):
            _, report, client = self.execute(stage=stage, slow_prior=True)
        self.assertFalse(report['errors'], report)
        self.assertTrue(report['zero_current_verified'], report)
        self.assertTrue(report['baseline_restored'], report)
        self.assertLessEqual(max(client.commands), 7)

    def test_3700_step_retains_seven_amp_electrical_envelope(self):
        self.check_seven_amp_speed_step('speed_3700rpm_7a_counter_return_coast', 'speed_3200rpm_7a_counter_return_coast')

    def test_4200_step_retains_seven_amp_electrical_envelope(self):
        self.check_seven_amp_speed_step('speed_4200rpm_7a_counter_return_coast', 'speed_3700rpm_7a_counter_return_coast')

    def test_4700_step_retains_seven_amp_electrical_envelope(self):
        self.check_seven_amp_speed_step('speed_4700rpm_7a_counter_return_coast', 'speed_4200rpm_7a_counter_return_coast')

    def test_5200_step_retains_seven_amp_electrical_envelope(self):
        self.check_seven_amp_speed_step('speed_5200rpm_7a_coast_reacquire', 'speed_4700rpm_7a_coast_reacquire')

    def test_5200_hold_changes_duration_but_not_motor_configuration(self):
        stage = 'speed_5200rpm_7a_hold60'
        limits = stage_limits(stage)
        prior = stage_limits('speed_5200rpm_7a_coast_reacquire')
        self.assertEqual({k for k in limits if limits[k] != prior[k]},
                         {'powered_s', 'minimum_observation_s', 'i2t', 'energy', 'travel', 'full_travel'})
        self.assertEqual(limits['powered_s'], 60)
        self.assertEqual(timing_stage(stage), 'speed_5200rpm_7a_coast_reacquire')
        original = CounterClient.get_values
        def battery_values(client):
            return replace(original(client), v_in=24.5)
        with patch.object(CounterClient, 'get_values', battery_values):
            _, report, client = self.execute(stage=stage, slow_prior=True)
        _, candidate = build_pilot(client.original, 1.02, 207.2, 'speed_5200rpm_7a_coast_reacquire')
        self.assertEqual(report['plan']['candidate_sha256'], hashlib.sha256(candidate).hexdigest())
        self.assertFalse(report['errors'], report)
        self.assertTrue(report['zero_current_verified'])
        self.assertTrue(report['baseline_restored'])
        self.assertLessEqual(max(client.commands), 7)

    def test_5700_eight_amp_step_has_bounded_one_minute_budget(self):
        stage = 'speed_5700rpm_8a_hold60'
        limits = stage_limits(stage)
        self.assertEqual(limits['current'], 8)
        self.assertEqual(limits['trip'], 11)
        self.assertEqual(limits['i2t'], 8**2*60)
        self.assertEqual(limits['powered_s'], 60)
        self.assertEqual(limits['input_current'], 2)
        from vesc_workbench.synrm_pilot_runner import higher_speed_reference
        with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
            higher_speed_reference('prior', b'baseline', stage)
        self.assertEqual(audit.call_args.args[2], 'speed_5200rpm_7a_hold60')
        original = CounterClient.get_values
        def battery_values(client):
            return replace(original(client), v_in=24.5)
        with patch.object(CounterClient, 'get_values', battery_values):
            _, report, client = self.execute(stage=stage, slow_prior=True, read_latency_s=.0005, synchronous_logs=True)
        self.assertFalse(report['errors'], report)
        self.assertTrue(report['zero_current_verified'])
        self.assertTrue(report['baseline_restored'])
        self.assertLessEqual(max(client.commands), 8)
        self.assertEqual(report['plan']['changes']['l_abs_current_max'], 11)

    def test_6200_step_preserves_eight_amp_electrical_limits(self):
        self.check_eight_amp_speed_step('speed_6200rpm_8a_hold60', 'speed_5700rpm_8a_hold60')

    def test_6700_step_preserves_eight_amp_electrical_limits(self):
        self.check_eight_amp_speed_step('speed_6700rpm_8a_hold60', 'speed_6200rpm_8a_hold60')

    def test_native_6200_repeats_same_motor_candidate_and_replays_native_clock(self):
        stage = 'speed_6200rpm_8a_native60'
        original = CounterClient.get_values
        def battery_values(client):
            return replace(original(client), v_in=24.5)
        with patch.object(CounterClient, 'get_values', battery_values):
            folder, report, client = self.execute(stage=stage)
        self.assertTrue(report['ok'], report)
        self.assertEqual(report['measurement_method'], 'sector_assisted_encoder_native_clock_v1')
        _, expected = build_pilot(client.original, 1.02, 207.2, 'speed_6200rpm_8a_hold60')
        self.assertEqual(report['plan']['candidate_sha256'], hashlib.sha256(expected).hexdigest())
        self.assertFalse(stage_limits(stage)['defer_coast_capture'])
        from vesc_workbench.native_counter_snapshot import SNAPSHOT_METHOD
        (folder/'native-runtime.json').write_text(json.dumps(dict(method=SNAPSHOT_METHOD,
            installed=True, removed=True, flash_writes=False)))
        with patch('vesc_workbench.synrm_pilot_runner.load_clock_reference', return_value=client.native_clock_reference):
            audit_speed_run(folder, client.original, stage)

    def test_native_7200_only_changes_speed_envelope_and_requires_6700(self):
        stage = 'speed_7200rpm_8a_native60'
        limits, prior = stage_limits(stage), stage_limits('speed_6700rpm_8a_native60')
        self.assertEqual({k for k in limits if limits[k] != prior.get(k)},
                         {'taper_start_rpm', 'cutoff_rpm', 'maximum_rpm',
                          'minimum_finish_rpm', 'travel', 'full_travel'})
        self.assertEqual(limits['taper_start_rpm']-prior['taper_start_rpm'], 500)
        from vesc_workbench.synrm_pilot_runner import higher_speed_reference
        from vesc_workbench.native_counter_snapshot import SNAPSHOT_METHOD
        with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
            higher_speed_reference('prior', b'baseline', stage)
        self.assertEqual(audit.call_args.args[2], 'speed_6700rpm_8a_native60')
        original = CounterClient.get_values
        with patch.object(CounterClient, 'get_values', lambda c: replace(original(c), v_in=24.5)):
            folder, report, client = self.execute(stage=stage)
        # This deliberately limited fake plant tops out below the requested step.
        self.assertFalse(report['ok'], report)
        self.assertEqual(report['status'], 'rotation_criterion_not_met')
        self.assertTrue(report['zero_current_verified'])
        self.assertTrue(report['baseline_restored'])
        self.assertLessEqual(max(client.commands), 8)
        self.assertEqual(client.commands[-1], 0)
        (folder/'native-runtime.json').write_text(json.dumps(dict(method=SNAPSHOT_METHOD,
            installed=True, removed=True, flash_writes=False)))
        with patch('vesc_workbench.synrm_pilot_runner.load_clock_reference', return_value=client.native_clock_reference):
            with self.assertRaises(ValueError):
                audit_speed_run(folder, client.original, stage)

    def test_native_7200_nine_amps_repeats_speed_target_with_bounded_current(self):
        stage = 'speed_7200rpm_9a_native60'
        limits, prior = stage_limits(stage), stage_limits('speed_7200rpm_8a_native60')
        self.assertEqual({k for k in limits if limits[k] != prior.get(k)},
                         {'current', 'observed_current', 'trip', 'i2t', 'energy'})
        self.assertEqual(limits['trip'], 12)
        self.assertEqual(limits['powered_s'], 60)
        self.assertEqual(limits['input_current'], 2)
        from vesc_workbench.synrm_pilot_runner import higher_speed_reference
        from vesc_workbench.native_counter_snapshot import SNAPSHOT_METHOD
        with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
            higher_speed_reference('prior', b'baseline', stage)
        self.assertEqual(audit.call_args.args[2], 'speed_6700rpm_8a_native60')
        original = CounterClient.get_values
        with patch.object(CounterClient, 'get_values', lambda c: replace(original(c), v_in=24.5)):
            folder, report, client = self.execute(stage=stage)
        self.assertTrue(report['ok'], report)
        self.assertLessEqual(max(client.commands), 9)
        self.assertEqual(client.commands[-1], 0)
        (folder/'native-runtime.json').write_text(json.dumps(dict(method=SNAPSHOT_METHOD,
            installed=True, removed=True, flash_writes=False)))
        with patch('vesc_workbench.synrm_pilot_runner.load_clock_reference', return_value=client.native_clock_reference):
            audit_speed_run(folder, client.original, stage)

    def test_native_7700_keeps_nine_amp_limits_and_replays(self):
        stage = 'speed_7700rpm_9a_native60'
        limits, prior = stage_limits(stage), stage_limits('speed_7200rpm_9a_native60')
        self.assertEqual({k for k in limits if limits[k] != prior.get(k)},
                         {'taper_start_rpm', 'cutoff_rpm', 'maximum_rpm',
                          'minimum_finish_rpm', 'travel', 'full_travel'})
        self.assertEqual(limits['taper_start_rpm']-prior['taper_start_rpm'], 500)
        from vesc_workbench.synrm_pilot_runner import higher_speed_reference
        from vesc_workbench.native_counter_snapshot import SNAPSHOT_METHOD
        with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
            higher_speed_reference('prior', b'baseline', stage)
        self.assertEqual(audit.call_args.args[2], 'speed_7200rpm_9a_native60')
        original = CounterClient.get_values
        with patch.object(CounterClient, 'get_values', lambda c: replace(original(c), v_in=24.5)):
            folder, report, client = self.execute(stage=stage)
        self.assertTrue(report['ok'], report)
        self.assertLessEqual(max(client.commands), 9)
        self.assertEqual(client.commands[-1], 0)
        (folder/'native-runtime.json').write_text(json.dumps(dict(method=SNAPSHOT_METHOD,
            installed=True, removed=True, flash_writes=False)))
        with patch('vesc_workbench.synrm_pilot_runner.load_clock_reference', return_value=client.native_clock_reference):
            audit_speed_run(folder, client.original, stage)

    def test_native_8200_retains_electrical_and_time_limits(self):
        stage = 'speed_8200rpm_9a_native60'
        limits, prior = stage_limits(stage), stage_limits('speed_7700rpm_9a_native60')
        self.assertEqual({k for k in limits if limits[k] != prior.get(k)},
                         {'taper_start_rpm', 'cutoff_rpm', 'maximum_rpm',
                          'minimum_finish_rpm', 'travel', 'full_travel'})
        self.assertEqual(limits['taper_start_rpm'], 7800)
        self.assertEqual(limits['maximum_rpm'], 9020)
        from vesc_workbench.synrm_pilot_runner import higher_speed_reference
        with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
            higher_speed_reference('prior', b'baseline', stage)
        self.assertEqual(audit.call_args.args[2], 'speed_7700rpm_9a_native60')
        self.assertEqual(timing_stage(stage), 'speed_7700rpm_9a_native60')

    def test_native_ten_amp_steps_keep_bounds_and_require_qualified_predecessors(self):
        from vesc_workbench.synrm_pilot_runner import higher_speed_reference
        from vesc_workbench.native_counter_snapshot import SNAPSHOT_METHOD
        steps = [('speed_8200rpm_10a_native60', 'speed_7700rpm_9a_native60', 7800),
                 ('speed_8700rpm_10a_native60', 'speed_8200rpm_10a_native60', 8300),
                 ('speed_9200rpm_10a_native60', 'speed_8700rpm_10a_native60', 8800)]
        for stage, predecessor, taper in steps:
            limits = stage_limits(stage)
            self.assertEqual((limits['current'], limits['trip'], limits['input_current'], limits['powered_s']),
                             (10, 13, 2, 60))
            self.assertEqual((limits['i2t'], limits['energy']), (6000, 600))
            self.assertEqual(limits['taper_start_rpm'], taper)
            self.assertEqual(limits['cutoff_rpm'], taper+400)
            self.assertEqual(limits['maximum_rpm'], (taper+400)*11//10)
            with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
                higher_speed_reference('prior', b'baseline', stage)
            self.assertEqual(audit.call_args.args[2], predecessor)
        base, raised = stage_limits('speed_8200rpm_9a_native60'), stage_limits(steps[0][0])
        self.assertEqual({k for k in raised if raised[k] != base.get(k)},
                         {'current', 'observed_current', 'trip', 'i2t', 'energy'})
        original = CounterClient.get_values
        with patch.object(CounterClient, 'get_values', lambda c: replace(original(c), v_in=24.5)):
            folder, report, client = self.execute(stage=steps[-1][0])
        self.assertTrue(report['ok'], report)
        self.assertLessEqual(max(client.commands), 10)
        self.assertEqual(client.commands[-1], 0)
        (folder/'native-runtime.json').write_text(json.dumps(dict(method=SNAPSHOT_METHOD,
            installed=True, removed=True, flash_writes=False)))
        with patch('vesc_workbench.synrm_pilot_runner.load_clock_reference', return_value=client.native_clock_reference):
            audit_speed_run(folder, client.original, steps[-1][0])

    def test_rpm95_diagnostic_only_moves_soft_knee_not_hard_limits(self):
        from vesc_workbench.wire_config import decode_config
        from vesc_workbench.synrm_pilot_runner import higher_speed_reference
        stage = 'speed_8700rpm_10a_rpm95'
        old, new = stage_limits('speed_8700rpm_10a_native60'), stage_limits(stage)
        self.assertEqual({k for k in new if new[k] != old.get(k)}, {'erpm_start'})
        client = CounterClient([0.0])
        baseline = patch_config(client.original, 'motor', dict(l_max_vin=60))
        _, a = build_pilot(baseline, 1.02, 207.2, 'speed_8700rpm_10a_native60')
        _, b = build_pilot(baseline, 1.02, 207.2, stage)
        a, b = decode_config(a, 'motor'), decode_config(b, 'motor')
        self.assertEqual({k for k in b if b[k] != a[k]}, {'l_erpm_start'})
        self.assertAlmostEqual(b['l_erpm_start'], .95)
        self.assertGreater(new['maximum_rpm']*b['l_erpm_start'], new['cutoff_rpm'])
        self.assertLess(new['maximum_rpm']*b['l_erpm_start'], new['maximum_rpm'])
        with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
            higher_speed_reference('prior', b'baseline', stage)
        self.assertEqual(audit.call_args.args[2], 'speed_8200rpm_10a_native60')

    def check_eight_amp_speed_step(self, stage, previous_stage):
        limits, prior = stage_limits(stage), stage_limits(previous_stage)
        expected = {'taper_start_rpm', 'cutoff_rpm', 'maximum_rpm', 'minimum_finish_rpm', 'travel', 'full_travel'}
        if stage == 'speed_6700rpm_8a_hold60':
            expected.update(('queued_logging', 'memory_logging'))
        self.assertEqual({k for k in limits if limits[k] != prior.get(k)}, expected)
        from vesc_workbench.synrm_pilot_runner import higher_speed_reference
        with patch('vesc_workbench.synrm_pilot_runner.audit_speed_run') as audit:
            higher_speed_reference('prior', b'baseline', stage)
        self.assertEqual(audit.call_args.args[2], previous_stage)
        original = CounterClient.get_values
        def battery_values(client):
            return replace(original(client), v_in=24.5)
        with patch.object(CounterClient, 'get_values', battery_values):
            folder, report, client = self.execute(stage=stage, read_latency_s=.0005,
                                                  synchronous_logs=not limits.get('memory_logging'))
        self.assertFalse(report['errors'], report)
        self.assertTrue(report['zero_current_verified'])
        self.assertTrue(report['baseline_restored'])
        self.assertLessEqual(max(client.commands), 8)
        if limits.get('memory_logging'):
            self.assertTrue(report['memory_logging'])
            self.assertTrue(report['logs_drained'])
            report['logs_drained'] = False
            (folder/'result.json').write_text(json.dumps(report))
            from vesc_workbench.synrm_pilot_runner import audit_speed_run
            with self.assertRaisesRegex(ValueError, 'memory log drainage'):
                audit_speed_run(folder, client.original, stage)

    def test_coast_reacquire_preserves_full_replay_but_rejects_second_delay(self):
        stage = 'speed_4700rpm_7a_coast_reacquire'
        previous = stage_limits('speed_4700rpm_7a_counter_return_coast')
        self.assertEqual({k:v for k,v in stage_limits(stage).items() if k in previous}, previous)
        self.assertEqual(timing_stage(stage), 'speed_4700rpm_7a_counter_return_coast')
        self.assertEqual(timing_stage(stage, coast=True), 'speed_4700rpm_7a_counter_return_coast')
        original = CounterClient.get_values
        def battery_values(client):
            return replace(original(client), v_in=24.5)
        with patch.object(CounterClient, 'get_values', battery_values):
            folder, report, client = self.execute('coast_latency', stage)
            _, failed, _ = self.execute('coast_latency_twice', stage)
        self.assertFalse(report['errors'], report)
        self.assertFalse(report.get('telemetry_guard_exceeded'), report)
        self.assertEqual(len(report['deferred_coast_captures']), 1)
        self.assertTrue(report['zero_current_verified'])
        self.assertTrue(report['baseline_restored'])
        self.assertFalse(failed['ok'])
        self.assertTrue(failed['telemetry_guard_exceeded'])
        self.assertTrue(failed['zero_current_verified'])
        self.assertTrue(failed['baseline_restored'])
        from vesc_workbench.counter_angle import replay_counter_run
        samples = [json.loads(line) for line in (folder/'samples.jsonl').read_text().splitlines()]
        observations = [json.loads(line) for line in (folder/'observations.jsonl').read_text().splitlines()]
        replay_counter_run(samples, observations, 5170, coast_gap_s=.1, coast_window_s=.5, allow_coast_deferred=True)
        with self.assertRaises(ValueError):
            replay_counter_run(samples, observations, 5170, coast_gap_s=.1, coast_window_s=.5)
        deferred_index = next(i for i,r in enumerate(samples) if r.get('counter_capture_deferred'))
        with self.assertRaisesRegex(ValueError, 'never resolved'):
            replay_counter_run(samples[:deferred_index+1], observations, 5170,
                               coast_gap_s=.1, coast_window_s=.5, allow_coast_deferred=True)
