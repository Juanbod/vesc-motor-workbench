"""Replay saved HFI captures without opening a serial port."""
import argparse
import json
from pathlib import Path

from vesc_workbench.hfi_audit import audit_run, synthetic_axis
from vesc_workbench.locked_rotor import axial_delta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    rows = []
    for name in args.reports:
        path = Path(name).resolve()
        report = json.loads(path.read_text(encoding='utf-8'))
        points = json.loads((path.parent/'plot-points.json').read_text(encoding='utf-8'))
        rows.append(dict(source=str(path), **audit_run(report, points)))
    result = dict(source_commit='f7c2b34e1cff2234cae98be3abf0cd50e249558f',
                  motor_commands_sent=False, calibration_validated=False, rows=rows,
                  synthetic_max_exact_axis_error_deg=max(abs(axial_delta(synthetic_axis(i/10), i/10)) for i in range(1800)),
                  synthetic_max_approximate_axis_error_deg=max(abs(axial_delta(synthetic_axis(i/10, True), i/10)) for i in range(1800)),
                  limitation='Synthetic model checks conventions, not real hardware or exact firmware binary identity')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    with (output/'audit.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
