"""Run exactly one low-current pilot, only after physical fixture removal."""
import argparse
import json
from pathlib import Path

from vesc_workbench.fixture import require_free
from vesc_workbench.locked_probe import ProbeClient
from vesc_workbench.offset_comparison import hfi_pose
from vesc_workbench.synrm_pilot_runner import run_pilot, timing_reference
from vesc_workbench.synrm_repeatability import read_quiet_baseline
from vesc_workbench.synrm_pilot import SPEED_STAGES, stage_limits
from vesc_workbench.host_scheduling import above_normal_priority, defer_cyclic_gc
from vesc_workbench.counter_angle import audit_counter_reference
from vesc_workbench.battery_return import require_battery_source
from vesc_workbench.native_probe_client import NativeProbeClient
from vesc_workbench.native_clock_calibration import load_clock_reference


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--armed-free-rotor', action='store_true', required=True)
    p.add_argument('--baseline', required=True)
    p.add_argument('--hfi-summary', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--stage', choices=('pilot', 'extension_3a', 'rotation_3a') + SPEED_STAGES, default='pilot')
    p.add_argument('--prior-run')
    p.add_argument('--above-normal', action='store_true')
    p.add_argument('--defer-cyclic-gc', action='store_true')
    p.add_argument('--buffered-rx', action='store_true')
    p.add_argument('--timing-probe')
    p.add_argument('--coast-timing-probe')
    p.add_argument('--counter-reference')
    p.add_argument('--native-clock-calibration')
    p.add_argument('--reference-baseline', help='Original HFI baseline for an audited ADC-only restart')
    args = p.parse_args()
    require_free()  # Must precede opening COM10, even when --armed is supplied.
    baseline = Path(args.baseline).read_bytes()
    pose = hfi_pose(args.hfi_summary)
    if args.reference_baseline:
        from vesc_workbench.baseline_transition import transfer_pose
        pose = transfer_pose(pose, Path(args.reference_baseline).read_bytes(), baseline)
    timing_checks = {}
    counter_evidence = None
    native_reference = None
    client_type, client_options = ProbeClient, {}
    if stage_limits(args.stage).get('native_counter'):
        if not args.native_clock_calibration:
            p.error('Native acquisition requires a fresh --native-clock-calibration')
        native_reference = load_clock_reference(args.native_clock_calibration, baseline)
        client_type = NativeProbeClient
        client_options = dict(baseline=baseline, clock_calibration=native_reference,
                              maximum_rpm=stage_limits(args.stage)['maximum_rpm'],
                              dq=stage_limits(args.stage).get('native_dq', False))
    if stage_limits(args.stage).get('return_current_a'):
        require_battery_source()
    if stage_limits(args.stage).get('counter_assisted'):
        if not args.counter_reference:
            p.error('Counter-assisted acquisition requires --counter-reference before controller access')
        try:
            if args.reference_baseline:
                from vesc_workbench.baseline_transition import transfer_counter_evidence
                counter_evidence = transfer_counter_evidence(args.counter_reference, baseline)
            else:
                counter_evidence = audit_counter_reference(args.counter_reference, baseline)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            p.error(f'Counter qualification failed before controller access: {exc}')
    if stage_limits(args.stage).get('maximum_rpm', 0) > 2420 or counter_evidence is not None:
        if not args.timing_probe or not args.coast_timing_probe:
            p.error('This speed stage requires both --timing-probe and --coast-timing-probe; no controller access performed')
        try:
            for coast, folder in ((False, args.timing_probe), (True, args.coast_timing_probe)):
                timing_checks['coast' if coast else 'powered'] = timing_reference(
                    folder, baseline, args.stage, coast=coast, above_normal=args.above_normal,
                    defer_gc=args.defer_cyclic_gc, buffered_rx=args.buffered_rx,
                    native_clock_reference=native_reference)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            p.error(f'Timing qualification failed before controller access: {exc}')
    with above_normal_priority(args.above_normal) as scheduling, \
         defer_cyclic_gc(args.defer_cyclic_gc) as gc_mode, client_type('COM10', timeout_s=.1, buffered_rx=args.buffered_rx, **client_options) as client:
        client.response_timeout_s = .1
        report = run_pilot(client, baseline, pose, args.output, stage=args.stage, prior_run=args.prior_run,
                           entry_reader=(lambda: read_quiet_baseline(client, baseline)) if args.stage in SPEED_STAGES else None,
                           counter_evidence=counter_evidence)
    if native_reference is not None:
        with (Path(args.output)/'native-runtime.json').open('x', encoding='utf-8') as f:
            json.dump(client.native_snapshot_runtime, f, indent=2)
    with (Path(args.output)/'host-scheduling.json').open('x', encoding='utf-8') as f:
        json.dump(dict(scheduling=scheduling, cyclic_gc=gc_mode, buffered_rx=args.buffered_rx,
                       timing_qualification=timing_checks), f, indent=2, allow_nan=False)
    if (args.stage in SPEED_STAGES and report['zero_current_verified']
            and report['baseline_restored'] and report.get('app_isolated')):
        with ProbeClient('COM10', timeout_s=.1, buffered_rx=args.buffered_rx) as client:
            client.response_timeout_s = .1
            final = read_quiet_baseline(client, (Path(args.output)/'mcconf-before.bin').read_bytes())
        with (Path(args.output)/'final-readback.json').open('x', encoding='utf-8') as f:
            json.dump(final, f, indent=2, allow_nan=False)
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
