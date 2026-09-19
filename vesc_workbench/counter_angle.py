"""Counter-assisted encoder acquisition, not an independent shaft tachometer.

Reference VESC 6.02 counts six corrected FOC sectors per electrical turn.
Only the reviewed ratio=2, non-inverted encoder configuration is supported.
Each response is conservatively bracketed by its complete request latency.
"""
from collections import deque
import math


def signed_delta(new, old):
    if any(type(v) is not int or not -(2**31) <= v < 2**31 for v in (new, old)):
        raise ValueError('Invalid signed 32-bit sector counter')
    return (new - old + 2**31) % 2**32 - 2**31


class CounterCaptureAmbiguous(ValueError):
    pass


class CounterAngle:
    def __init__(self, maximum_rpm, gap_s=.025, window_s=.25):
        if not all(math.isfinite(v) and v > 0 for v in (maximum_rpm, gap_s, window_s)) or window_s < 4*gap_s:
            raise ValueError('Invalid counter acquisition limits')
        self.maximum_rpm = maximum_rpm
        self.gap_s = gap_s
        self.window_s = window_s
        self.previous = None
        self.travel = 0.0
        self.counter_steps = 0
        self.anchor_latency = None
        self.history = deque()
        self.deferred_coast_samples = 0

    def configure_timing(self, gap_s, window_s):
        """Keep accumulated turns when changing to a zero-current coast window."""
        if not all(math.isfinite(v) and v > 0 for v in (gap_s, window_s)) or window_s < 4*gap_s:
            raise ValueError('Invalid counter acquisition limits')
        self.gap_s, self.window_s = gap_s, window_s

    def update_coast(self, row, *, allow_defer=False):
        """Defer at most one ambiguous zero-current capture; keep the last good anchor."""
        try:
            return self.update(row)
        except CounterCaptureAmbiguous:
            keys = ('current_motor_a', 'id_a', 'iq_a', 'duty', 'fault_code')
            if (not allow_defer or self.deferred_coast_samples or self.previous is None
                    or any(not isinstance(row.get(k), (int, float)) or not math.isfinite(row[k]) for k in keys)
                    or row['fault_code'] != 0 or abs(row['current_motor_a']) > .1
                    or math.hypot(row['id_a'], row['iq_a']) > .2 or abs(row['duty']) > .001):
                raise
            dc = signed_delta(row['tachometer'], self.previous['tachometer'])
            da = signed_delta(row['tachometer_abs'], self.previous['tachometer_abs'])
            duration = row['t']-self.previous['t']+self.previous['latency_s']
            if da < 0 or da+2 < abs(dc) or 30*abs(dc) > 6*self.maximum_rpm*duration+30.2:
                raise ValueError('Deferred capture counter is inconsistent')
            self.deferred_coast_samples += 1
            return dict(counter_capture_deferred=True)

    def update(self, row):
        for key in ('t', 'latency_s', 'position_deg'):
            if not isinstance(row.get(key), (int, float)) or not math.isfinite(row[key]):
                raise ValueError('Missing or nonfinite counter acquisition data')
        if not 0 <= row['position_deg'] < 360 or not 0 <= row['latency_s'] <= self.gap_s:
            raise ValueError('Counter angle or latency outside bounds')
        for key in ('tachometer', 'tachometer_abs'):
            signed_delta(row.get(key), row.get(key))
        step = 0.0
        count_total = self.counter_steps
        if self.previous is not None:
            old = self.previous
            gap = row['t'] - old['t']
            if not 0 < gap <= self.gap_s:
                raise ValueError('Counter telemetry gap exceeds bound')
            dc = signed_delta(row['tachometer'], old['tachometer'])
            count_total += dc
            da = signed_delta(row['tachometer_abs'], old['tachometer_abs'])
            # Counter fields and position are sequential, not an atomic snapshot.
            tolerance = 30.2 + 6*self.maximum_rpm*(old['latency_s'] + row['latency_s'])
            if tolerance >= 180:
                raise CounterCaptureAmbiguous('Counter/angle wrap is temporally ambiguous')
            raw_step = row['position_deg'] - old['position_deg']
            step = raw_step + 360*round((30*dc - raw_step)/360)
            if abs(step - 30*dc) > tolerance:
                raise ValueError('Sector counter disagrees with encoder angle')
            # Boundary chatter can increase the absolute count even at rest.
            if da < 0 or da + 2 < abs(dc):
                raise ValueError('Absolute sector counter disagrees with signed counter')
            if abs(step) > 6*self.maximum_rpm*(gap + old['latency_s']) + .2:
                raise ValueError('Counter step implies overspeed or counter reset')
        travel = self.travel + step
        anchor_latency = row['latency_s'] if self.anchor_latency is None else self.anchor_latency
        global_tolerance = 30.2 + 6*self.maximum_rpm*(anchor_latency + row['latency_s'])
        if global_tolerance >= 180:
            raise CounterCaptureAmbiguous('Counter anchor/angle wrap is temporally ambiguous')
        if abs(30*count_total - travel) > global_tolerance:
            raise ValueError('Cumulative sector counter disagrees with encoder travel')
        self.history.append((row['t'], row['latency_s'], travel))
        while len(self.history) > 2 and self.history[1][0] < row['t'] - self.window_s:
            self.history.popleft()
        first_t, first_latency, first_travel = self.history[0]
        elapsed = row['t'] - first_t
        rpm = lower = upper = 0.0
        if elapsed >= .09:
            shortest = elapsed - row['latency_s']
            longest = elapsed + first_latency
            if shortest <= 0:
                raise ValueError('Overlapping speed measurement intervals')
            distance = travel - first_travel
            bounds = [(distance + error)/duration/6
                      for error in (-.2, .2) for duration in (shortest, longest)]
            lower, upper = min(bounds), max(bounds)
            rpm = distance / ((shortest + longest)/2) / 6
        self.previous = dict(row)
        self.travel = travel
        self.counter_steps = count_total
        self.anchor_latency = anchor_latency
        return dict(counter_step_deg=step, counter_travel_deg=travel,
                    counter_rpm=rpm, counter_rpm_lower=lower,
                    counter_rpm_upper=upper, counter_window_s=elapsed)


