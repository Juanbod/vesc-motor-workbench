"""Offline aggregation of independent measured offset runs."""
import argparse
import json
from pathlib import Path
from vesc_workbench.hfi_capture import summarize_dft_runs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("runs", nargs="+")
    p.add_argument("--reference-offset", required=True, type=float)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    paths = [Path(path).resolve() for path in args.runs]
    runs = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    result = summarize_dft_runs(runs, args.reference_offset)
    result["source_reports"] = [str(path) for path in paths]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    with (output / "offset-result.json").open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
