"""One free-rotor current pilot with no automatic repeat or speed command."""
from dataclasses import asdict
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import re
from time import perf_counter, sleep

from .fixture import FixtureInterlock, require_free, verify_encoder_quiet
from .hfi_capture import write_motor_verified
from .locked_probe import preflight_config
from .locked_rotor import angular_delta
from .synrm_pilot import build_pilot, encoder_policy, validate_observation, fresh_adc_changes, stage_limits
from .synrm_pilot import rotation_current, ROTATION_STAGES, SPEED_STAGES
from .synrm_pilot import adjacent_speed_evidence, speed_stability, timing_stage, counter_timing
from .wire_config import patch_config
from .counter_angle import CounterAngle, guard_speed, replay_counter_run
from .queued_log import open_trial_log, check_trial_log
from .battery_return import BatteryReturnMonitor, require_battery_source, audit_battery_return
from .telemetry_capture import CAPTURE_TIMING, capture_values
from .native_counter_tracker import NativeCounterAngle
from .native_clock_calibration import load_clock_reference
from .native_counter_snapshot import SNAPSHOT_METHOD, DQ_SNAPSHOT_METHOD, validate_dq_record


def verify_native_runtime(folder, *, dq=False):
    runtime = json.loads((Path(folder)/'native-runtime.json').read_text(encoding='utf-8'))
    if (runtime.get('method') != (DQ_SNAPSHOT_METHOD if dq else SNAPSHOT_METHOD) or runtime.get('installed') is not True
            or runtime.get('removed') is not True or runtime.get('flash_writes') is not False):
        raise ValueError('Prepared native snapshot lifecycle does not match the active method')


def counter_type(limits):
    return NativeCounterAngle if limits.get('native_counter') else CounterAngle


def counter_method(limits):
    return ('sector_assisted_encoder_native_clock_v1' if limits.get('native_counter')
            else 'sector_assisted_encoder_request_brackets_v1')


def check_encoder(client):
    client.send_payload(b'\x14encoder')
    lines = []
    for _ in range(8):
        text = client.read_response(21)[1:].decode('utf-8', errors='replace').strip()
        if not text:
            break
        lines.append(text)
    else:
        raise ValueError('Encoder diagnostic terminator missing')
    text = '\n'.join(lines)
    rate = re.search(r'error rate:\s*([\d.]+)\s*%', text)
    if 'SPI' not in text or not rate or float(rate[1]) != 0:
        raise ValueError('SPI encoder diagnostic did not report zero error rate')
    return text


def extension_reference(folder, baseline):
    folder = Path(folder)
    prior = json.loads((folder/'result.json').read_text(encoding='utf-8'))
    final = json.loads((folder/'final-readback.json').read_text(encoding='utf-8'))
    for key in ('ok', 'excitation_sent', 'motion_observed', 'zero_current_verified', 'baseline_restored', 'no_faults'):
        if prior.get(key) is not True:
            raise ValueError(f'Prior physical pilot is missing {key}')
    if prior.get('errors') or prior['plan'].get('stage', 'pilot') != 'pilot':
        raise ValueError('Extension requires the initial pilot, not a chain of escalations')
    if not final.get('read_only') or not final.get('zero_current_verified') or not final.get('app_isolated'):
        raise ValueError('Independent quiet readback required')
    import hashlib
    if hashlib.sha256(baseline).hexdigest() != final['baseline_sha256']:
        raise ValueError('Independent readback uses another baseline')
    verify_encoder_quiet(final['samples'])
    return dict(source=str(folder.resolve()), starting_pose_deg=final['samples'][-1]['position_deg'],
                earlier_powered_travel_deg=prior['travel_deg'],
                interpretation='Current/motion evidence only, not global offset calibration or total travel qualification')


def rotation_reference(folder, baseline):
    """Review a recovered 90-degree extension stop, never an arbitrary failure."""
    import hashlib
    folder = Path(folder)
    prior = json.loads((folder/'result.json').read_text(encoding='utf-8'))
    final = json.loads((folder/'final-readback.json').read_text(encoding='utf-8'))
    if (prior.get('status') != 'travel_envelope_exceeded'
            or prior['plan'].get('stage') != 'extension_3a'
            or prior.get('errors') != ['Stale encoder, unexpected direction, travel or speed limit']):
        raise ValueError('Rotation requires the reviewed extension travel stop, not other failures or repeats')
    for key in ('excitation_sent', 'zero_current_verified', 'baseline_restored', 'no_faults', 'app_isolated'):
        if prior.get(key) is not True:
            raise ValueError(f'Prior extension is missing {key}')
    if not all(final.get(k) is True for k in ('read_only', 'zero_current_verified', 'app_isolated', 'baseline_restored')):
        raise ValueError('Independent recovered readback required')
    if (hashlib.sha256(baseline).hexdigest() != final['baseline_sha256']
            or (folder/'mcconf-before.bin').read_bytes() != baseline):
        raise ValueError('Prior extension baseline mismatch')
    verify_encoder_quiet(final['samples'])
    candidate = (folder/'mcconf-candidate.bin').read_bytes()
    if hashlib.sha256(candidate).hexdigest() != prior['plan']['candidate_sha256']:
        raise ValueError('Prior candidate evidence mismatch')
    source = encoder_policy(candidate)
    rows = [json.loads(line) for line in (folder/'observations.jsonl').read_text(encoding='utf-8').splitlines()]
    if (len(rows) < 10 or not 90 <= rows[-1]['travel_deg'] < 95
            or any(row['travel_deg'] >= 90 for row in rows[:-1])
            or max(row['command_a'] for row in rows) != 3):
        raise ValueError('Raw evidence does not identify the single 90-degree stop at 3 A')
    for row in rows:
        # Only the known displacement guard is excluded; all other guards stay.
        validate_observation(dict(row, travel_deg=0), row['command_a'], source,
                             settled_current=row['elapsed_s'] >= .6, stage='extension_3a')
    return dict(source=str(folder.resolve()), starting_pose_deg=final['samples'][-1]['position_deg'],
                earlier_powered_travel_deg=rows[-1]['travel_deg'],
                interpretation='Recovered angular-envelope stop; supports a distinct bounded rotation experiment, not calibration')