def guard_speed(evidence, maximum_rpm):
    if evidence['counter_rpm_lower'] < -5 or evidence['counter_rpm_upper'] >= maximum_rpm:
        raise ValueError('Counter speed uncertainty reaches direction or speed bound')


def audit_counter_reference(folder, baseline):
    """Qualify measurement agreement only; never reclassify a failed speed trial."""
    import hashlib
    import json
    from pathlib import Path
    from .fixture import verify_encoder_quiet
    from .synrm_pilot import build_pilot, encoder_policy

    folder = Path(folder)
    report = json.loads((folder/'result.json').read_text(encoding='utf-8'))
    final = json.loads((folder/'final-readback.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256(baseline).hexdigest()
    if (report['plan']['stage'] != 'speed_2200rpm_5a_hold'
            or report.get('errors') or report.get('telemetry_guard_exceeded')
            or not all(report.get(k) is True for k in ('excitation_sent', 'zero_current_verified',
                         'baseline_restored', 'no_faults', 'app_isolated'))
            or final.get('baseline_sha256') != digest
            or final.get('excitation_sent') is not False
            or not all(final.get(k) is True for k in ('read_only', 'zero_current_verified',
                         'baseline_restored', 'app_isolated'))
            or (folder/'mcconf-before.bin').read_bytes() != baseline):
        raise ValueError('Recovered, fault-free reference acquisition required')
    verify_encoder_quiet(final['samples'])
    _, expected = build_pilot(baseline, report['plan']['changes']['foc_encoder_offset'],
                             report['plan']['source_pose_deg'], 'speed_2200rpm_5a_hold')
    if expected != (folder/'mcconf-candidate.bin').read_bytes():
        raise ValueError('Counter reference candidate mismatch')
    encoder_policy(expected, 'speed_2200rpm_5a_hold')
    tracker = CounterAngle(2420)
    rows = []
    started = False
    travel_by_stage = dict(powered=0.0, stopping=0.0)
    previous = None
    with (folder/'samples.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['stage'] == 'before_current':
                if started:
                    raise ValueError('Multiple reference starts')
                started = True
            if not started or row['stage'] == 'final':
                continue
            if row['stage'] not in ('before_current', 'powered', 'stopping') or row['fault_code']:
                raise ValueError('Invalid counter reference stage or fault')
            evidence = tracker.update(row)
            guard_speed(evidence, 2420)
            if previous is not None:
                raw_step = (row['position_deg'] - previous['position_deg'] + 180) % 360 - 180
                if abs(raw_step - evidence['counter_step_deg']) > .00001:
                    raise ValueError('Counter reconstruction disagrees with original short-gap acquisition')
                travel_by_stage[row['stage']] += evidence['counter_step_deg']
            rows.append(row)
            previous = row
    if travel_by_stage['powered'] < 180000 or travel_by_stage['stopping'] < 36000:
        raise ValueError('Insufficient powered/coast counter validation travel')
    # Replay actual recorded packets with deliberately sparse host delivery.
    sparse = CounterAngle(2420)
    sparse.update(rows[0])
    last = rows[0]
    for row in rows[1:]:
        if row['t'] - last['t'] >= .016 or row is rows[-1]:
            sparse.update(row)
            last = row
    if abs(sparse.travel - tracker.travel) > .00001:
        raise ValueError('Sparse counter replay lost complete revolutions')
    return dict(measurement_agreement_verified=True, speed_trial_qualified=False,
                baseline_sha256=digest, reference=str(folder.resolve()),
                samples=len(rows), travel_deg=tracker.travel, travel_by_stage=travel_by_stage,
                sparse_replay_travel_deg=sparse.travel,
                source_sha256={name: hashlib.sha256((folder/name).read_bytes()).hexdigest()
                               for name in ('samples.jsonl', 'result.json', 'mcconf-candidate.bin', 'final-readback.json')})


def replay_counter_run(samples, observations, maximum_rpm, *, coast_gap_s=.025, coast_window_s=.25,
                       allow_coast_deferred=False, tracker_type=CounterAngle):
    """Recompute a completed counter acquisition, including coast, from its samples."""
    start_indices = [i for i, row in enumerate(samples) if row['stage'] == 'before_current']
    if len(start_indices) != 1:
        raise ValueError('Exactly one counter-run starting sample required')
    index = start_indices[0]
    start_t = samples[index]['t']
    seed = [row for row in samples[:index+1] if row['t'] >= start_t-.12]
    if len(seed) < 2 or seed[-1]['t'] - seed[0]['t'] < .1:
        raise ValueError('Counter replay quiet seed missing')
    tracker = tracker_type(maximum_rpm)
    for row in seed:
        guard_speed(tracker.update(row), maximum_rpm)
    origin = tracker.travel
    powered = {}
    coasting = False
    pending_capture = False
    for row in samples[index+1:]:
        if row['stage'] == 'final':
            continue
        if row['stage'] not in ('powered', 'stopping'):
            raise ValueError('Unexpected counter acquisition stage')
        if row['stage'] == 'powered' and coasting:
            raise ValueError('Powered acquisition resumed after coast')
        if row['stage'] == 'stopping':
            coasting = True
            tracker.configure_timing(coast_gap_s, coast_window_s)
        evidence = (tracker.update_coast(row, allow_defer=allow_coast_deferred)
                    if row['stage'] == 'stopping' else tracker.update(row))
        if evidence.get('counter_capture_deferred'):
            if row.get('counter_capture_deferred') is not True:
                raise ValueError('Missing deferred coast capture evidence')
            pending_capture = True
            continue
        if row.get('counter_capture_deferred'):
            raise ValueError('Unexpected deferred coast capture marker')
        guard_speed(evidence, maximum_rpm)
        pending_capture = False
        for key, value in evidence.items():
            if key not in row or not math.isfinite(row[key]) or abs(row[key] - value) > .00001:
                raise ValueError('Saved counter evidence disagrees with replay')
        if row['stage'] == 'powered':
            powered[row['t']] = evidence
    if pending_capture:
        raise ValueError('Deferred coast capture was never resolved')
    if len(powered) != len(observations):
        raise ValueError('Counter sample/observation count mismatch')
    for row in observations:
        evidence = powered.pop(row['t'])
        if (abs(row['encoder_rpm'] - evidence['counter_rpm']) > .00001
                or abs(row['travel_deg'] - (evidence['counter_travel_deg'] - origin)) > .00001):
            raise ValueError('Counter speed/travel observation mismatch')
