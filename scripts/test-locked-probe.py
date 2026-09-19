"""Exactly one bounded fixed-phase current probe; no rotation or calibration."""
import argparse
import json
from vesc_workbench.fixture import require_locked
from vesc_workbench.locked_probe import ProbeClient, run_probe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--port", default="COM10")
    parser.add_argument("--resume-baseline", help="Original backup; live bytes must exactly match its protective variant")
    parser.add_argument("--armed-locked-probe", action="store_true", required=True)
    args = parser.parse_args()
    require_locked()
    with ProbeClient(args.port, timeout_s=.25) as client:
        client.response_timeout_s = 2
        result = run_probe(client, args.output, args.resume_baseline)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