def repeatability_reference(folder, baseline, *, completed_series=False):
    """At most three same-current repeats, each after a qualified rotation."""
    import hashlib
    folder = Path(folder)
    prior = json.loads((folder/'result.json').read_text(encoding='utf-8'))
    final = json.loads((folder/'final-readback.json').read_text(encoding='utf-8'))
    if (prior.get('status') != 'bounded_rotation_observed'
            or prior['plan'].get('stage') not in ROTATION_STAGES or prior.get('errors')
            or any(prior.get(k) for k in ('full_event_travel_exceeded', 'coast_guard_exceeded', 'telemetry_guard_exceeded'))):
        raise ValueError('Repeat requires a successful bounded rotation, never a failed attempt')
    for key in ('ok', 'excitation_sent', 'motion_observed', 'zero_current_verified',
                'baseline_restored', 'no_faults', 'app_isolated'):
        if prior.get(key) is not True:
            raise ValueError(f'Prior rotation is missing {key}')
    previous_index = 0 if prior['plan']['stage'] == 'rotation_3a' else prior['repeatability_index']
    if (type(previous_index) is not int
            or (previous_index != 3 if completed_series else not 0 <= previous_index < 3)):
        raise ValueError('Three-repeat allowance exhausted or invalid')
    if not all(final.get(k) is True for k in ('read_only', 'zero_current_verified', 'app_isolated', 'baseline_restored')):
        raise ValueError('Independent recovered readback required')
    if (hashlib.sha256(baseline).hexdigest() != final['baseline_sha256']
            or (folder/'mcconf-before.bin').read_bytes() != baseline):
        raise ValueError('Repeat baseline mismatch')
    verify_encoder_quiet(final['samples'])
    candidate = (folder/'mcconf-candidate.bin').read_bytes()
    _, expected = build_pilot(baseline, prior['plan']['changes']['foc_encoder_offset'],
                              prior['plan']['source_pose_deg'], prior['plan']['stage'])
    if candidate != expected or hashlib.sha256(candidate).hexdigest() != prior['plan']['candidate_sha256']:
        raise ValueError('Prior candidate is not the reviewed 3 A rotation configuration')
    source = encoder_policy(candidate)
    rows = [json.loads(line) for line in (folder/'observations.jsonl').read_text(encoding='utf-8').splitlines()]
    if (len(rows) < 30 or not 3.5 <= rows[-1]['elapsed_s'] < 4
            or rows[-1]['travel_deg'] < 360 or rows[-1]['encoder_rpm'] < 5):
        raise ValueError('Prior raw rotation completion criteria missing')
    for row in rows:
        validate_observation(row, row['command_a'], source,
                             settled_current=row['elapsed_s'] >= .6, stage=prior['plan']['stage'])
    samples = [json.loads(line) for line in (folder/'samples.jsonl').read_text(encoding='utf-8').splitlines()]
    starts = [r['position_deg'] for r in samples if r['stage'] == 'before_current']
    if len(starts) != 1:
        raise ValueError('One recorded starting pose required')
    previous_poses = [] if previous_index == 0 else prior['prior_run_reference']['tested_start_poses_deg']
    if len(previous_poses) != previous_index:
        raise ValueError('Repeat starting-pose history mismatch')
    tested = [*previous_poses, starts[0]]
    next_pose = final['samples'][-1]['position_deg']
    if any(not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p < 360 for p in tested):
        raise ValueError('Invalid starting-pose history')
    if not completed_series and min(abs(angular_delta(next_pose, p)) for p in tested) < 10:
        raise ValueError('Next natural stop is within 10 degrees of an already tested start')
    return dict(source=str(folder.resolve()), starting_pose_deg=next_pose,
                repeatability_index=previous_index+1, tested_start_poses_deg=tested,
                interpretation='Same 3 A ceiling, distinct natural stop angles, not guaranteed startup or calibrated offset')


def speed_reference(folder, baseline):
    folder = Path(folder)
    result = json.loads((folder/'result.json').read_text(encoding='utf-8'))
    if result['plan']['stage'] != 'repeatability_3a' or result.get('repeatability_index') != 3:
        raise ValueError('Speed step requires the completed three-start series')
    reference = repeatability_reference(folder, baseline, completed_series=True)
    series = json.loads((folder.parent/'series.json').read_text(encoding='utf-8'))
    if (series.get('ok') is not True or series.get('status') != 'three_starts_observed'
            or len(series['trials']) != 3
            or any(r.get('ok') is not True or r.get('independent_zero_verified') is not True for r in series['trials'])
            or Path(series['trials'][-1]['path']).resolve() != folder.resolve()):
        raise ValueError('Successful three-trial series summary required')
    reference.pop('repeatability_index')
    reference['interpretation'] = 'Completed low-current startup series supports one bounded speed increase, not maximum-speed or offset qualification'
    return reference


