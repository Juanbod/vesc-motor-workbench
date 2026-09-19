"""Read-only controller-timed encoder/distance snapshot and exact float32 inversion."""
import math
import re
from struct import pack, unpack, unpack_from
from time import perf_counter

SNAPSHOT_METHOD = 'prepared_readonly_lambda_v1'
DQ_SNAPSHOT_METHOD = 'prepared_readonly_dq_lambda_v2'


def f32(value):
    return unpack('>f', pack('>f', value))[0]


def snapshot_expression(nonce, *, dq=False):
    if type(nonce) is not int or not 1 <= nonce <= 0xffffff:
        raise ValueError('Invalid snapshot nonce')
    extra = ('(bufset-f32 b 32 (get-vd))(bufset-f32 b 36 (get-vq))'
             '(bufset-f32 b 40 (get-id))(bufset-f32 b 44 (get-iq))'
             '(bufset-u32 b 48 (systime))') if dq else ''
    return (f'(let ((s (systime)) (d (get-dist)) (a (get-dist-abs)) (p (get-encoder)) '
            f'(e (systime)) (b (array-create {52 if dq else 32}))) (progn (bufset-u32 b 0 {6820 if dq else 6817}) '
            f'(bufset-u32 b 4 {nonce}) (bufset-u32 b 8 s) (bufset-f32 b 12 d) '
            '(bufset-f32 b 16 a) (bufset-f32 b 20 p) (bufset-u32 b 24 e) '
            f'(bufset-f32 b 28 (get-encoder-error-rate)) {extra}(send-data b)))').encode('ascii')


def prepared_expression(name, *, remove=False, dq=False):
    if not re.fullmatch(r'wbcs[0-9a-f]{12}', name):
        raise ValueError('Invalid private snapshot function name')
    if remove:
        return f"(progn (undefine '{name}) 6819)".encode('ascii')
    body = snapshot_expression(16777215, dq=dq).decode('ascii').replace('16777215', 'n')
    expression = f'(progn (define {name} (lambda (n) {body})) 6818)'.encode('ascii')
    if len(expression) >= 512:
        raise ValueError('Prepared snapshot exceeds REPL bound')
    return expression


def checked_repl_ack(client, expression, expected):
    client.send_payload(bytes((138,))+expression+b'\0')
    for _ in range(16):
        line = client.read_response(135)[1:].decode('ascii', errors='replace').strip('\0\r\n ')
        if line == f'> {expected}':
            return
        # send-data returns t; its REPL print can follow the binary snapshot.
        if line == '> t':
            continue
        if line.startswith('> '):
            raise ValueError(f'Unexpected snapshot setup result: {line}')
    raise ValueError('No snapshot setup acknowledgement')


def read_counter_snapshot(client, nonce, clock=perf_counter, *, prepared_name=None, dq=False):
    expression = snapshot_expression(nonce, dq=dq)
    if prepared_name is not None:
        prepared_expression(prepared_name)  # Validate before interpolation.
        expression = f'({prepared_name} {nonce})'.encode('ascii')
    before = clock()
    client.send_payload(bytes((138,))+expression+b'\0')
    payload = client.read_response(36)
    after = clock()
    result = dict(nonce=nonce, raw_payload_hex=payload.hex(), host_request_s=before,
                  host_received_s=after, host_latency_s=after-before)
    if len(payload) != (53 if dq else 33) or payload[0] != 36 or unpack_from('>II', payload, 1) != (6820 if dq else 6817, nonce):
        raise ValueError('Native counter snapshot framing/nonce mismatch')
    start, distance, absolute, angle, end, error_rate = unpack_from('>IfffIf', payload, 9)
    if (not all(math.isfinite(v) for v in (distance, absolute, angle, error_rate))
            or not 0 <= angle < 360 or error_rate != 0 or ((end-start) & 0xffffffff) > 100):
        raise ValueError('Invalid native counter snapshot or encoder error')
    result.update(start_tick=start, end_tick=end, distance=distance, distance_abs=absolute,
                  position_deg=angle, encoder_error_rate=error_rate)
    if dq:
        vd, vq, id_a, iq_a, dq_end = unpack_from('>ffffI', payload, 33)
        if (not all(math.isfinite(v) for v in (vd, vq, id_a, iq_a))
                or ((dq_end-end) & 0xffffffff) > 100):
            raise ValueError('Invalid native dq diagnostic or acquisition bracket')
        result.update(dq_vd_v=vd, dq_vq_v=vq, dq_id_a=id_a, dq_iq_a=iq_a, dq_end_tick=dq_end)
    return result


