import hashlib
import json
from pathlib import Path
import tempfile
from unittest import TestCase

from vesc_workbench.synrm_pilot_runner import timing_reference
from vesc_workbench.counter_angle import CounterAngle
from vesc_workbench.telemetry_capture import CAPTURE_TIMING
from vesc_workbench.native_counter_tracker import NativeCounterAngle
from vesc_workbench.native_counter_snapshot import f32, SNAPSHOT_METHOD


class TimingGateTests(TestCase):
    def test_native_gate_binds_raw_clock_to_verified_reference(self):
        runtime = dict(method=SNAPSHOT_METHOD, installed=True, removed=True, flash_writes=False)
        (self.root/'native-runtime.json').write_text(json.dumps(runtime))
        stage = 'speed_6700rpm_8a_native60'
        reference = dict(verified=True, source_sha256='clock-source',
                         tick_hz_lower=10000, tick_hz_upper=10000,
                         distance_scale=f32(.006208386))
        self.report.update(stage=stage, sample_pause_s=0, timing_limit_s=.025,
                           native_counter=True, native_clock_reference=reference,
                           memory_logging=True, queued_logging=False, logs_drained=True)
        tracker = NativeCounterAngle(6820)
        with (self.root/'observations.jsonl').open('w') as stream:
            for i in range(15001):
                tick = 40*i+1
                row = dict(self.row, t=i*.004, tachometer=0, tachometer_abs=0,
                           returned_energy_j=0, current_in_a=0,
                           native_start_tick=tick-1, native_end_tick=tick,
                           native_elapsed_ticks=40*i, native_tick_hz_lower=10000,
                           native_tick_hz_upper=10000,
                           native_distance_scale=reference['distance_scale'],
                           native_distance=0, native_distance_abs=0)
                row.update(tracker.update(row))
                stream.write(json.dumps(row)+'\n')
        self.write_metadata()
        self.assertTrue(timing_reference(self.root, self.baseline, stage, now=62,
                                        native_clock_reference=reference)['verified'])
        reused = timing_reference(self.root, self.baseline, 'speed_7200rpm_8a_native60',
                                  now=62, native_clock_reference=reference)
        self.assertTrue(reused['verified'])
        self.assertEqual(reused['replayed_maximum_rpm'], 7920)
        self.assertTrue(timing_reference(self.root, self.baseline, 'speed_7200rpm_9a_native60',
                                        now=62, native_clock_reference=reference)['verified'])
        self.report['stage'] = 'speed_7200rpm_9a_native60'
        self.write_metadata()
        next_step = timing_reference(self.root, self.baseline, 'speed_7700rpm_9a_native60',
                                     now=62, native_clock_reference=reference)
        self.assertTrue(next_step['verified'])
        self.assertEqual(next_step['replayed_maximum_rpm'], 8470)
        self.report['stage'] = 'speed_7700rpm_9a_native60'
        self.write_metadata()
        next_step = timing_reference(self.root, self.baseline, 'speed_8200rpm_9a_native60',
                                     now=62, native_clock_reference=reference)
        self.assertTrue(next_step['verified'])
        self.assertEqual(next_step['replayed_maximum_rpm'], 9020)
        from vesc_workbench.synrm_pilot import timing_stage
        for target, bound in (('speed_8200rpm_10a_native60', 9020),
                              ('speed_8700rpm_10a_native60', 9570),
                              ('speed_9200rpm_10a_native60', 10120),
                              ('speed_8700rpm_10a_rpm95', 9570)):
            self.report['stage'] = timing_stage(target)
            self.write_metadata()
            proof = timing_reference(self.root, self.baseline, target, now=62,
                                     native_clock_reference=reference)
            self.assertTrue(proof['verified'])
            self.assertEqual(proof['replayed_maximum_rpm'], bound)
        from vesc_workbench.native_counter_snapshot import DQ_SNAPSHOT_METHOD
        self.report['stage'] = 'speed_8200rpm_10a_dq'
        self.write_metadata()
        with self.assertRaisesRegex(ValueError, 'lifecycle'):
            timing_reference(self.root, self.baseline, 'speed_8200rpm_10a_dq', now=62,
                             native_clock_reference=reference)
        (self.root/'native-runtime.json').write_text(json.dumps(dict(runtime, method=DQ_SNAPSHOT_METHOD)))
        with self.assertRaisesRegex(ValueError, 'dq diagnostic'):
            timing_reference(self.root, self.baseline, 'speed_8200rpm_10a_dq', now=62,
                             native_clock_reference=reference)
        path = self.root/'observations.jsonl'
        original = path.read_text()
        with path.open('w') as stream:
            for line in original.splitlines():
                row = json.loads(line)
                row.update(native_dq_vd_v=0, native_dq_vq_v=0, native_dq_id_a=0,
                           native_dq_iq_a=0, native_dq_end_tick=row['native_end_tick']+2)
                stream.write(json.dumps(row)+'\n')
        self.assertTrue(timing_reference(self.root, self.baseline, 'speed_8700rpm_10a_dq',
                                        now=62, native_clock_reference=reference)['verified'])
        self.assertTrue(timing_reference(self.root, self.baseline, 'speed_8700rpm_10a_dq_return075',
                                        now=62, native_clock_reference=reference)['verified'])
        self.report['stage'] = 'speed_8700rpm_10a_dq_return075'
        self.write_metadata()
        self.assertTrue(timing_reference(self.root, self.baseline, 'speed_9200rpm_10a_dq_return075',
                                        now=62, native_clock_reference=reference)['verified'])
        self.report['stage'] = 'speed_9200rpm_10a_dq_return075'
        self.write_metadata()
        self.assertTrue(timing_reference(self.root, self.baseline, 'speed_9200rpm_10p5a_dq_return075',
                                        now=62, native_clock_reference=reference)['verified'])
        path.write_text(original)
        (self.root/'native-runtime.json').write_text(json.dumps(runtime))
        self.report['stage'] = stage
        self.write_metadata()
        for bad in (None, dict(reference, verified=False),
                    dict(reference, source_sha256='other-source'),
                    dict(reference, tick_hz_upper=10001),
                    dict(reference, distance_scale=.01)):
            with self.assertRaises(ValueError):
                timing_reference(self.root, self.baseline, stage, now=62,
                                 native_clock_reference=bad)
        for bad in (dict(runtime, removed=False), dict(runtime, method='inline')):
            (self.root/'native-runtime.json').write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                timing_reference(self.root, self.baseline, stage, now=62,
                                 native_clock_reference=reference)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.baseline = b'timing-test-baseline'
        self.row = dict(t=0, command_a=0, command_interval_s=.004, latency_s=.001,
                        current_motor_a=0, id_a=0, iq_a=0, duty=0, v_in=24.5,
                        temp_mos_c=27, position_deg=81, fault_code=0)
        self.report = dict(ok=True, zero_current_verified=True, baseline_unchanged=True,
                           capture_timing=CAPTURE_TIMING,
                           excitation_sent=False, configuration_writes=False, errors=[],
                           stage='speed_2700rpm_5a_hold', coast_cadence=False,
                           sample_pause_s=0, duration_s=60, timing_limit_s=.005,
                           maximum_command_interval_s=.004, maximum_get_values_latency_s=.001)
        self.final = dict(read_only=True, zero_current_verified=True, baseline_restored=True,
                          app_isolated=True, excitation_sent=False,
                          baseline_sha256=hashlib.sha256(self.baseline).hexdigest(),
                          samples=[dict(self.row, t=61+i*.04) for i in range(11)])
        self.write_metadata()
        with (self.root/'observations.jsonl').open('w') as f:
            for i in range(15001):
                f.write(json.dumps(dict(self.row, t=i*.004))+'\n')

    def write_metadata(self):
        (self.root/'result.json').write_text(json.dumps(self.report))
        (self.root/'final-readback.json').write_text(json.dumps(self.final))

    def check(self, **kwargs):
        return timing_reference(self.root, self.baseline, 'speed_2700rpm_5a_hold', now=62, **kwargs)

    def test_successful_matching_raw_evidence(self):
        result = self.check()
        self.assertTrue(result['verified'])
        self.assertEqual(result['samples'], 15001)

    def test_older_timestamp_method_requires_a_new_probe(self):
        del self.report['capture_timing']
        self.write_metadata()
        with self.assertRaisesRegex(ValueError, 'timestamp method'):
            self.check()

    def test_failed_report_cannot_be_used_even_with_good_raw_data(self):
        self.report['ok'] = False
        self.write_metadata()
        with self.assertRaises(ValueError):
            self.check()

    def test_modes_and_cadence_must_match(self):
        for options in (dict(coast=True), dict(above_normal=True), dict(defer_gc=True), dict(buffered_rx=True)):
            with self.assertRaises(ValueError):
                self.check(**options)

    def test_stale_or_different_baseline_refused(self):
        with self.assertRaises(ValueError):
            timing_reference(self.root, self.baseline, 'speed_2700rpm_5a_hold', now=1000)
        with self.assertRaises(ValueError):
            timing_reference(self.root, b'other', 'speed_2700rpm_5a_hold', now=62)

    def test_above_normal_proof_requires_matching_thread_switch_interval(self):
        self.report['host_scheduling'] = dict(applied=True)
        for interval in (None, .005, .002):
            self.report['host_scheduling']['thread_switch_interval_s'] = interval
            self.write_metadata()
            with self.assertRaises(ValueError):
                self.check(above_normal=True)
        self.report['host_scheduling']['thread_switch_interval_s'] = .001
        self.write_metadata()
        self.assertTrue(self.check(above_normal=True)['verified'])

    def test_raw_gap_or_current_cannot_be_hidden_by_summary(self):
        original = (self.root/'observations.jsonl').read_text()
        for changes in (dict(command_a=1), dict(command_interval_s=.006), dict(latency_s=float('nan'))):
            (self.root/'observations.jsonl').write_text(original+json.dumps(dict(self.row, t=60.004, **changes))+'\n')
            with self.assertRaises(ValueError):
                self.check()

    def test_bad_final_standstill_refused(self):
        self.final['samples'][-1]['position_deg'] = 90
        self.write_metadata()
        with self.assertRaises(ValueError):
            self.check()

    def test_counter_stage_requires_reproducible_raw_counters(self):
        self.report.update(stage='speed_2200rpm_5a_counter', sample_pause_s=.002, timing_limit_s=.025)
        self.write_metadata()
        with self.assertRaises(ValueError):
            timing_reference(self.root, self.baseline, self.report['stage'], now=62)
        tracker = CounterAngle(2420)
        with (self.root/'observations.jsonl').open('w') as stream:
            for i in range(15001):
                row = dict(self.row, t=i*.004, tachometer=0, tachometer_abs=0)
                row.update(tracker.update(row))
                stream.write(json.dumps(row)+'\n')
        self.assertTrue(timing_reference(self.root, self.baseline, self.report['stage'], now=62)['verified'])

    def test_battery_counter_stage_rejects_nonfinite_returned_energy(self):
        self.report.update(stage='speed_2700rpm_6a_counter_return', sample_pause_s=.002, timing_limit_s=.025)
        self.write_metadata()
        tracker = CounterAngle(2970)
        with (self.root/'observations.jsonl').open('w') as stream:
            for i in range(15001):
                row = dict(self.row, t=i*.004, tachometer=0, tachometer_abs=0, returned_energy_j=0, current_in_a=0)
                row.update(tracker.update(row))
                stream.write(json.dumps(row)+'\n')
        self.assertTrue(timing_reference(self.root, self.baseline, self.report['stage'], now=62)['verified'])
        with (self.root/'observations.jsonl').open('a') as stream:
            row = dict(self.row, t=60.004, tachometer=0, tachometer_abs=0, returned_energy_j=float('nan'), current_in_a=0)
            row.update(tracker.update(row))
            stream.write(json.dumps(row)+'\n')
        with self.assertRaisesRegex(ValueError, 'battery-return'):
            timing_reference(self.root, self.baseline, self.report['stage'], now=62)

    def test_reused_workload_must_pass_the_tighter_new_speed_envelope(self):
        self.report.update(stage='speed_5700rpm_8a_hold60', sample_pause_s=.002, timing_limit_s=.025,
                           queued_logging=True, logs_drained=True)
        self.write_metadata()
        def write_rows(slow):
            tracker = CounterAngle(6270)
            with (self.root/'observations.jsonl').open('w') as stream:
                for i in range(15001):
                    row = dict(self.row, t=i*.004, tachometer=0, tachometer_abs=0,
                               returned_energy_j=0, current_in_a=0,
                               latency_s=.0028 if slow and i == 10000 else .001)
                    row.update(tracker.update(row))
                    stream.write(json.dumps(row)+'\n')
        write_rows(False)
        result = timing_reference(self.root, self.baseline, 'speed_6200rpm_8a_hold60', now=62)
        self.assertTrue(result['verified'])
        self.assertEqual(result['replayed_maximum_rpm'], 6820)
        self.assertEqual(result['probe_stage'], 'speed_5700rpm_8a_hold60')
        write_rows(True)
        self.report['maximum_get_values_latency_s'] = .0028
        self.write_metadata()
        self.assertTrue(timing_reference(self.root, self.baseline, 'speed_5700rpm_8a_hold60', now=62)['verified'])
        with self.assertRaisesRegex(ValueError, 'temporally ambiguous'):
            timing_reference(self.root, self.baseline, 'speed_6200rpm_8a_hold60', now=62)

    def test_memory_stage_requires_matching_backend_and_completed_drain(self):
        stage = 'speed_6700rpm_8a_hold60'
        self.report.update(stage=stage, sample_pause_s=.002, timing_limit_s=.025,
                           memory_logging=True, queued_logging=False, logs_drained=True)
        tracker = CounterAngle(7370)
        with (self.root/'observations.jsonl').open('w') as stream:
            for i in range(15001):
                row = dict(self.row, t=i*.004, tachometer=0, tachometer_abs=0,
                           returned_energy_j=0, current_in_a=0)
                row.update(tracker.update(row))
                stream.write(json.dumps(row)+'\n')
        self.write_metadata()
        self.assertTrue(timing_reference(self.root, self.baseline, stage, now=62)['verified'])
        for changes in (dict(memory_logging=False), dict(queued_logging=True), dict(logs_drained=False)):
            original = self.report.copy()
            self.report.update(changes)
            self.write_metadata()
            with self.assertRaises(ValueError):
                timing_reference(self.root, self.baseline, stage, now=62)
            self.report = original
