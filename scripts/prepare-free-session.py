"""Preserve fresh ADC calibration and isolate external control in RAM at standstill."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter, sleep

from vesc_workbench.baseline_transition import adc_transition
from vesc_workbench.fixture import require_free, verify_encoder_quiet
from vesc_workbench.locked_probe import ProbeClient, preflight_config
from vesc_workbench.synrm_repeatability import read_quiet_baseline
from vesc_workbench.wire_config import patch_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-baseline', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    require_free()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False)
    report = dict(excitation_sent=False, motor_config_writes=False, flash_writes=False, ok=False)
    try:
        with ProbeClient('COM10', timeout_s=.1, buffered_rx=True) as client:
            client.response_timeout_s = .3
            fw = asdict(client.fw_version())
            actual, app = client.get_raw_config('motor'), client.get_raw_config('app')
            (root/'mcconf-before.bin').write_bytes(actual)
            (root/'appconf-before.bin').write_bytes(app)
            report['baseline_transition'] = adc_transition(Path(args.reference_baseline).read_bytes(), actual)
            isolated = patch_config(app, 'app', dict(app_to_use=0, timeout_msec=300, timeout_brake_current=0))
            preflight_config(fw, actual, isolated)
            rows = []
            for _ in range(25):
                require_free()
                started = perf_counter()
                row = dict(asdict(client.get_values()), position_deg=client.pid_position, t=perf_counter())
                rows.append(row)
                if row['t']-started > .1 or not 21 <= row['v_in'] < 24.9 or row['temp_mos_c'] > 50:
                    raise ValueError('Quiet session voltage, temperature or latency guard')
                sleep(.02)
            report['entry_samples'] = rows
            verify_encoder_quiet(rows)
            if client.get_raw_config('motor') != actual or client.get_raw_config('app') != app:
                raise ValueError('Configuration changed before isolation')
            require_free()
            client.set_app_config_temporary(isolated)
            if client.get_raw_config('app') != isolated:
                raise ValueError('RAM isolation readback mismatch')
            (root/'appconf-isolated.bin').write_bytes(isolated)
            final = read_quiet_baseline(client, actual)
            (root/'final-readback.json').write_text(json.dumps(final, indent=2), encoding='utf-8')
            report['ok'] = True
    except Exception as exc:
        report['error'] = str(exc)
    (root/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'entry_samples'}, indent=2))
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