def timing_reference(folder, baseline, stage, *, coast=False, above_normal=False,
                     defer_gc=False, buffered_rx=False, now=None, native_clock_reference=None):
    """Offline capacity gate, to be evaluated before opening the controller."""
    folder = Path(folder)
    report = json.loads((folder/'result.json').read_text(encoding='utf-8'))
    limits = stage_limits(stage)
    gap, counter_window = counter_timing(limits, coast=coast)
    pause_s = limits.get('coast_sample_interval_s', limits['sample_interval_s']) if coast else limits['sample_interval_s']
    if (any(report.get(k) is not True for k in ('ok', 'zero_current_verified', 'baseline_unchanged'))
            or report.get('excitation_sent') is not False or report.get('configuration_writes') is not False
            or report.get('errors') or report.get('stage') not in (stage, timing_stage(stage, coast=coast))
            or report.get('coast_cadence', False) != coast or report.get('sample_pause_s') != pause_s
            or report.get('duration_s', 0) < 60 or report.get('timing_limit_s') != gap
            or report.get('buffered_rx', False) != buffered_rx
            or report.get('host_scheduling', {}).get('applied', False) != above_normal
            or (above_normal and report.get('host_scheduling', {}).get('thread_switch_interval_s') != .001)
            or report.get('cyclic_gc', {}).get('deferred', False) != defer_gc
            or report.get('queued_logging', False) != limits.get('queued_logging', False)
            or report.get('memory_logging', False) != limits.get('memory_logging', False)
            or report.get('native_counter', False) != limits.get('native_counter', False)
            or ((limits.get('queued_logging') or limits.get('memory_logging')) and report.get('logs_drained') is not True)
            or report.get('precise_short_pause', False)):
        raise ValueError('Successful matching 60-second zero-current timing probe required')
    if report.get('capture_timing') != CAPTURE_TIMING:
        raise ValueError('Timing proof must match the active capture timestamp method')
    if limits.get('native_counter'):
        verify_native_runtime(folder, dq=limits.get('native_dq', False))
        if (not native_clock_reference or native_clock_reference.get('verified') is not True
                or report.get('native_clock_reference', {}).get('source_sha256') != native_clock_reference['source_sha256']):
            raise ValueError('Native timing proof requires matching clock calibration')
    for key in ('maximum_command_interval_s', 'maximum_get_values_latency_s'):
        value = report.get(key)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= gap:
            raise ValueError('Timing probe exceeds acquisition budget')
    final = json.loads((folder/'final-readback.json').read_text(encoding='utf-8'))
    if (any(final.get(k) is not True for k in ('read_only', 'zero_current_verified', 'baseline_restored', 'app_isolated'))
            or final.get('excitation_sent') is not False
            or final.get('baseline_sha256') != hashlib.sha256(baseline).hexdigest()):
        raise ValueError('Timing probe baseline or independent quiet readback mismatch')
    try:
        verify_encoder_quiet(final['samples'])
    except FixtureInterlock as exc:
        raise ValueError('Timing probe final standstill check failed') from exc
    age = (perf_counter() if now is None else now)-final['samples'][-1]['t']
    if not math.isfinite(age) or not 0 <= age <= 600:
        raise ValueError('Timing probe is stale or belongs to another clock epoch')
    previous = first = None
    count = 0
    counter_probe = counter_type(limits)(limits['maximum_rpm'], gap, counter_window) if limits.get('counter_assisted') else None
    battery_probe = BatteryReturnMonitor() if limits.get('return_current_a') else None
    with (folder/'observations.jsonl').open(encoding='utf-8') as source:
        for line in source:
            row = json.loads(line)
            if limits.get('native_dq'):
                validate_dq_record(row)
            keys = ('t', 'command_a', 'command_interval_s', 'latency_s', 'current_motor_a',
                    'id_a', 'iq_a', 'duty', 'v_in', 'temp_mos_c', 'position_deg', 'fault_code')
            if any(k not in row or not isinstance(row[k], (int, float)) or not math.isfinite(row[k]) for k in keys):
                raise ValueError('Invalid raw timing evidence')
            if (row['command_a'] != 0 or row['fault_code'] != 0 or abs(row['current_motor_a']) > .1
                    or math.hypot(row['id_a'], row['iq_a']) > .2 or abs(row['duty']) > .001
                    or not 18 <= row['v_in'] <= 30 or row['temp_mos_c'] > 50
                    or not 0 <= row['position_deg'] < 360 or not 0 <= row['latency_s'] <= gap
                    or not 0 <= row['command_interval_s'] <= gap
                    or (previous is not None and not 0 < row['t']-previous <= gap)):
                raise ValueError('Raw timing evidence violates zero-current or timing bounds')
            if counter_probe is not None:
                if limits.get('native_counter') and any(row.get(k) != native_clock_reference[v] for k, v in (
                        ('native_tick_hz_lower', 'tick_hz_lower'), ('native_tick_hz_upper', 'tick_hz_upper'),
                        ('native_distance_scale', 'distance_scale'))):
                    raise ValueError('Native raw sample calibration mismatch')
                evidence = counter_probe.update(row)
                guard_speed(evidence, limits['maximum_rpm'])
                if any(key not in row or not math.isfinite(row[key]) or abs(row[key]-value) > .00001
                       for key, value in evidence.items()):
                    raise ValueError('Timing probe lacks reproducible counter evidence')
            if battery_probe is not None:
                energy = battery_probe.observe(row)
                if ('returned_energy_j' not in row or not math.isfinite(row['returned_energy_j'])
                        or abs(row['returned_energy_j']-energy) > .00001):
                    raise ValueError('Timing probe lacks reproducible battery-return evidence')
            first = row['t'] if first is None else first
            previous = row['t']
            count += 1
    if count < 50 or previous-first < 59.5 or final['samples'][0]['t'] < previous:
        raise ValueError('Incomplete timing probe or invalid final-readback ordering')
    return dict(path=str(folder.resolve()), stage=stage, probe_stage=report['stage'], coast_cadence=coast,
                samples=count, age_s=age, maximum_gap_s=gap,
                replayed_maximum_rpm=limits['maximum_rpm'], verified=True)


