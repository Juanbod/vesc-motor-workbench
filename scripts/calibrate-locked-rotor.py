"""Prepare, simulate or analyze locked-rotor calibration WITHOUT connecting to VESC."""
import argparse
import json
from pathlib import Path

from vesc_workbench.locked_rotor import (
    LockedRotorPlan, analyze, preparation, report_text, save_json, simulated_dataset,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "simulate", "analyze"))
    parser.add_argument("--output", required=True, help="New output directory; existing results are never overwritten")
    parser.add_argument("--plan", help="JSON object containing LockedRotorPlan fields")
    parser.add_argument("--baseline", help="Optional local baseline binary, read only for SHA-256")
    parser.add_argument("--input", help="Captured dataset JSON; required for analyze")
    args = parser.parse_args(argv)
    if (args.mode == "analyze") != bool(args.input):
        parser.error("--input is required only for analyze")
    if args.mode == "analyze" and args.plan:
        parser.error("analyze uses the plan embedded in its dataset")
    plan = LockedRotorPlan(**json.loads(Path(args.plan).read_text(encoding="utf-8-sig"))) if args.plan else LockedRotorPlan()
    prepared = preparation(plan, args.baseline)
    output = Path(args.output)
    # Read and validate before creating output. No serial module is imported.
    input_bytes = Path(args.input).read_bytes() if args.input else None
    data = json.loads(input_bytes.decode("utf-8-sig")) if input_bytes is not None else None
    if args.mode == "simulate":
        data = simulated_dataset(plan)
    if args.mode != "prepare":
        result = analyze(data)
        # The imported plan is authoritative, even for rejected datasets.
        if args.mode == "analyze":
            prepared["plan"] = data.get("plan") if isinstance(data, dict) else None
            prepared["acquisition_schedule"] = None
    output.mkdir(parents=True, exist_ok=False)
    save_json(output / "preparation.json", prepared)
    if args.mode != "prepare":
        # Preserve the original bytes of imported evidence, including invalid
        # nonfinite JSON extensions, without laundering them into a clean input.
        if args.input:
            with (output / "dataset.json").open("xb") as target:
                target.write(input_bytes)
        else:
            save_json(output / "dataset.json", data)
        save_json(output / "result.json", result)
        with (output / "report.md").open("x", encoding="utf-8") as stream:
            stream.write(report_text(result))
        print(json.dumps({"status": result["status"], "reason": result["reason"],
                          "output": str(output.resolve()), "controller_connected": False}, indent=2))
        return 0 if result["status"] == "candidate_only" else 2
    print(json.dumps(prepared, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
