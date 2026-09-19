"""Zero-current validation of controller-timed snapshots against ordinary GET_VALUES."""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import secrets
from time import perf_counter

from vesc_workbench.fixture import require_free
from vesc_workbench.locked_probe import ProbeClient
from vesc_workbench.lisp_capability import read_lisp_capability
from vesc_workbench.synrm_repeatability import read_quiet_baseline
from vesc_workbench.wire_config import decode_config
from vesc_workbench.native_counter_snapshot import read_counter_snapshot, DistanceCounterDecoder, NativeCounterClock
from vesc_workbench.counter_angle import CounterAngle, guard_speed
from vesc_workbench.native_clock_calibration import calibrate_clock
from vesc_workbench.host_scheduling import above_normal_priority, defer_cyclic_gc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--duration-s', type=int, choices=(5, 60), default=5)
    parser.add_argument('--calibrate-clock', action='store_true')
    parser.add_argument('--above-normal', action='store_true')
    parser.add_argument('--defer-cyclic-gc', action='store_true')
    args = parser.parse_args()
    if args.calibrate_clock and args.duration_s != 60:
        parser.error('Clock calibration requires the full 60-second acquisition')
    require_free()
    baseline = Path(args.baseline).read_bytes()
    configuration = decode_config(baseline, 'motor')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    result = dict(excitation_sent=False, configuration_writes=False, flash_writes=False,
                  qualified_for_powered_control=False, tick_hz_assumed=10000,
                  ok=False, errors=[], samples=0)
    rows = []
    with above_normal_priority(args.above_normal) as scheduling, \
         defer_cyclic_gc(args.defer_cyclic_gc) as gc_mode, \
         ProbeClient('COM10', timeout_s=.1, buffered_rx=True) as client:
        result['host_scheduling'] = dict(scheduling=scheduling, cyclic_gc=gc_mode)
        client.response_timeout_s = .2
        try:
            entry = read_quiet_baseline(client, baseline)
            (output/'entry-readback.json').write_text(json.dumps(entry, indent=2), encoding='utf-8')
            capability = read_lisp_capability(client)
            result['capability'] = capability
            if capability['stored_code_bytes'] != 0 or not capability['runtime_response']:
                raise ValueError('An available empty Lisp runtime is required')
            nonce = secrets.randbelow(0xffffff)+1
            decoder = None
            clock = NativeCounterClock()
            tracker = CounterAngle(7370, .025, .25)
            started = perf_counter()
            while perf_counter()-started < args.duration_s:
                require_free()
                if (output/'STOP').exists():
                    raise ValueError('STOP requested')
                client.set_current(0)
                before = asdict(client.get_values())
                snapshot = read_counter_snapshot(client, nonce)
                nonce = nonce % 0xffffff+1
                after = asdict(client.get_values())
                record = dict(native=snapshot, legacy_before=before, legacy_after=after)
                rows.append(record)
                for values in (before, after):
                    if (values['fault_code'] or abs(values['current_motor_a']) > .1
                            or math.hypot(values['id_a'], values['iq_a']) > .2
                            or abs(values['duty']) > .001 or not 21 <= values['v_in'] < 24.9):
                        raise ValueError('Quiet native snapshot telemetry guard')
                for field in ('tachometer', 'tachometer_abs'):
                    if before[field] != after[field]:
                        raise ValueError('Rotor sector changed during quiet calibration')
                if decoder is None:
                    decoder = DistanceCounterDecoder(configuration, snapshot,
                                                      before['tachometer'], before['tachometer_abs'])
                    result['possible_distance_scales'] = decoder.scales
                row = clock.row(snapshot, decoder)
                record['counter_input'] = row
                if row['tachometer'] != before['tachometer'] or row['tachometer_abs'] != before['tachometer_abs']:
                    raise ValueError('Native counters disagree with legacy GET_VALUES')
                evidence = tracker.update(row)
                guard_speed(evidence, 7370)
                record['counter_evidence'] = evidence
                if snapshot['host_latency_s'] > .025:
                    raise ValueError('Native snapshot host round trip exceeds 25 ms')
            first, last = rows[0]['native'], rows[-1]['native']
            native_duration = rows[-1]['counter_input']['t']-rows[0]['counter_input']['t']
            lower = last['host_request_s']-first['host_received_s']-.0002
            upper = last['host_received_s']-first['host_request_s']+.0002
            if args.calibrate_clock:
                result['clock_calibration'] = calibrate_clock([row['native'] for row in rows])
            elif not lower <= native_duration <= upper:
                raise ValueError('Native timer frequency disagrees with host time brackets')
            result.update(ok=True, controller_clock_scale_consistent=lower <= native_duration <= upper,
                          native_duration_s=native_duration,
                          host_duration_bounds_s=[lower, upper], samples=len(rows),
                          maximum_host_round_trip_s=max(r['native']['host_latency_s'] for r in rows),
                          maximum_native_bracket_s=max(r['counter_input']['latency_s'] for r in rows))
        except Exception as exc:
            result['errors'].append(str(exc))
            result['samples'] = len(rows)
        finally:
            client.set_current(0)
            final = read_quiet_baseline(client, baseline)
            (output/'final-readback.json').write_text(json.dumps(final, indent=2), encoding='utf-8')
            with (output/'samples.jsonl').open('x', encoding='utf-8') as stream:
                for row in rows:
                    stream.write(json.dumps(row, allow_nan=False)+'\n')
            (output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
