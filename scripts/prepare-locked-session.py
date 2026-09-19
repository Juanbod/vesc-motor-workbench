"""Read fresh calibration and disable external control in RAM, without excitation."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from time import perf_counter, sleep

from vesc_workbench.fixture import locked_isolation_permit, verify_encoder_quiet, require_locked
from vesc_workbench.locked_probe import ProbeClient, preflight_config
from vesc_workbench.hfi_capture import guard_sample
from vesc_workbench.wire_config import decode_config


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    p.add_argument('--previous-baseline', required=True)
    args = p.parse_args()
    require_locked()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(excitation_sent=False, app_isolated=False, ok=False)
    samples = []
    with ProbeClient('COM10', timeout_s=.3) as c:
        c.response_timeout_s = 2
        try:
            fw = asdict(c.fw_version())
            if fw != dict(major=6, minor=2, hardware='MKSESC_84_100_HP'):
                raise ValueError('Unexpected firmware/hardware')
            motor, app = c.get_raw_config('motor'), c.get_raw_config('app')
            (output / 'mcconf-before.bin').write_bytes(motor)
            (output / 'appconf-before.bin').write_bytes(app)
            old = decode_config(Path(args.previous_baseline).read_bytes(), 'motor')
            new = decode_config(motor, 'motor')
            changes = {k: [old[k], v] for k, v in new.items() if old[k] != v}
            report['motor_changes'] = changes
            allowed = {f'foc_offsets_{kind}[{i}]' for kind in ('current', 'voltage') for i in range(3)}
            if set(changes) - allowed:
                raise ValueError('Non-calibration motor changes require review')
            def quiet():
                rows = []
                deadline = perf_counter() + .5
                while perf_counter() < deadline:
                    c.set_current(0)
                    started = perf_counter()
                    row = dict(asdict(c.get_values()), position_deg=c.pid_position, t=perf_counter())
                    samples.append(row)
                    if perf_counter() - started > .1:
                        raise ValueError('Telemetry latency exceeds 100 ms')
                    guard_sample(row, rows[0]['position_deg'] if rows else row['position_deg'])
                    rows.append(row)
                    sleep(.015)
                verify_encoder_quiet(rows)
                return rows
            with locked_isolation_permit(app, quiet()) as permit:
                # The isolated bytes are validated before any write is sent.
                preflight_config(fw, motor, permit.isolated)
                c.set_app_config_temporary(permit.isolated)
                if c.get_raw_config('app') != permit.isolated:
                    raise ValueError('Temporary app readback mismatch')
                report['app_isolated'] = True
                (output / 'appconf-isolated.bin').write_bytes(permit.isolated)
            quiet()
            if c.get_raw_config('motor') != motor:
                raise ValueError('Motor configuration changed during preparation')
            report.update(ok=True, baseline_sha256=hashlib.sha256(motor).hexdigest(),
                          encoder_deg=samples[-1]['position_deg'])
        except Exception as exc:
            report['failure'] = str(exc)
        finally:
            try:
                c.set_current(0)
            finally:
                report['samples'] = samples
                (output / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'samples'}, indent=2))
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
