"""Generate a non-armed pilot draft from existing evidence, with no UART access."""
import argparse
import json
from pathlib import Path

from vesc_workbench.offset_comparison import hfi_pose
from vesc_workbench.synrm_pilot import build_pilot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--hfi-summary', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    baseline = Path(args.baseline).read_bytes()
    pose = hfi_pose(args.hfi_summary)
    plan, candidate = build_pilot(baseline, pose['offset_deg'] % 360, pose['encoder_deg'])
    if pose['baseline_sha256'] != plan['baseline_sha256']:
        raise ValueError('HFI evidence and baseline do not match')
    plan['source_evidence'] = pose
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    # Deliberately not named mcconf.bin or recommended: not an uploadable release.
    with (output/'candidate.NOT_ARMED.bin').open('xb') as stream:
        stream.write(candidate)
    with (output/'plan.json').open('x', encoding='utf-8') as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)
    print(json.dumps(plan, indent=2))


if __name__ == '__main__':
    main()
