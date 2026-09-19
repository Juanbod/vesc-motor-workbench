"""Bounded logging/timing probe; sends zero current only, never rewrites config."""
import argparse
import gc
import json
import math
from pathlib import Path
from time import perf_counter, sleep

from vesc_workbench.fixture import require_free, verify_encoder_quiet
from vesc_workbench.locked_probe import ProbeClient
from vesc_workbench.synrm_repeatability import read_quiet_baseline
from vesc_workbench.synrm_pilot import stage_limits, counter_timing
from vesc_workbench.host_scheduling import above_normal_priority, defer_cyclic_gc
from vesc_workbench.counter_angle import CounterAngle, guard_speed
from vesc_workbench.battery_return import BatteryReturnMonitor, require_battery_source
from vesc_workbench.queued_log import open_trial_log, check_trial_log
from vesc_workbench.telemetry_capture import CAPTURE_TIMING, capture_values
from vesc_workbench.native_probe_client import NativeProbeClient
from vesc_workbench.native_counter_tracker import NativeCounterAngle
from vesc_workbench.native_clock_calibration import load_clock_reference


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--above-normal', action='store_true')
    p.add_argument('--defer-cyclic-gc', action='store_true')
    p.add_argument('--coast-cadence', action='store_true')
    p.add_argument('--buffered-rx', action='store_true')
    p.add_argument('--native-clock-calibration')
    p.add_argument('--duration-s', type=int, choices=(15, 60), default=15)
    p.add_argument('--stage', choices=('speed_700rpm_5a_upper', 'speed_1200rpm_5a_smooth',
                                      'speed_1700rpm_5a_smooth', 'speed_2200rpm_5a_smooth',
                                      'speed_2200rpm_5a_hold', 'speed_2700rpm_5a_hold',
                                      'speed_2200rpm_5a_counter', 'speed_2700rpm_5a_counter',
                                      'speed_2700rpm_6a_counter_return', 'speed_2700rpm_6a_counter_return_coast',
                                      'speed_3200rpm_7a_counter_return_coast', 'speed_3700rpm_7a_counter_return_coast',
                                      'speed_4200rpm_7a_counter_return_coast', 'speed_4700rpm_7a_counter_return_coast',
                                      'speed_5200rpm_7a_coast_reacquire', 'speed_5700rpm_8a_hold60',
                                      'speed_6200rpm_8a_hold60', 'speed_6700rpm_8a_hold60',
                                      'speed_6200rpm_8a_native60', 'speed_6700rpm_8a_native60',
                                      'speed_7200rpm_8a_native60', 'speed_7200rpm_9a_native60',
                                      'speed_7700rpm_9a_native60', 'speed_8200rpm_9a_native60',
                                      'speed_8200rpm_10a_native60', 'speed_8700rpm_10a_native60',
                                      'speed_9200rpm_10a_native60', 'speed_8700rpm_10a_rpm95',
                                      'speed_8200rpm_10a_dq', 'speed_8700rpm_10a_dq',
                                      'speed_8700rpm_10a_dq_return075', 'speed_9200rpm_10a_dq_return075',
                                      'speed_9200rpm_10p5a_dq_return075'),
                   default='speed_700rpm_5a_upper')
    args = p.parse_args()
    limits = stage_limits(args.stage)
    timing_limit, counter_window = counter_timing(limits, coast=args.coast_cadence)
    tracker_type = NativeCounterAngle if limits.get('native_counter') else CounterAngle
    counter = tracker_type(limits['maximum_rpm'], timing_limit, counter_window) if limits.get('counter_assisted') else None
    battery_source = require_battery_source() if limits.get('return_current_a') else None
    battery_monitor = BatteryReturnMonitor() if battery_source is not None else None
    sample_pause = limits.get('coast_sample_interval_s', limits['sample_interval_s']) if args.coast_cadence else limits['sample_interval_s']
    require_free()
    baseline = Path(args.baseline).read_bytes()
    native_reference = None
    client_type, client_options = ProbeClient, {}
    if limits.get('native_counter'):
        if not args.native_clock_calibration:
            p.error('Native acquisition requires a fresh --native-clock-calibration')
        native_reference = load_clock_reference(args.native_clock_calibration, baseline)
        client_type = NativeProbeClient
        client_options = dict(baseline=baseline, clock_calibration=native_reference,
                              maximum_rpm=limits['maximum_rpm'], dq=limits.get('native_dq', False))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(excitation_sent=False, configuration_writes=False, zero_current_verified=False,
                  ok=False, timing_limit_s=timing_limit, stage=args.stage,
                  sample_pause_s=sample_pause, coast_cadence=args.coast_cadence, duration_s=args.duration_s, errors=[],
                  maximum_phase_s={}, slow_command_intervals=[], maximum_gc_pause_s=0)
    report['queued_logging'] = limits.get('queued_logging', False)
    report['memory_logging'] = limits.get('memory_logging', False)
    report['capture_timing'] = CAPTURE_TIMING
    if native_reference is not None:
        report['native_counter'] = True
        report['native_clock_reference'] = native_reference
    rows = []
    if battery_source is not None:
        report['battery_source'] = battery_source
    gaps = []
    gc_started = {}
    def gc_timing(phase, info):
        generation = info['generation']
        if phase == 'start':
            gc_started[generation] = perf_counter()
        elif generation in gc_started:
            report['maximum_gc_pause_s'] = max(report['maximum_gc_pause_s'],
                                                perf_counter()-gc_started.pop(generation))
    with above_normal_priority(args.above_normal) as scheduling, \
         defer_cyclic_gc(args.defer_cyclic_gc) as gc_mode, client_type('COM10', timeout_s=.1, buffered_rx=args.buffered_rx, **client_options) as client:
        report['host_scheduling'] = scheduling
        report['cyclic_gc'] = gc_mode
        report['buffered_rx'] = args.buffered_rx
        client.response_timeout_s = .1
        gc.callbacks.append(gc_timing)
        try:
            entry = read_quiet_baseline(client, baseline)
            (output/'entry-readback.json').write_text(json.dumps(entry, indent=2), encoding='utf-8')
            started = perf_counter()
            previous_command = None
            previous_phases = None
            with open_trial_log(output/'samples.jsonl', limits.get('queued_logging', False), memory=limits.get('memory_logging', False)) as raw, \
                 open_trial_log(output/'observations.jsonl', limits.get('queued_logging', False), memory=limits.get('memory_logging', False)) as observations:
                while perf_counter()-started < args.duration_s:
                    cycle_start = perf_counter()
                    require_free()
                    if (output/'STOP').exists():
                        raise ValueError('STOP requested')
                    now = perf_counter()
                    interval = 0 if previous_command is None else now-previous_command
                    previous_command = now
                    if interval > timing_limit and len(report['slow_command_intervals']) < 20:
                        report['slow_command_intervals'].append(dict(t=now, interval_s=interval,
                            previous_cycle=previous_phases, current_interlock_s=now-cycle_start))
                    client.set_current(0)
                    sent = perf_counter()
                    if sample_pause > 0:
                        sleep(sample_pause)
                    before = perf_counter()
                    row = capture_values(client)
                    if battery_monitor is not None:
                        row['returned_energy_j'] = battery_monitor.observe(row)
                    if counter is not None:
                        previous_counter_sample = counter.previous
                        try:
                            evidence = counter.update(row)
                            guard_speed(evidence, limits['maximum_rpm'])
                        except ValueError:
                            report['failed_counter_sample'] = row
                            report['failed_counter_previous'] = previous_counter_sample
                            raise
                        row.update(evidence)
                    received = perf_counter()
                    if (not all(math.isfinite(v) for v in row.values()) or row['fault_code']
                            or abs(row['current_motor_a']) > .1 or math.hypot(row['id_a'], row['iq_a']) > .2
                            or abs(row['duty']) > .001 or not 18 <= row['v_in'] <= 30 or row['temp_mos_c'] > 50):
                        raise ValueError('Quiet timing probe telemetry guard')
                    rows.append(row)
                    if interval:
                        gaps.append(interval)
                    raw.write(json.dumps(row, allow_nan=False)+'\n')
                    check_trial_log(raw)
                    observations.write(json.dumps(dict(row, command_a=0, command_interval_s=interval), allow_nan=False)+'\n')
                    check_trial_log(observations)
                    finished = perf_counter()
                    previous_phases = dict(interlock_s=now-cycle_start, send_s=sent-now,
                        sleep_s=before-sent, read_s=received-before,
                        validation_logging_s=finished-received, total_s=finished-cycle_start)
                    for name, value in previous_phases.items():
                        report['maximum_phase_s'][name] = max(value, report['maximum_phase_s'].get(name, 0))
            report['logs_drained'] = True
            tail = [r for r in rows if r['t'] >= rows[-1]['t']-.4]
            verify_encoder_quiet(tail)
            final = read_quiet_baseline(client, baseline)
            (output/'final-readback.json').write_text(json.dumps(final, indent=2), encoding='utf-8')
            report.update(zero_current_verified=True, baseline_unchanged=True, samples=len(rows),
                          maximum_command_interval_s=max(gaps),
                          over_20ms_command_intervals=sum(g > .02 for g in gaps),
                          over_limit_command_intervals=sum(g > timing_limit for g in gaps),
                          maximum_get_values_latency_s=max(r['latency_s'] for r in rows),
                          ok=all(g <= timing_limit for g in gaps)
                             and all(r['latency_s'] <= timing_limit for r in rows))
        except (Exception, KeyboardInterrupt) as exc:
            report['errors'].append(str(exc) or type(exc).__name__)
        finally:
            gc.callbacks.remove(gc_timing)
            client.set_current(0)
            (output/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    if native_reference is not None:
        (output/'native-runtime.json').write_text(json.dumps(client.native_snapshot_runtime, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
