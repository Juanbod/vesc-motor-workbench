"""Bounded stator-field alignment; never writes a candidate encoder offset."""
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import statistics
from time import perf_counter as monotonic, sleep

from .fixture import PROBE_LIMITS, FixtureInterlock, require_free, verify_encoder_quiet
from .hfi_capture import terminal_expect, write_motor_verified
from .locked_probe import preflight_config
from .locked_rotor import _axial_mean, axial_delta, angular_delta
from .wire_config import decode_config, patch_config


LIMITS = {**PROBE_LIMITS, 'l_slow_abs_current': 0, 'foc_f_zv': 30000,
          'foc_mtpa_mode': 0, 'foc_fw_current_max': 0,
          'foc_cc_decoupling': 0}
DWELL_S = .8
COOLDOWN_S = 2.0


def plan(mode='pilot', current=.5, start_phase=150, dwell_s=DWELL_S):
    if mode not in ('pilot', 'sweep') or current not in (.5, 1., 2.):
        raise ValueError('Only pilot/sweep and reviewed 0.5, 1, 2 A levels are allowed')
    if not math.isfinite(start_phase) or not 0 <= start_phase < 360:
        raise ValueError('Invalid stator field angle')
    if dwell_s not in (.8, 2., 4.):
        raise ValueError('Only bounded 0.8, 2 or 4 second holds are reviewed')
    angles = [(start_phase + i * 30) % 360 for i in range(13)]
    steps = ([dict(phase_deg=start_phase, direction='pilot')] if mode == 'pilot' else
             [dict(phase_deg=a, direction=d) for d, seq in
              [('forward', angles), ('reverse', angles[::-1])] for a in seq])
    return dict(schema='stator-alignment-v1', mode=mode, current_a=current,
                dwell_s=dwell_s, cooldown_s=COOLDOWN_S, limits=LIMITS.copy(),
                steps=steps, commanded_on_time_s=len(steps)*dwell_s,
                requires_free_fixture=True, offset_auto_apply=False,
                source_commit='f7c2b34e1cff2234cae98be3abf0cd50e249558f')


def circular_mean(angles):
    if not angles or any(not math.isfinite(a) for a in angles):
        raise ValueError('No valid encoder angles')
    x = statistics.mean(math.cos(math.radians(a)) for a in angles)
    y = statistics.mean(math.sin(math.radians(a)) for a in angles)
    if math.hypot(x, y) < .9:
        raise ValueError('Encoder positions are too dispersed')
    return math.degrees(math.atan2(y, x)) % 360


def check_motion(row, previous=None, origin=None):
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in row.values()):
        raise ValueError('Unavailable/nonfinite telemetry')
    if not 0 <= row['position_deg'] < 360:
        raise ValueError('Invalid encoder position')
    if row['fault_code'] or not 18 <= row['v_in'] <= 30 or row['temp_mos_c'] > 50:
        raise ValueError('Fault, supply or MOS temperature guard')
    if (max(abs(row['current_motor_a']), math.hypot(row['id_a'], row['iq_a'])) > 2.5
            or abs(row['current_in_a']) > 1.2 or abs(row['duty']) > .1):
        raise ValueError('Current/duty guard')
    if origin is not None and abs(angular_delta(row['position_deg'], origin)) > 60:
        raise ValueError('Travel exceeds 60 mechanical degrees in one step')
    if previous is not None:
        dt = row['t'] - previous['t']
        if not 0 < dt <= .1:
            raise ValueError('Telemetry gap exceeds 100 ms')
        if abs(angular_delta(row['position_deg'], previous['position_deg'])) / dt / 6 > 60:
            raise ValueError('Encoder speed exceeds 60 mechanical RPM')


