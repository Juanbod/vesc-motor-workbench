"""Lisp capability/readout probe; optional literal arithmetic, never motor commands."""
import argparse
import json
from pathlib import Path
import secrets

from vesc_workbench.fixture import require_free
from vesc_workbench.locked_probe import ProbeClient
from vesc_workbench.lisp_capability import read_lisp_capability, probe_empty_lisp_arithmetic, read_native_snapshot
from vesc_workbench.synrm_repeatability import read_quiet_baseline
from vesc_workbench.native_encoder_burst import read_native_burst


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--output', required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--empty-runtime-arithmetic', action='store_true',
                        help='May initialize an empty interpreter for literal (+ 1 2); no motor commands')
    mode.add_argument('--native-snapshot', action='store_true')
    mode.add_argument('--native-burst', action='store_true')
    args = parser.parse_args()
    require_free()
    baseline = Path(args.baseline).read_bytes()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    with ProbeClient('COM10', timeout_s=.1, buffered_rx=True) as client:
        client.response_timeout_s = .2
        entry = read_quiet_baseline(client, baseline)
        (output/'entry-readback.json').write_text(json.dumps(entry, indent=2), encoding='utf-8')
        try:
            result = read_lisp_capability(client)
            if args.empty_runtime_arithmetic:
                result['arithmetic_probe'] = probe_empty_lisp_arithmetic(client, result)
                result['runtime_started'] = None
                result['runtime_available_after_probe'] = result['arithmetic_probe']['arithmetic_verified']
            if args.native_snapshot or args.native_burst:
                if result['stored_code_bytes'] != 0 or not result['runtime_response']:
                    raise ValueError('Snapshot requires confirmed empty storage and an available runtime')
                if args.native_snapshot:
                    result['native_snapshot'] = read_native_snapshot(client)
                else:
                    result['native_burst'] = read_native_burst(client, secrets.randbelow(0xffffff)+1)
            (output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        finally:
            final = read_quiet_baseline(client, baseline)
            (output/'final-readback.json').write_text(json.dumps(final, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
