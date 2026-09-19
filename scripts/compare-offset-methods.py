"""Offline report from recorded physical data. Requires NumPy; never opens UART."""
import argparse
import json
from pathlib import Path

from vesc_workbench.offset_comparison import hfi_pose, alignment_rows, compare


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    training = [hfi_pose(root/'profiles'/f'synrm-as5048a-offset-{name}-20260912'/'offset-result.json')
                for name in ('measured', 'pose2', 'pose3', 'pose4')]
    check = [hfi_pose(root/'profiles/synrm-as5048a-offset-return-20260912/offset-result.json')]
    alignment, excluded = [], []
    for name in ('stator-alignment-pilot-20260912-06', 'stator-alignment-sweep-20260912-01',
                 'stator-alignment-pilot-20260912-07'):
        good, bad = alignment_rows(root/'logs'/name/'result.json')
        alignment.extend(good)
        excluded.extend(bad)
    result = compare(training, check, alignment)
    result['excluded_alignment_steps'] = excluded
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    (output/'comparison.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
