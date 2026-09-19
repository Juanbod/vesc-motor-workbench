"""Zero-current-only recovery of a recorded alignment run after coast-down."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter, sleep

from vesc_workbench.field_alignment import LIMITS, check_motion
from vesc_workbench.fixture import require_free, verify_encoder_quiet
from vesc_workbench.hfi_capture import write_motor_verified
from vesc_workbench.locked_probe import ProbeClient, preflight_config
from vesc_workbench.wire_config import patch_config


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-directory', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    require_free()
    source, output = Path(args.run_directory), Path(args.output)
    baseline = (source/'mcconf-before.bin').read_bytes()
    limited = (source/'mcconf-limited.bin').read_bytes()
    if patch_config(baseline, 'motor', LIMITS) != limited:
        raise ValueError('Recovery source is not the exact reviewed protective configuration')
    output.mkdir(parents=True, exist_ok=False)
    report = dict(excitation_sent=False, restored=False, zero_current_verified=False, ok=False)
    samples = []
    with ProbeClient('COM10', timeout_s=.15) as c:
        c.response_timeout_s = 2
        try:
            c.set_current(0)
            fw = asdict(c.fw_version())
            entry, app = c.get_raw_config('motor'), c.get_raw_config('app')
            preflight_config(fw, baseline, app)
            if entry not in (baseline, limited):
                raise ValueError('Unrecognized motor state; no restoration write')
            (output/'mcconf-entry.bin').write_bytes(entry)
            (output/'appconf-entry.bin').write_bytes(app)
            deadline = perf_counter()+6
            while perf_counter() < deadline:
                c.set_current(0)
                before = perf_counter()
                row = dict(asdict(c.get_values()), position_deg=c.pid_position, t=perf_counter())
                samples.append(row)
                if row['t']-before > .1:
                    raise ValueError('Slow recovery telemetry')
                check_motion(row)
                tail = [r for r in samples if r['t'] >= row['t']-.4]
                try:
                    verify_encoder_quiet(tail)
                except RuntimeError:
                    sleep(.015)
                    continue
                report['zero_current_verified'] = True
                break
            if not report['zero_current_verified']:
                raise ValueError('No quiet interval; retain protective configuration')
            if c.get_raw_config('app') != app or c.get_raw_config('motor') != entry:
                raise ValueError('Configuration changed during recovery')
            if entry != baseline:
                write_motor_verified(c, baseline)
            report['restored'] = c.get_raw_config('motor') == baseline
            report['app_unchanged'] = c.get_raw_config('app') == app
            c.set_current(0)
            final = dict(asdict(c.get_values()), position_deg=c.pid_position, t=perf_counter())
            check_motion(final)
            report['final'] = final
            report['ok'] = report['restored'] and report['app_unchanged']
        except (Exception, KeyboardInterrupt) as exc:
            report['failure'] = str(exc) or type(exc).__name__
        finally:
            try:
                c.set_current(0)
            except Exception as exc:
                report['ok'] = False
                report['stop_error'] = str(exc)
            report['samples'] = samples
            (output/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'samples'}, indent=2))
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
