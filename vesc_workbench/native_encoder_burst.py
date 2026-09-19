"""Fixed, read-only 16-sample encoder capture in Lisp RAM; no motor commands."""
import math
from struct import unpack_from
from time import perf_counter


TICK_HZ = 10000  # Pinned VESC 6.02 chconf.h; must be checked on the installed build.
COUNT = 16


def burst_expression(nonce):
    if type(nonce) is not int or not 1 <= nonce <= 0xffffff:
        raise ValueError('Invalid bounded capture nonce')
    expression = (
        f'(let ((b (array-create 200))) (progn (bufset-u32 b 0 6816) (bufset-u32 b 4 {nonce}) '
        '(looprange i 0 16 (let ((p (+ 8 (* i 12)))) (progn '
        '(bufset-u32 b p (systime)) (bufset-f32 b (+ p 4) (get-encoder)) '
        '(bufset-u32 b (+ p 8) (systime)) (sleep 0.001)))) (send-data b)))'
    )
    return expression.encode('ascii')


def decode_burst(payload, nonce, maximum_rpm=7370):
    if not math.isfinite(maximum_rpm) or maximum_rpm <= 0:
        raise ValueError('Invalid RPM envelope')
    if len(payload) != 201 or payload[0] != 36 or unpack_from('>II', payload, 1) != (6816, nonce):
        raise ValueError('Native burst framing or nonce mismatch')
    rows = []
    previous_end = previous_start = previous_angle = None
    elapsed_ticks = 0
    travel = 0
    for i in range(COUNT):
        start, angle, end = unpack_from('>IfI', payload, 9+12*i)
        width = (end-start) & 0xffffffff
        if width > 100 or not math.isfinite(angle) or not 0 <= angle < 360:
            raise ValueError('Invalid native capture angle/time bracket')
        row = dict(index=i, start_tick=start, end_tick=end, position_deg=angle,
                   bracket_upper_s=(width+1)/TICK_HZ)
        if previous_end is not None:
            gap = (end-previous_end) & 0xffffffff
            upper = ((end-previous_start) & 0xffffffff)+1
            if gap == 0 or gap > 100 or 6*maximum_rpm*upper/TICK_HZ+.2 >= 180:
                raise ValueError('Native sample gap is temporally ambiguous')
            step = (angle-previous_angle+180) % 360-180
            if abs(step) > 6*maximum_rpm*upper/TICK_HZ+.2:
                raise ValueError('Native angle change exceeds speed envelope')
            elapsed_ticks += gap
            travel += step
            row.update(gap_s=gap/TICK_HZ, gap_upper_s=upper/TICK_HZ, step_deg=step)
        row.update(elapsed_s=elapsed_ticks/TICK_HZ, travel_deg=travel)
        rows.append(row)
        previous_end, previous_start, previous_angle = end, start, angle
    return rows


def read_native_burst(client, nonce, clock=perf_counter):
    expression = burst_expression(nonce)
    started = clock()
    client.send_payload(bytes((138,))+expression+b'\0')
    payload = client.read_response(36)
    received = clock()
    result = dict(nonce=nonce, expression=expression.decode(), raw_payload_hex=payload.hex(),
                request_started_s=started, response_received_s=received,
                host_round_trip_s=received-started, tick_hz_assumed=TICK_HZ,
                excitation_sent=False, configuration_writes=False, flash_writes=False,
                capture_verified=False, qualified_for_powered_control=False, errors=[])
    try:
        rows = decode_burst(payload, nonce)
        result.update(rows=rows, capture_verified=True,
                      maximum_gap_upper_s=max(r.get('gap_upper_s', 0) for r in rows),
                      maximum_bracket_upper_s=max(r['bracket_upper_s'] for r in rows))
    except ValueError as exc:
        result['errors'].append(str(exc))
    return result
