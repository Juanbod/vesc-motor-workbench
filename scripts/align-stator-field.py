"""Default: offline plan only. Live use requires fixture removal and explicit arm."""
import argparse
import json
from pathlib import Path

from vesc_workbench.field_alignment import plan, run
from vesc_workbench.fixture import require_free
from vesc_workbench.locked_probe import ProbeClient


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('pilot', 'sweep'), default='pilot')
    p.add_argument('--current', type=float, choices=(.5, 1., 2.), default=.5)
    p.add_argument('--start-phase', type=float, default=150)
    p.add_argument('--dwell', type=float, choices=(.8, 2., 4.), default=.8)
    p.add_argument('--output', required=True)
    p.add_argument('--baseline')
    p.add_argument('--pilot-result')
    p.add_argument('--armed-free-rotor-alignment', action='store_true')
    args = p.parse_args()
    spec = plan(args.mode, args.current, args.start_phase, args.dwell)
    if not args.armed_free_rotor_alignment:
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=False)
        (output/'plan.json').write_text(json.dumps(spec, indent=2), encoding='utf-8')
        print('OFFLINE ONLY: no serial connection; plan saved to', output.resolve())
        return 0
    require_free()  # Fail before opening the serial port while fixture is locked.
    if not args.baseline:
        p.error('--baseline is required for live operation')
    pilot = json.loads(Path(args.pilot_result).read_text()) if args.pilot_result else None
    with ProbeClient('COM10', timeout_s=.15) as client:
        client.response_timeout_s = 2
        result = run(client, args.output, args.baseline, spec, pilot)
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