def settled_position(rows, current):
    if len(rows) < 10 or rows[-1]['t'] - rows[0]['t'] < .25:
        raise ValueError('Insufficient powered settling data')
    for i, row in enumerate(rows):
        check_motion(row, rows[i-1] if i else None)
        # In the audited command Id follows the stator vector, Iq target is zero.
        if not .65*current <= row['id_a'] <= 1.35*current or abs(row['iq_a']) > max(.15, .2*current):
            raise ValueError('Applied current vector not established')
    angles = [angular_delta(r['position_deg'], rows[0]['position_deg']) for r in rows]
    if max(angles)-min(angles) > .5 or abs(angles[-1]-angles[0]) > .2:
        raise ValueError('Rotor did not settle under the field')
    return circular_mean([r['position_deg'] for r in rows])


def analyze(steps, spec, ratio=2, inverted=False):
    """Max-L equilibrium becomes min-L axis by +90 electrical degrees, mod 180."""
    if len(steps) != len(spec['steps']):
        raise ValueError('Incomplete alignment sequence')
    if any(not s.get('settled') or not s.get('completed') for s in steps):
        raise ValueError('Unqualified alignment step')
    if any(s['phase_deg'] != p['phase_deg'] or s['direction'] != p['direction']
           for s, p in zip(steps, spec['steps'])):
        raise ValueError('Sequence does not match plan')
    result = dict(candidate=None, applied=False, global_calibration_validated=False)
    if spec['mode'] == 'pilot':
        result['status'] = 'pilot_only'
        return result
    forward = [s for s in steps if s['direction'] == 'forward']
    reverse = [s for s in steps if s['direction'] == 'reverse'][::-1]
    sign = -1 if inverted else 1
    for branch, direction in ((forward, 1), (reverse[::-1], -1)):
        for a, b in zip(branch, branch[1:]):
            actual = angular_delta(b['encoder_deg'], a['encoder_deg']) * sign * ratio
            if abs(actual - direction*30) > 5:
                raise ValueError('Rotor did not track successive field steps')
    hysteresis = max(abs(axial_delta(sign*ratio*a['encoder_deg'], sign*ratio*b['encoder_deg']))
                     for a, b in zip(forward, reverse))
    offsets = [(sign*ratio*s['encoder_deg'] - (s['phase_deg']+90)) % 180 for s in steps]
    offset, concentration = _axial_mean(offsets)
    residuals = [axial_delta(o, offset) for o in offsets]
    worst = max(map(abs, residuals))
    result.update(status='systematic_error_or_hysteresis', hysteresis_electrical_deg=hysteresis,
                  max_residual_deg=worst, concentration=concentration,
                  per_step_offset_mod180_deg=offsets, residuals_deg=residuals,
                  assumptions=dict(ratio=ratio, inverted=inverted, aligned_axis='maximum_L',
                                   target_d_axis='minimum_L', axis_shift_electrical_deg=90))
    if hysteresis <= 3 and worst <= 3 and concentration >= .99:
        result.update(status='candidate_requires_independent_validation',
                      candidate=dict(offset_candidates_deg=[offset, offset+180]))
    return result


def validate_pilot(pilot, spec, baseline_hash):
    if (not pilot.get('ok') or not pilot.get('physical_motion_verified')
            or not pilot.get('baseline_restored') or not pilot.get('zero_current_verified')
            or not pilot.get('app_isolated') or not pilot.get('no_faults')
            or pilot.get('baseline_sha256') != baseline_hash):
        raise ValueError('A successful physical pilot on this baseline is required')
    p = pilot['plan']
    if (p != plan('pilot', spec['current_a'], spec['steps'][0]['phase_deg'], spec['dwell_s'])
            or len(pilot['steps']) != 1 or not pilot['steps'][0].get('settled')
            or not pilot['steps'][0].get('completed')):
        raise ValueError('Pilot parameters differ from the requested sweep')