def validate_dq_record(row):
    keys = ('native_dq_vd_v', 'native_dq_vq_v', 'native_dq_id_a', 'native_dq_iq_a')
    if any(type(row.get(k)) not in (int, float) or not math.isfinite(row[k]) for k in keys):
        raise ValueError('Missing/nonfinite native dq diagnostic')
    end, start = row.get('native_dq_end_tick'), row.get('native_end_tick')
    if (type(end) is not int or type(start) is not int or not 0 <= end <= 0xffffffff
            or not 0 <= start <= 0xffffffff or ((end-start) & 0xffffffff) > 100):
        raise ValueError('Invalid native dq diagnostic bracket')


class DistanceCounterDecoder:
    """Keep every possible nearby float32 scale; reject non-unique counter recovery."""
    def __init__(self, configuration, snapshot, signed_counter, absolute_counter):
        diameter = configuration['si_wheel_diameter']
        poles = configuration['si_motor_poles']
        gear = configuration['si_gear_ratio']
        if not all(math.isfinite(v) and v > 0 for v in (diameter, poles, gear)):
            raise ValueError('Invalid distance scaling configuration')
        reference = f32(diameter*math.pi/(3*poles*gear))
        bits = unpack('>I', pack('>f', reference))[0]
        scales = [unpack('>f', pack('>I', bits+i))[0] for i in range(-8, 9)]
        for value, count in ((snapshot['distance'], signed_counter), (snapshot['distance_abs'], absolute_counter)):
            if type(count) is not int or not 100 <= abs(count) < 2**23:
                raise ValueError('Quiet counters cannot qualify float32 inversion')
            scales = [scale for scale in scales if f32(count*scale) == value]
        if not scales:
            raise ValueError('Native distance does not reproduce the observed sector counters')
        self.scales = scales

    def recover(self, distance):
        if not math.isfinite(distance):
            raise ValueError('Nonfinite native distance')
        possibilities = set()
        for scale in self.scales:
            estimate = distance/scale
            if abs(estimate) >= 2**23:
                raise ValueError('Float32 counter precision envelope exceeded')
            centre = math.floor(estimate)
            for candidate in range(centre-2, centre+4):
                if f32(candidate*scale) == distance:
                    possibilities.add(candidate)
        if len(possibilities) != 1:
            raise ValueError('Native distance-to-counter inversion is ambiguous')
        return possibilities.pop()


class NativeCounterClock:
    def __init__(self):
        self.previous_end = None
        self.elapsed_ticks = 0

    def row(self, snapshot, decoder):
        end, start = snapshot['end_tick'], snapshot['start_tick']
        if self.previous_end is not None:
            gap = (end-self.previous_end) & 0xffffffff
            if not 0 < gap <= 10000:
                raise ValueError('Native clock gap/reset exceeds one second')
            self.elapsed_ticks += gap
        self.previous_end = end
        width = (end-start) & 0xffffffff
        return dict(t=(self.elapsed_ticks+1)/10000, latency_s=(width+1)/10000,
                    position_deg=snapshot['position_deg'],
                    tachometer=decoder.recover(snapshot['distance']),
                    tachometer_abs=decoder.recover(snapshot['distance_abs']))