def higher_speed_reference(folder, baseline, stage='speed_180rpm_3a'):
    predecessors = {'speed_180rpm_3a': 'speed_90rpm_3a',
                    'speed_360rpm_3a': 'speed_180rpm_3a',
                    'speed_540rpm_3a': 'speed_360rpm_3a',
                    'speed_540rpm_5a': 'speed_540rpm_3a',
                    'speed_540rpm_5a_smooth': 'speed_540rpm_3a',
                    'speed_600rpm_5a_smooth': 'speed_540rpm_5a_smooth',
                    'speed_660rpm_5a_smooth': 'speed_600rpm_5a_smooth',
                    'speed_700rpm_5a_smooth': 'speed_660rpm_5a_smooth',
                    'speed_700rpm_5a_upper': 'speed_700rpm_5a_smooth',
                    'speed_1200rpm_5a_smooth': 'speed_700rpm_5a_upper',
                    'speed_1700rpm_5a_smooth': 'speed_1200rpm_5a_smooth',
                    'speed_2200rpm_5a_smooth': 'speed_1700rpm_5a_smooth',
                    'speed_2200rpm_5a_hold': 'speed_1700rpm_5a_smooth',
                    'speed_2700rpm_5a_hold': 'speed_2200rpm_5a_hold',
                    'speed_2200rpm_5a_counter': 'speed_2200rpm_5a_hold',
                    'speed_2700rpm_5a_counter': 'speed_2200rpm_5a_counter',
                    'speed_2700rpm_6a_counter': 'speed_2200rpm_5a_counter',
                    'speed_90rpm_2a_return_probe': 'speed_2200rpm_5a_counter',
                    'speed_90rpm_2a_return_margin': 'speed_2200rpm_5a_counter',
                    'speed_2700rpm_6a_counter_return': 'speed_90rpm_2a_return_margin',
                    'speed_2700rpm_6a_counter_return_coast': 'speed_90rpm_2a_return_margin',
                    'speed_3200rpm_7a_counter_return_coast': 'speed_2700rpm_6a_counter_return_coast',
                    'speed_3700rpm_7a_counter_return_coast': 'speed_3200rpm_7a_counter_return_coast',
                    'speed_4200rpm_7a_counter_return_coast': 'speed_3700rpm_7a_counter_return_coast',
                    'speed_4700rpm_7a_counter_return_coast': 'speed_4200rpm_7a_counter_return_coast',
                    'speed_4700rpm_7a_coast_reacquire': 'speed_4200rpm_7a_counter_return_coast',
                    'speed_5200rpm_7a_coast_reacquire': 'speed_4700rpm_7a_coast_reacquire',
                    'speed_5200rpm_7a_hold60': 'speed_4700rpm_7a_coast_reacquire',
                    'speed_5700rpm_8a_hold60': 'speed_5200rpm_7a_hold60',
                    'speed_6200rpm_8a_hold60': 'speed_5700rpm_8a_hold60',
                    'speed_6700rpm_8a_hold60': 'speed_6200rpm_8a_hold60',
                    'speed_6200rpm_8a_native60': 'speed_6200rpm_8a_hold60',
                    'speed_6700rpm_8a_native60': 'speed_6200rpm_8a_native60',
                    'speed_7200rpm_8a_native60': 'speed_6700rpm_8a_native60',
                    'speed_7200rpm_9a_native60': 'speed_6700rpm_8a_native60',
                    'speed_7700rpm_9a_native60': 'speed_7200rpm_9a_native60',
                    'speed_8200rpm_9a_native60': 'speed_7700rpm_9a_native60',
                    'speed_8200rpm_10a_native60': 'speed_7700rpm_9a_native60',
                    'speed_8700rpm_10a_native60': 'speed_8200rpm_10a_native60',
                    'speed_9200rpm_10a_native60': 'speed_8700rpm_10a_native60',
                    'speed_8700rpm_10a_rpm95': 'speed_8200rpm_10a_native60',
                    'speed_8200rpm_10a_dq': 'speed_8200rpm_10a_native60',
                    'speed_8700rpm_10a_dq': 'speed_8200rpm_10a_dq',
                    'speed_8700rpm_10a_dq_return075': 'speed_8200rpm_10a_dq',
                    'speed_9200rpm_10a_dq_return075': 'speed_8700rpm_10a_dq_return075',
                    'speed_9200rpm_10p5a_dq_return075': 'speed_8700rpm_10a_dq_return075',
                    'speed_540rpm_5a_restart': 'speed_9200rpm_10p5a_dq_return075',
                    'speed_540rpm_5a_restart_return075': 'speed_9200rpm_10p5a_dq_return075'}
    if stage not in predecessors:
        raise ValueError('Unreviewed speed progression')
    predecessor = predecessors[stage]
    if stage in ('speed_2700rpm_6a_counter_return', 'speed_2700rpm_6a_counter_return_coast'):
        startup = json.loads((Path(folder)/'result.json').read_text(encoding='utf-8'))
        audit_speed_run(startup['prior_run_reference']['source'], baseline, 'speed_2200rpm_5a_counter')
    reference_baseline = (Path(folder)/'mcconf-before.bin').read_bytes() if Path(folder).is_dir() else baseline
    if reference_baseline != baseline:
        from .baseline_transition import adc_transition
        transition = adc_transition(reference_baseline, baseline)
        reference = audit_speed_run(folder, reference_baseline, predecessor)
        return dict(reference, baseline_transition=transition)
    return audit_speed_run(folder, baseline, predecessor)


