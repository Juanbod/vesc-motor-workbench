"""One bounded experiment; uses the campaign's guards, backup and rollback."""
from pathlib import Path
from dataclasses import replace
import argparse
import json
import math

from vesc_workbench.bench import Campaign, HardwareBench, SimulatedBench, load_plan, write_json

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--plan', default='config/synrm-startup.json')
parser.add_argument('--openloop-erpm', type=float)
parser.add_argument('--speed', action='store_true')
parser.add_argument('--observer-error', action='store_true')
parser.add_argument('--kp', type=float)
parser.add_argument('--ki', type=float)
parser.add_argument('--current', type=float)
offset = parser.add_mutually_exclusive_group()
offset.add_argument('--offset-delta', type=float)
offset.add_argument('--offset-absolute', type=float)
parser.add_argument('--baseline', help='Require live motor bytes to match this backup before changes')
parser.add_argument('--repeats', type=int, default=1)
parser.add_argument('--mtpa', type=int, choices=(0, 1), default=1)
parser.add_argument('--direction', type=int, choices=(-1, 1), default=1)
parser.add_argument('--inverted', type=int, choices=(0, 1))
mode = parser.add_mutually_exclusive_group(required=True)
mode.add_argument('--armed', action='store_true')
mode.add_argument('--simulate', action='store_true')
args = parser.parse_args()
if args.observer_error and (args.simulate or not args.speed or args.openloop_erpm is not None):
    parser.error('--observer-error requires a hardware speed trial')
root = Path(__file__).resolve().parents[1]
source_plan = load_plan(root / args.plan)
plan = replace(source_plan, test_current_a=args.current if args.current is not None else source_plan.test_current_a,
               max_trials=args.repeats, direction=args.direction)
plan.validate()
if not 1 <= args.repeats <= 36:
    raise ValueError('Repeats must be in 1..36')
if args.offset_delta is not None and (not math.isfinite(args.offset_delta) or abs(args.offset_delta) > 180):
    raise ValueError('Offset delta outside +/-180')
if args.offset_absolute is not None and not 0 <= args.offset_absolute < 360:
    raise ValueError('Absolute offset must be in [0, 360)')
for gain in (args.kp, args.ki):
    if gain is not None and not 0 < gain <= .2:
        raise ValueError('Speed gains must be in (0, 0.2]')
output = Path(args.output)
output.mkdir(parents=True, exist_ok=False)
if args.observer_error:
    from vesc_workbench.observer_bench import ObserverBench
    bench = ObserverBench('COM10')
else:
    bench = SimulatedBench() if args.simulate else HardwareBench('COM10')
campaign = Campaign(bench, plan, output, simulated=args.simulate)
failure = None
try:
    if args.baseline and not args.simulate and bench.motor != Path(args.baseline).read_bytes():
        raise ValueError('Live motor configuration differs from the required baseline')
    bench.snapshot(output / 'baseline')
    from dataclasses import asdict
    write_json(output / 'plan.json', {'arguments': vars(args), 'effective_plan': asdict(plan)})
    bench.prepare(plan)
    changes = {**campaign.common(), 'foc_mtpa_mode': args.mtpa,
               'foc_encoder_offset': args.offset_absolute if args.offset_absolute is not None
               else (bench.values['foc_encoder_offset'] + (args.offset_delta or 0)) % 360}
    if args.inverted is not None:
        if args.inverted != bench.values.get('foc_encoder_inverted', 0):
            raise ValueError('Recalibrate and validate encoder direction separately before these trials')
        changes['foc_encoder_inverted'] = args.inverted
    for key, value in (('s_pid_kp', args.kp), ('s_pid_ki', args.ki)):
        if value is not None:
            if not 0 < value <= .2:
                raise ValueError('Speed gains must be in (0, 0.2]')
            changes[key] = value
    for _ in range(args.repeats):
        result = campaign.trial('diagnostic', changes, speed=args.speed, openloop_erpm=args.openloop_erpm)
        campaign.state = result['status']
        print(json.dumps(result, indent=2), flush=True)
        if not result['ok']:
            break
        if args.observer_error:
            if not result.get('observer_comparison', {}).get('passes_angle_screen'):
                campaign.state = 'observer_not_tracking'
                break
            campaign.state = 'observer_screen_passed'
except (Exception, KeyboardInterrupt) as exc:
    failure = str(exc) or type(exc).__name__
    campaign.state = 'stopped'
    print(failure)
finally:
    cleanup = bench.close()
    if cleanup.get('error'):
        campaign.state = 'recovery_required'
    campaign.journal(reason=failure, cleanup=cleanup)
    campaign.report(failure, cleanup)
    print(json.dumps(cleanup))

raise SystemExit(0 if not failure and not cleanup.get('error')
                 and cleanup.get('motor_restored') and campaign.results
                 and all(r.get('ok') for r in campaign.results)
                 and (not args.observer_error or all(
                     r.get('observer_comparison', {}).get('passes_angle_screen')
                     for r in campaign.results)) else 2)
