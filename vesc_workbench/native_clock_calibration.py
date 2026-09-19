"""Bound controller tick frequency using host request/response time brackets."""
import math


def load_clock_reference(path, baseline, *, now=None):
    """Recompute the calibration from its immutable quiet source before hardware access."""
    import hashlib
    import json
    from pathlib import Path
    from struct import unpack_from
    from time import perf_counter
    from .fixture import verify_encoder_quiet
    from .native_counter_snapshot import DistanceCounterDecoder
    from .wire_config import decode_config

    path = Path(path)
    saved = json.loads(path.read_text(encoding='utf-8'))
    source = Path(saved['source'])
    data = (source/'samples.jsonl').read_bytes()
    if hashlib.sha256(data).hexdigest() != saved['source_sha256']:
        raise ValueError('Native clock source hash mismatch')
    report = json.loads((source/'result.json').read_text(encoding='utf-8'))
    if (report.get('excitation_sent') is not False or report.get('configuration_writes') is not False
            or report.get('flash_writes') is not False
            or any(error != 'Native timer frequency disagrees with host time brackets' for error in report.get('errors', []))):
        raise ValueError('Native clock source is not a quiet acquisition')
    final = json.loads((source/'final-readback.json').read_text(encoding='utf-8'))
    if (final.get('baseline_sha256') != hashlib.sha256(baseline).hexdigest()
            or final.get('excitation_sent') is not False
            or any(final.get(k) is not True for k in ('read_only', 'baseline_restored', 'zero_current_verified', 'app_isolated'))):
        raise ValueError('Native clock source final baseline/standstill mismatch')
    verify_encoder_quiet(final['samples'])
    age = (perf_counter() if now is None else now)-final['samples'][-1]['t']
    if not math.isfinite(age) or not 0 <= age <= 600:
        raise ValueError('Native clock calibration is stale')
    rows = [json.loads(line) for line in data.splitlines()]
    decoder = None
    nonces = set()
    for row in rows:
        native, before, after = row['native'], row['legacy_before'], row['legacy_after']
        payload = bytes.fromhex(native['raw_payload_hex'])
        if (len(payload) != 33 or payload[0] != 36
                or unpack_from('>II', payload, 1) != (6817, native['nonce']) or native['nonce'] in nonces):
            raise ValueError('Invalid native clock source packet/nonce')
        nonces.add(native['nonce'])
        fields = unpack_from('>IfffIf', payload, 9)
        keys = ('start_tick', 'distance', 'distance_abs', 'position_deg', 'end_tick', 'encoder_error_rate')
        if any(native[k] != v for k, v in zip(keys, fields)) or native['encoder_error_rate'] != 0:
            raise ValueError('Native clock source raw packet mismatch')
        for values in (before, after):
            if (any(not math.isfinite(v) for v in values.values()) or values['fault_code']
                    or abs(values['current_motor_a']) > .1 or math.hypot(values['id_a'], values['iq_a']) > .2
                    or abs(values['duty']) > .001 or not 21 <= values['v_in'] < 24.9):
                raise ValueError('Native clock source was not at zero current')
        if decoder is None:
            decoder = DistanceCounterDecoder(decode_config(baseline, 'motor'), native,
                                              before['tachometer'], before['tachometer_abs'])
        if (decoder.recover(native['distance']) != before['tachometer'] or before['tachometer'] != after['tachometer']
                or decoder.recover(native['distance_abs']) != before['tachometer_abs']
                or before['tachometer_abs'] != after['tachometer_abs']):
            raise ValueError('Native clock source counter disagreement')
    calibration = calibrate_clock([row['native'] for row in rows])
    if any(calibration[k] != saved[k] for k in ('tick_hz_lower', 'tick_hz_upper', 'tick_hz_estimate')):
        raise ValueError('Native clock calibration is not reproducible')
    if len(decoder.scales) != 1 or final['samples'][0]['t'] < rows[-1]['native']['host_received_s']:
        raise ValueError('Native clock final order or distance scale is ambiguous')
    return dict(calibration, path=str(path.resolve()), source_sha256=saved['source_sha256'],
                age_s=age, distance_scale=decoder.scales[0], verified=True)


def calibrate_clock(snapshots):
    if len(snapshots) < 50:
        raise ValueError('Insufficient native clock evidence')
    expanded = []
    previous_tick = previous_received = None
    ticks = 0
    for row in snapshots:
        start, end, tick = row['host_request_s'], row['host_received_s'], row['end_tick']
        if (not all(math.isfinite(v) for v in (start, end)) or not 0 <= end-start <= .025
                or type(tick) is not int or not 0 <= tick <= 0xffffffff
                or (previous_received is not None and start <= previous_received)):
            raise ValueError('Invalid host/native clock brackets')
        if previous_tick is not None:
            delta = (tick-previous_tick) & 0xffffffff
            if not 0 < delta < 10000:
                raise ValueError('Native clock reset/gap')
            ticks += delta
        expanded.append((start, end, ticks))
        previous_tick, previous_received = tick, end
    if expanded[-1][0]-expanded[0][1] < 59.5:
        raise ValueError('A full minute of clock evidence is required')
    lower, upper = 9000.0, 11000.0
    checked = 0
    # Several staggered long windows detect incompatible frequency/drift bounds.
    for first_index in range(0, len(expanded)//2, max(1, len(expanded)//20)):
        a = expanded[first_index]
        for last_index in range(first_index+1, len(expanded), max(1, len(expanded)//20)):
            b = expanded[last_index]
            duration_low, duration_high = b[0]-a[1], b[1]-a[0]
            if duration_low < 10:
                continue
            delta = b[2]-a[2]
            lower = max(lower, (delta-1)/duration_high)
            upper = min(upper, (delta+1)/duration_low)
            checked += 1
    a, b = expanded[0], expanded[-1]
    lower = max(lower, (b[2]-a[2]-1)/(b[1]-a[0]))
    upper = min(upper, (b[2]-a[2]+1)/(b[0]-a[1]))
    if lower > upper or checked < 10:
        raise ValueError('No consistent controller clock rate fits the observations')
    if (upper-lower)/lower > .001:
        raise ValueError('Controller clock calibration interval is too wide')
    return dict(tick_hz_lower=lower, tick_hz_upper=upper, tick_hz_estimate=(lower+upper)/2,
                checked_windows=checked+1, samples=len(snapshots),
                host_span_s=b[1]-a[0], relative_interval_width=(upper-lower)/lower,
                nominal_10000hz_consistent=lower <= 10000 <= upper,
                scope='Observed stationary bench interval; not a temperature-wide clock certification')