def audit_speed_run(folder, baseline, predecessor):
    """Audit a completed acquisition without opening a hardware connection."""
    import hashlib
    previous_limits = stage_limits(predecessor)
    folder = Path(folder)
    prior = json.loads((folder/'result.json').read_text(encoding='utf-8'))
    if previous_limits.get('queued_logging') and (prior.get('queued_logging') is not True or prior.get('logs_drained') is not True):
        raise ValueError('Completed queued log drainage required')
    if previous_limits.get('memory_logging') and (prior.get('memory_logging') is not True or prior.get('logs_drained') is not True):
        raise ValueError('Completed memory log drainage required')
    if (prior['plan']['stage'] != predecessor
            or prior.get('status') != 'bounded_speed_increase_observed' or prior.get('errors')
            or any(prior.get(k) for k in ('full_event_travel_exceeded', 'coast_guard_exceeded', 'telemetry_guard_exceeded', 'battery_guard_exceeded'))
            or not all(prior.get(k) is True for k in ('ok', 'excitation_sent', 'motion_observed',
                        'zero_current_verified', 'baseline_restored', 'no_faults', 'app_isolated'))):
        raise ValueError(f'Next speed step requires a qualified {predecessor} trial')
    final = json.loads((folder/'final-readback.json').read_text(encoding='utf-8'))
    if (not all(final.get(k) is True for k in ('read_only', 'zero_current_verified', 'baseline_restored', 'app_isolated'))
            or final.get('excitation_sent') is not False
            or final['baseline_sha256'] != hashlib.sha256(baseline).hexdigest()
            or (folder/'mcconf-before.bin').read_bytes() != baseline):
        raise ValueError('Independent baseline restoration evidence required')
    verify_encoder_quiet(final['samples'])
    candidate = (folder/'mcconf-candidate.bin').read_bytes()
    _, expected = build_pilot(baseline, prior['plan']['changes']['foc_encoder_offset'],
                              prior['plan']['source_pose_deg'], predecessor)
    if candidate != expected or hashlib.sha256(candidate).hexdigest() != prior['plan']['candidate_sha256']:
        raise ValueError('Previous speed candidate differs from reviewed settings')
    source = encoder_policy(candidate, predecessor)
    rows = [json.loads(line) for line in (folder/'observations.jsonl').read_text(encoding='utf-8').splitlines()]
    if previous_limits.get('return_current_a'):
        samples = [json.loads(line) for line in (folder/'samples.jsonl').read_text(encoding='utf-8').splitlines()]
        audit_battery_return(samples)
    if previous_limits.get('counter_assisted'):
        if prior.get('measurement_method') != counter_method(previous_limits):
            raise ValueError('Counter measurement method missing')
        samples = [json.loads(line) for line in (folder/'samples.jsonl').read_text(encoding='utf-8').splitlines()]
        if previous_limits.get('native_counter'):
            verify_native_runtime(folder, dq=previous_limits.get('native_dq', False))
            if previous_limits.get('native_dq'):
                for row in samples:
                    validate_dq_record(row)
            clock_ref = load_clock_reference(prior['native_clock_reference']['path'], baseline, now=samples[0]['t'])
            if any(row.get(k) != clock_ref[v] for row in samples for k, v in (
                    ('native_tick_hz_lower', 'tick_hz_lower'), ('native_tick_hz_upper', 'tick_hz_upper'),
                    ('native_distance_scale', 'distance_scale'))):
                raise ValueError('Native run calibration does not match its source')
        coast_gap, coast_window = counter_timing(previous_limits, coast=True)
        replay_counter_run(samples, rows, previous_limits['maximum_rpm'],
                           coast_gap_s=coast_gap, coast_window_s=coast_window,
                           allow_coast_deferred=previous_limits.get('defer_coast_capture', False),
                           tracker_type=counter_type(previous_limits))
    if (len(rows) < 50 or not previous_limits['minimum_observation_s'] <= rows[-1]['elapsed_s'] < previous_limits['powered_s']
            or rows[-1]['travel_deg'] < previous_limits['finish_travel']
            or rows[-1]['encoder_rpm'] < previous_limits['minimum_finish_rpm']):
        raise ValueError('Previous speed-step raw completion evidence missing')
    for row in rows:
        validate_observation(row, row['command_a'], source,
                             settled_current=row['elapsed_s'] >= .6, stage=predecessor)
    if any(not 0 < b['t']-a['t'] <= previous_limits.get('telemetry_gap_s', .1)
           for a, b in zip(rows, rows[1:])):
        raise ValueError('Predecessor raw acquisition gaps failed')
    if 'stability_window_s' in previous_limits:
        tail = [(r['t'], r['encoder_rpm']) for r in rows
                if r['t'] >= rows[-1]['t']-previous_limits['stability_window_s']]
        if not speed_stability(tail, predecessor)['verified']:
            raise ValueError('Predecessor raw stability evidence failed')
        if prior.get('speed_stability', {}).get('verified') is not True:
            raise ValueError('Predecessor stability result missing')
    return dict(source=str(folder.resolve()), starting_pose_deg=final['samples'][-1]['position_deg'],
                interpretation='Qualified predecessor and independent standstill; only the explicitly reviewed next stage, not maximum-speed qualification')


