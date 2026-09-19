"""Exactly three bounded 3 A startup attempts; stop on the first nonqualified run."""
import argparse
import json
from pathlib import Path

from vesc_workbench.fixture import require_free
from vesc_workbench.locked_probe import ProbeClient
from vesc_workbench.offset_comparison import hfi_pose
from vesc_workbench.synrm_repeatability import run_repeatability


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--armed-free-rotor', action='store_true', required=True)
    p.add_argument('--baseline', required=True)
    p.add_argument('--hfi-summary', required=True)
    p.add_argument('--prior-run', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    require_free()
    baseline = Path(args.baseline).read_bytes()
    pose = hfi_pose(args.hfi_summary)

    def connect():
        c = ProbeClient('COM10', timeout_s=.1)
        c.response_timeout_s = .1
        return c

    summary = run_repeatability(connect, baseline, pose, args.output, args.prior_run,
                                progress=lambda event: print(json.dumps(event), flush=True))
    print(json.dumps(summary, indent=2))
    return 0 if summary['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