def run(client, output, required_baseline, spec, pilot=None):
    require_free()
    if spec != plan(spec['mode'], spec['current_a'], spec['steps'][0]['phase_deg'], spec['dwell_s']):
        raise ValueError('Plan is not the reviewed bounded schedule')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(plan=spec, simulated=False, ok=False, steps=[], errors=[],
                  baseline_restored=False, zero_current_verified=False,
                  app_isolated=False, physical_motion_verified=False, offset_applied=False)
    samples = []
    original = isolated = None
    write_attempted = False
    outstanding_until = 0
    with (output/'samples.jsonl').open('x', encoding='utf-8') as log:
        def sample(stage, previous=None, origin=None, enforce=True):
            before = monotonic()
            row = dict(asdict(client.get_values()), position_deg=client.pid_position, t=monotonic())
            log.write(json.dumps(dict(row, stage=stage, latency_s=monotonic()-before), allow_nan=False)+'\n')
            log.flush()
            samples.append(row)
            if enforce:
                if monotonic()-before > .1:
                    raise ValueError('Telemetry latency exceeds 100 ms')
                check_motion(row, previous, origin)
            return row

        def stop_and_verify(seconds):
            rows = []
            not_before = max(monotonic()+seconds, outstanding_until+.5)
            until = not_before + 6
            while monotonic() < until:
                try:
                    client.set_current(0)
                    rows.append(sample('stopping', enforce=False))
                except (Exception, KeyboardInterrupt) as exc:
                    report['errors'].append('stop/read: '+str(exc))
                    rows = []
                if rows and monotonic() >= not_before:
                    tail = [r for r in rows if r['t'] >= rows[-1]['t']-.4]
                    try:
                        verify_encoder_quiet(tail)
                    except FixtureInterlock:
                        pass
                    else:
                        check_motion(tail[-1])
                        return tail
                sleep(.015)
            raise ValueError('No standstill confirmation within coast-down budget; keep protective limits')

        try:
            fw = asdict(client.fw_version())
            original, app = client.get_raw_config('motor'), client.get_raw_config('app')
            if original != Path(required_baseline).read_bytes():
                raise ValueError('Fresh reviewed baseline required')
            report['baseline_sha256'] = hashlib.sha256(original).hexdigest()
            (output/'mcconf-before.bin').write_bytes(original)
            (output/'appconf-before.bin').write_bytes(app)
            isolated = patch_config(app, 'app', dict(app_to_use=0, timeout_msec=300, timeout_brake_current=0))
            motor, _ = preflight_config(fw, original, isolated)
            if motor['foc_encoder_ratio'] != 2 or motor['foc_encoder_inverted'] != 0:
                raise ValueError('Reviewed ratio=2/noninverted required')
            if (motor['l_current_max'] < 2 or motor['l_abs_current_max'] < 3
                    or motor['l_current_max_scale'] != 1 or motor['l_current_min_scale'] != 1):
                raise ValueError('Unexpected current limits/scales')
            if spec['mode'] == 'sweep':
                validate_pilot(pilot or {}, spec, report['baseline_sha256'])
            stop_and_verify(.5)
            client.set_app_config_temporary(isolated)
            if client.get_raw_config('app') != isolated:
                raise ValueError('App isolation readback mismatch')
            report['app_isolated'] = True
            limited = patch_config(original, 'motor', LIMITS)
            (output/'mcconf-limited.bin').write_bytes(limited)
            write_attempted = True
            write_motor_verified(client, limited)
            stop_and_verify(.5)
            terminal_expect(client, 'rotor_lock_openloop',
                            'This command requires three arguments. [current time angle]')
            for index, item in enumerate(spec['steps']):
                require_free()
                if (output/'STOP').exists():
                    raise ValueError('STOP requested')
                if client.get_raw_config('motor') != limited or client.get_raw_config('app') != isolated:
                    raise ValueError('Configuration changed between steps')
                initial = sample('before_step')
                command = f"rotor_lock_openloop {spec['current_a']:.3f} {spec['dwell_s']:.3f} {item['phase_deg']:.3f}"
                dispatched = monotonic()
                # The stock timed loop resets its own watchdog. Host stop is not
                # guaranteed to cancel it; cover the bounded command tail.
                outstanding_until = dispatched + spec['dwell_s'] + .5
                step = dict(item, index=index, dispatch_t=dispatched, command=command,
                            settled=False, completed=False, max_powered_displacement_deg=0)
                report['steps'].append(step)
                with (output/f'dispatch-{index:02d}.json').open('x', encoding='utf-8') as f:
                    json.dump(step, f)
                client.send_payload(b'\x14'+command.encode('ascii'))
                powered = []
                previous = initial
                complete = None
                until = monotonic()+spec['dwell_s']+.5
                while monotonic() < until:
                    require_free()
                    if (output/'STOP').exists():
                        raise ValueError('STOP during alignment')
                    row = sample('powered', previous, initial['position_deg'])
                    previous = row
                    displacement = abs(angular_delta(row['position_deg'], initial['position_deg']))
                    step['max_powered_displacement_deg'] = max(step['max_powered_displacement_deg'], displacement)
                    step['last_powered_encoder_deg'] = row['position_deg']
                    # Motion evidence is independent of successful settling.
                    # A moving/unsettled pilot must still fail sweep authorization.
                    report['physical_motion_verified'] |= displacement >= 1
                    messages = [p for p in client.prints if p['t'] >= dispatched]
                    if any('Fault' in p['text'] or 'Invalid' in p['text'] for p in messages):
                        raise ValueError('Firmware rejected/faulted alignment')
                    complete = next((p for p in messages if p['text'] == 'Done'), None)
                    if complete:
                        break
                    powered.append(row)
                    sleep(.01)
                if not complete:
                    raise ValueError('No timed-command completion')
                step['completed'] = True
                window = .8 if spec['dwell_s'] >= 2 else .32
                tail = [r for r in powered if complete['t']-(window+.03) <= r['t'] <= complete['t']-.03]
                if not tail or tail[-1]['t']-tail[0]['t'] < window-.07:
                    raise ValueError('Insufficient final powered observation window')
                step['encoder_deg'] = settled_position(tail, spec['current_a'])
                step['settled'] = True
                step['travel_deg'] = angular_delta(step['encoder_deg'], initial['position_deg'])
                report['physical_motion_verified'] |= abs(step['travel_deg']) >= 1
                if spec['mode'] == 'sweep' and index:
                    prior = report['steps'][index-1]
                    expected = angular_delta(step['phase_deg'], prior['phase_deg'])
                    actual = motor['foc_encoder_ratio'] * angular_delta(step['encoder_deg'], prior['encoder_deg'])
                    step['tracking_error_electrical_deg'] = actual-expected
                    if abs(actual-expected) > 5:
                        raise ValueError('Rotor did not track field step; no further steps permitted')
                stop_and_verify(COOLDOWN_S)
            if not report['physical_motion_verified']:
                raise ValueError('No physical movement verified; not an alignment calibration')
            report['analysis'] = analyze(report['steps'], spec)
        except (Exception, KeyboardInterrupt) as exc:
            report['errors'].append(str(exc) or type(exc).__name__)
        finally:
            try:
                stop_and_verify(1.)
                report['zero_current_verified'] = True
                # Do not restore high motor limits if external control changed.
                actual_app = client.get_raw_config('app')
                if write_attempted and actual_app != isolated:
                    raise ValueError('App changed; leave protective motor limits in place')
                if write_attempted:
                    write_motor_verified(client, original)
                report['baseline_restored'] = original is not None and client.get_raw_config('motor') == original
                if isolated is not None:
                    report['app_isolated'] = actual_app == isolated
            except (Exception, KeyboardInterrupt) as exc:
                report['errors'].append('cleanup: '+str(exc))
                try:
                    client.set_current(0)
                except Exception as stop_exc:
                    report['errors'].append('final stop: '+str(stop_exc))
            report['no_faults'] = bool(samples) and all(r['fault_code'] == 0 for r in samples)
            report['terminal_output'] = client.prints
            report['ok'] = bool(not report['errors'] and report['baseline_restored']
                                and report['zero_current_verified'] and report['app_isolated']
                                and report['no_faults'] and report.get('analysis'))
            (output/'result.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report