def run_pilot(client, baseline, pose, output, *, clock=perf_counter, pause=sleep,
              stage='pilot', prior_run=None, stop_file=None, entry_readback=None, counter_evidence=None,
              entry_reader=None):
    require_free()
    limits = stage_limits(stage)
    battery_source = require_battery_source() if limits.get('return_current_a') else None
    if limits.get('counter_assisted') and (not isinstance(counter_evidence, dict)
            or counter_evidence.get('measurement_agreement_verified') is not True
            or counter_evidence.get('baseline_sha256') != hashlib.sha256(baseline).hexdigest()):
        raise ValueError('Counter measurement qualification required before actuation')
    reference_loader = rotation_reference if stage == 'rotation_3a' else extension_reference
    if stage == 'repeatability_3a':
        reference_loader = repeatability_reference
    elif stage == 'speed_90rpm_3a':
        reference_loader = speed_reference
    elif stage in SPEED_STAGES:
        reference_loader = lambda folder, data: higher_speed_reference(folder, data, stage)
    reference = reference_loader(prior_run, baseline) if stage != 'pilot' and prior_run else None
    if stage != 'pilot' and reference is None:
        raise ValueError('A prior physical pilot and independent readback are required')
    starting_pose = reference['starting_pose_deg'] if reference else pose['encoder_deg']
    plan, candidate = build_pilot(baseline, pose['offset_deg'] % 360, pose['encoder_deg'], stage)
    if pose['baseline_sha256'] != plan['baseline_sha256']:
        raise ValueError('Pose evidence does not match baseline')
    if entry_reader is not None:
        if entry_readback is not None:
            raise ValueError('Use either a supplied entry or a fresh entry reader')
        entry_readback = entry_reader()
    if stage in ('repeatability_3a',) + SPEED_STAGES:
        if (not isinstance(entry_readback, dict)
                or not all(entry_readback.get(k) is True for k in
                           ('read_only', 'baseline_restored', 'zero_current_verified', 'app_isolated'))
                or entry_readback.get('excitation_sent') is not False
                or entry_readback.get('baseline_sha256') != plan['baseline_sha256']):
            raise ValueError('Fresh independent entry readback required for each repeat')
        verify_encoder_quiet(entry_readback['samples'])
        last = entry_readback['samples'][-1]
        if not 0 <= clock()-last['t'] <= 1:
            raise ValueError('Repeat entry readback is stale')
        starting_pose = last['position_deg']
        if (stage == 'repeatability_3a'
                and min(abs(angular_delta(starting_pose, p)) for p in reference['tested_start_poses_deg']) < 10):
            raise ValueError('Fresh entry pose is too close to a previously tested start')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    if entry_readback is not None:
        (output/'entry-readback.json').write_text(json.dumps(entry_readback, indent=2, allow_nan=False), encoding='utf-8')
    def stop_requested():
        return (output/'STOP').exists() or (stop_file is not None and Path(stop_file).exists())
    report = dict(status='preflight', excitation_sent=False, zero_current_verified=False,
                  baseline_restored=False, offset_calibrated=False, motion_observed=False,
                  source_evidence_kind='configuration_inference_not_direct_telemetry',
                  errors=[], plan=plan, prior_run_reference=reference,
                  expected_start_pose_deg=starting_pose)
    report['capture_timing'] = CAPTURE_TIMING
    if pose.get('baseline_transition'):
        report['hfi_baseline_transition'] = pose['baseline_transition']
    if limits.get('native_counter'):
        report['native_counter'] = True
        report['native_clock_reference'] = client.native_clock_reference
        if hasattr(client, 'native_snapshot_runtime'):
            (output/'native-runtime-entry.json').write_text(
                json.dumps(client.native_snapshot_runtime, indent=2), encoding='utf-8')
    if limits.get('counter_assisted'):
        report['counter_qualification'] = counter_evidence
    if battery_source is not None:
        report['battery_source'] = battery_source
    if limits.get('queued_logging'):
        report['queued_logging'] = True
    if limits.get('memory_logging'):
        report['memory_logging'] = True
    if stage == 'repeatability_3a':
        report['repeatability_index'] = reference['repeatability_index']
    if stage in ('repeatability_3a',) + SPEED_STAGES:
        report['starting_pose_reference'] = dict(method='fresh_independent_entry_readback',
                                                 previous_quiet_deg=reference['starting_pose_deg'],
                                                 entry_deg=starting_pose,
                                                 change_from_prior_deg=angular_delta(starting_pose, reference['starting_pose_deg']))
    modified = False
    isolated = None
    rows = []
    motion_previous = None
    motion_previous_t = None
    motion_previous_latency = 0
    full_travel = 0.0
    counter = None
    counter_origin = 0.0
    battery_monitor = BatteryReturnMonitor() if battery_source is not None else None

    with open_trial_log(output/'samples.jsonl', limits.get('queued_logging', False), memory=limits.get('memory_logging', False)) as stream, \
         open_trial_log(output/'observations.jsonl', limits.get('queued_logging', False), memory=limits.get('memory_logging', False)) as observation_stream:
        def record(row):
            try:
                stream.write(json.dumps(row, allow_nan=False)+'\n')
                check_trial_log(stream)
            except OSError as exc:
                if not report.get('logging_failed'):
                    report['errors'].append(str(exc))
                report['logging_failed'] = True
                client.set_current(0)
                if row['stage'] not in ('stopping', 'final'):
                    raise

        def sample(stage):
            nonlocal motion_previous, motion_previous_t, motion_previous_latency, full_travel, counter
            row = capture_values(client, clock)
            if battery_monitor is not None:
                try:
                    row['returned_energy_j'] = battery_monitor.observe(row)
                    report['returned_energy_j'] = battery_monitor.energy_j
                except ValueError:
                    client.set_current(0)
                    report['battery_guard_exceeded'] = True
                    report['returned_energy_j'] = battery_monitor.energy_j
                    rows.append(dict(row, stage=stage))
                    record(rows[-1])
                    raise
            if counter is not None and stage in ('powered', 'stopping'):
                try:
                    if stage == 'stopping':
                        # quiet(retry=True) has sent zero before this read. Never resume torque.
                        counter.configure_timing(*counter_timing(limits, coast=True))
                    evidence = (counter.update_coast(row, allow_defer=limits.get('defer_coast_capture', False))
                                if stage == 'stopping' else counter.update(row))
                    if not evidence.get('counter_capture_deferred'):
                        guard_speed(evidence, limits['maximum_rpm'])
                    row.update(evidence)
                except ValueError as exc:
                    client.set_current(0)
                    report['telemetry_guard_exceeded'] = True
                    events = report.setdefault('counter_errors', [])
                    if len(events) < 20:
                        events.append(dict(stage=stage, t=row['t'], reason=str(exc)))
                    # Only the finally/recovery path can run after this exception.
                    # A fresh window may prove standstill, never repair the failed run.
                    counter = counter_type(limits)(limits['maximum_rpm'], limits['telemetry_gap_s'])
                    rows.append(dict(row, stage=stage))
                    record(rows[-1])
                    raise
            timing_failure = False
            if stage == 'powered' and motion_previous_t is not None:
                gap = row['t']-motion_previous_t
                limit = limits.get('telemetry_gap_s', .1)
                if not 0 < gap <= limit or not 0 <= row['latency_s'] <= limit:
                    client.set_current(0)
                    report['timing_abort'] = dict(response_gap_s=gap, latency_s=row['latency_s'],
                                                  limit_s=limit, zero_command_sent_at=clock())
                    timing_failure = True
            rows.append(dict(row, stage=stage))
            record(rows[-1])
            if timing_failure:
                raise ValueError('Control/telemetry gap exceeds stage limit; zero sent before logging')
            if any(not isinstance(v, (float, int)) or not math.isfinite(v) for v in row.values()):
                report['telemetry_guard_exceeded'] = True
                raise ValueError('Invalid telemetry')
            if (row['latency_s'] > .1 or not 0 <= row['position_deg'] < 360
                    or row['fault_code'] or not limits.get('minimum_voltage', 18) <= row['v_in'] <= limits.get('maximum_voltage', 30)
                    or row['temp_mos_c'] > 50):
                report['telemetry_guard_exceeded'] = True
                raise ValueError('Telemetry, fault, bus or temperature guard')
            if row.get('counter_capture_deferred'):
                report.setdefault('deferred_coast_captures', []).append(dict(t=row['t'], latency_s=row['latency_s']))
                return row
            if stage == 'before_current':
                motion_previous = row['position_deg']
                motion_previous_t = row['t']
                motion_previous_latency = row['latency_s']
            elif motion_previous is not None:
                step = row.get('counter_step_deg', angular_delta(row['position_deg'], motion_previous))
                gap = row['t']-motion_previous_t
                previous_latency = motion_previous_latency
                full_travel += step
                motion_previous = row['position_deg']
                motion_previous_t = row['t']
                motion_previous_latency = row['latency_s']
                report['full_event_travel_deg'] = full_travel
                report['full_event_peak_abs_travel_deg'] = max(abs(full_travel), report.get('full_event_peak_abs_travel_deg', 0))
                if abs(full_travel) >= limits.get('full_travel', limits['travel']):
                    report['full_event_travel_exceeded'] = True
                if report['plan']['stage'] in ROTATION_STAGES and stage == 'stopping':
                    coast_gap, _ = counter_timing(limits, coast=True)
                    if (gap <= 0 or gap > coast_gap
                            or row['latency_s'] > coast_gap
                            or (not limits.get('counter_assisted')
                                and abs(step/gap/6) >= limits.get('maximum_rpm', 60))):
                        report['coast_guard_exceeded'] = True
                        events = report.setdefault('coast_timing_events', [])
                        if len(events) < 20:
                            evidence = adjacent_speed_evidence(step, gap, previous_latency, row['latency_s']) if gap > 0 else dict(response_gap_s=gap)
                            events.append(dict(t=row['t'], **evidence))
                    if (math.hypot(row['id_a'], row['iq_a']) > limits['observed_current']
                            or abs(row['current_motor_a']) > limits['observed_current']):
                        report['coast_guard_exceeded'] = True
            return row

        def quiet(seconds=.5, retry=False):
            tail = []
            deadline = clock()+seconds
            last_error = None
            while clock() < deadline:
                try:
                    client.set_current(0)
                    row = sample('stopping' if retry else 'quiet')
                    if row.get('counter_capture_deferred'):
                        tail = []
                        pause(limits.get('coast_sample_interval_s', .002))
                        continue
                except Exception as exc:
                    last_error = exc
                    tail = []
                    if not retry:
                        raise
                else:
                    tail.append(row)
                    tail = [r for r in tail if r['t'] >= row['t']-.45]
                    try:
                        verify_encoder_quiet(tail)
                    except FixtureInterlock as exc:
                        last_error = exc
                    else:
                        if retry:
                            return
                pause_s = limits.get('coast_sample_interval_s', limits.get('sample_interval_s', .02)) if retry else limits.get('sample_interval_s', .02)
                if pause_s > 0:
                    pause(pause_s)
            if not tail or clock()-tail[-1]['t'] > .1:
                raise ValueError(f'No fresh quiet telemetry: {last_error}')
            verify_encoder_quiet(tail)

        try:
            fw = asdict(client.fw_version())
            actual, app = client.get_raw_config('motor'), client.get_raw_config('app')
            if actual != baseline:
                report['fresh_adc_changes'] = fresh_adc_changes(baseline, actual)
                report['source_hfi_baseline_sha256'] = pose['baseline_sha256']
                (output/'mcconf-evidence-reference.bin').write_bytes(baseline)
                baseline = actual
                plan, candidate = build_pilot(baseline, pose['offset_deg'] % 360, pose['encoder_deg'], stage)
                report['plan'] = plan
            isolated = patch_config(app, 'app', dict(app_to_use=0, timeout_msec=300, timeout_brake_current=0))
            preflight_config(fw, baseline, isolated)
            (output/'mcconf-before.bin').write_bytes(baseline)
            (output/'appconf-before.bin').write_bytes(app)
            (output/'mcconf-candidate.bin').write_bytes(candidate)
            quiet()
            client.set_app_config_temporary(isolated)
            if client.get_raw_config('app') != isolated:
                raise ValueError('Application isolation readback mismatch')
            report['app_isolated'] = True
            report['encoder_diagnostics'] = check_encoder(client)
            quiet(seconds=8)
            if abs(angular_delta(rows[-1]['position_deg'], starting_pose)) > .5:
                raise ValueError('Rotor moved outside the reviewed starting-pose window')
            if stop_requested():
                raise ValueError('STOP requested before configuration write')
            modified = True
            readback = write_motor_verified(client, candidate)
            report['source_evidence'] = encoder_policy(readback, stage)
            quiet(seconds=1)
            if client.get_raw_config('motor') != candidate or client.get_raw_config('app') != isolated:
                raise ValueError('Configuration changed before excitation')
            if abs(angular_delta(rows[-1]['position_deg'], starting_pose)) > .5:
                raise ValueError('Starting pose changed during preparation')
            if stage in ROTATION_STAGES:
                quiet(seconds=.4)
            previous = sample('before_current')
            if abs(angular_delta(previous['position_deg'], starting_pose)) > .5:
                raise ValueError('Starting pose changed during speed-window preparation')
            if (stage == 'repeatability_3a'
                    and min(abs(angular_delta(previous['position_deg'], p))
                            for p in reference['tested_start_poses_deg']) < 10):
                raise ValueError('Actual starting angle is too close to a previously tested start')
            start = clock()
            history = deque([(previous['t'], 0.0)])
            if stage in ROTATION_STAGES:
                seed = [r for r in rows if r['t'] >= previous['t']-.12]
                gap_limit = limits.get('telemetry_gap_s', .1)
                if (len(seed) < 2 or seed[-1]['t']-seed[0]['t'] < .1
                        or any(not 0 < b['t']-a['t'] <= gap_limit for a, b in zip(seed, seed[1:]))
                        or any(r['latency_s'] > gap_limit or abs(r['current_motor_a']) > .1
                               or math.hypot(r['id_a'], r['iq_a']) > .2 or abs(r['duty']) > .001
                               or abs(angular_delta(r['position_deg'], previous['position_deg'])) > .5 for r in seed)):
                    raise ValueError('Fresh quiet speed-estimation window required before excitation')
                # A sub-ms first difference magnifies idle encoder quantization/noise.
                history = deque((r['t'], angular_delta(r['position_deg'], previous['position_deg'])) for r in seed)
                report['initial_speed_window_s'] = seed[-1]['t']-seed[0]['t']
                if limits.get('counter_assisted'):
                    counter = counter_type(limits)(limits['maximum_rpm'], limits['telemetry_gap_s'])
                    for seed_row in seed:
                        guard_speed(counter.update(seed_row), limits['maximum_rpm'])
                    counter_origin = counter.travel
                    report['measurement_method'] = counter_method(limits)
            speed_tail = deque()
            travel = energy = i2t = current_ok_s = 0.0
            command = rpm = 0.0
            last_command_t = start
            report['status'] = 'no_verified_motion'
            # Leave margin for one <=100 ms RPC before the stage duration budget.
            while clock()-start < limits.get('powered_s', 4)-.2:
                require_free()
                if stop_requested():
                    raise ValueError('STOP requested')
                elapsed = clock()-start
                if stage in ROTATION_STAGES:
                    now = clock()
                    report['last_supervisor_input'] = dict(previous_command_a=command, encoder_rpm=rpm,
                                                           command_interval_s=now-last_command_t,
                                                           sample_age_s=now-previous['t'], elapsed_s=now-start)
                    if now-previous['t'] > limits.get('telemetry_gap_s', .1):
                        raise ValueError('Stale encoder before current command')
                    if limits.get('latch_speed_cutoff') and rpm >= limits['cutoff_rpm']:
                        raise ValueError('Speed cutoff reached; end trial and verify zero current')
                    command = rotation_current(command, rpm, now-last_command_t, now-start, stage)
                    last_command_t = clock()
                else:
                    command = min(limits['current'], limits['current']*elapsed)
                client.set_current(command)
                report['excitation_sent'] |= command > 0
                if limits.get('sample_interval_s', .02) > 0:
                    pause(limits.get('sample_interval_s', .02))
                row = sample('powered')
                dt = row['t']-previous['t']
                if not 0 < dt <= limits.get('telemetry_gap_s', .1):
                    raise ValueError('Control/telemetry gap exceeds stage limit')
                travel += row.get('counter_step_deg', angular_delta(row['position_deg'], previous['position_deg']))
                history.append((row['t'], travel))
                while history[0][0] < row['t']-.12:
                    history.popleft()
                rpm = (travel-history[0][1])/(row['t']-history[0][0])/6 if len(history) > 1 else 0
                if counter is not None:
                    travel = row['counter_travel_deg'] - counter_origin
                    rpm = row['counter_rpm']
                if 'stability_window_s' in limits:
                    speed_tail.append((row['t'], rpm))
                    while speed_tail[0][0] < row['t']-limits['stability_window_s']:
                        speed_tail.popleft()
                energy += max(0, row['current_in_a']*row['v_in'])*dt
                i2t += (row['id_a']**2+row['iq_a']**2)*dt
                observation = dict(row, encoder_rpm=rpm, encoder_age_s=0, travel_deg=travel,
                                   elapsed_s=clock()-start, input_energy_j=energy, i2t_a2s=i2t)
                observation_stream.write(json.dumps(dict(observation, command_a=command), allow_nan=False)+'\n')
                check_trial_log(observation_stream)
                report.update(travel_deg=travel, powered_s=clock()-start,
                              input_energy_j=energy, i2t_a2s=i2t,
                              last_powered_observation=dict(observation, command_a=command),
                              encoder_displacement_detected=abs(travel) >= 3)
                validate_observation(observation, command, report['source_evidence'],
                                     settled_current=elapsed >= .5, stage=stage)
                current_ok_s = current_ok_s+dt if elapsed >= .5 else 0
                if (stage not in ROTATION_STAGES and current_ok_s >= .15
                        and travel >= limits['finish_travel'] and elapsed >= limits['minimum_observation_s']):
                    report.update(status='local_motion_and_current_observed', motion_observed=True)
                    break
                previous = row
            if stage in ROTATION_STAGES:
                minimum_rpm = limits.get('minimum_finish_rpm', 5)
                stability_ok = True
                if 'stability_window_s' in limits:
                    report['speed_stability'] = speed_stability(list(speed_tail), stage)
                    stability_ok = report['speed_stability']['verified']
                if current_ok_s >= limits.get('powered_s', 4)-1 and travel >= limits['finish_travel'] and rpm >= minimum_rpm and stability_ok:
                    report.update(status='bounded_speed_increase_observed' if stage in SPEED_STAGES else 'bounded_rotation_observed', motion_observed=True)
                else:
                    report['status'] = 'rotation_criterion_not_met'
            elif stage != 'pilot' and current_ok_s >= .15 and travel >= 3 and report['status'] != 'aborted':
                report.update(status='extended_current_motion_observed', motion_observed=True)
        except (Exception, KeyboardInterrupt) as exc:
            report['status'] = 'aborted'
            report['errors'].append(str(exc) or type(exc).__name__)
        finally:
            try:
                quiet(seconds=limits.get('recovery_s', 8), retry=True)
                report['zero_current_verified'] = True
                if modified:
                    write_motor_verified(client, baseline)
                report['baseline_restored'] = client.get_raw_config('motor') == baseline
                report['app_isolated'] = isolated is not None and client.get_raw_config('app') == isolated
                if not report['baseline_restored']:
                    raise ValueError('Baseline not restored')
                sample('final')
                if report.get('full_event_travel_deg') is not None:
                    report['coast_travel_deg'] = report['full_event_travel_deg']-report.get('travel_deg', 0)
            except (Exception, KeyboardInterrupt) as exc:
                report['status'] = 'recovery_required'
                report['errors'].append(f'Recovery: {exc}')
            finally:
                try:
                    client.set_current(0)
                except Exception as exc:
                    report['errors'].append(f'Final stop: {exc}')
                for log in (stream, observation_stream):
                    try:
                        log.close()
                    except OSError as exc:
                        report['errors'].append(f'Log drain: {exc}')
                if limits.get('queued_logging') or limits.get('memory_logging'):
                    report['logs_drained'] = not report['errors']
                report['no_faults'] = bool(rows) and all(r['fault_code'] == 0 for r in rows)
                report['ok'] = bool(report['motion_observed'] and not report['errors']
                                    and report['zero_current_verified'] and report['baseline_restored']
                                    and report['app_isolated'] and report['no_faults']
                                    and not report.get('full_event_travel_exceeded')
                                    and not report.get('coast_guard_exceeded')
                                    and not report.get('battery_guard_exceeded')
                                    and not report.get('telemetry_guard_exceeded'))
                if report.get('coast_guard_exceeded') and report['status'] != 'recovery_required':
                    report['status'] = 'coast_guard_exceeded'
                if report.get('full_event_travel_exceeded') and report['status'] != 'recovery_required':
                    report['status'] = 'travel_envelope_exceeded'
                with (output/'result.json').open('x', encoding='utf-8') as f:
                    json.dump(report, f, indent=2, allow_nan=False)
    return report
