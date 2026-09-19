"""Offline clock calibration from preserved read-only native snapshots."""
import argparse
import hashlib
import json
from pathlib import Path

from vesc_workbench.native_clock_calibration import calibrate_clock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    source = Path(args.source)
    path = source/'samples.jsonl'
    data = path.read_bytes()
    rows = [json.loads(line) for line in data.splitlines()]
    result = calibrate_clock([row['native'] for row in rows])
    result.update(source=str(source.resolve()), source_sha256=hashlib.sha256(data).hexdigest(),
                  excitation_sent=False, prior_failed_probe_reclassified=False,
                  qualified_for_powered_control=False)
    with Path(args.output).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
