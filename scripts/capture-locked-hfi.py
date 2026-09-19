"""One low-voltage HFI measurement with raw plotting and exact rollback."""
import argparse
import json
from vesc_workbench.fixture import require_locked
from vesc_workbench.hfi_capture import HfiClient, run_capture


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--baseline", required=True)
    p.add_argument("--duty", type=float, choices=(.005, .01, .02, .05, .1), default=.01)
    p.add_argument("--plot-mode", type=int, choices=(1, 2), default=2)
    p.add_argument("--armed-locked-hfi", action="store_true", required=True)
    args = p.parse_args()
    require_locked()
    with HfiClient("COM10", timeout_s=.15, plot_mode=args.plot_mode) as client:
        client.response_timeout_s = 2
        result = run_capture(client, args.output, args.baseline, args.duty)
    display = dict(result)
    if "analysis" in display:
        display["analysis"] = {k: v for k, v in display["analysis"].items() if k != "frames"}
    print(json.dumps(display, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
