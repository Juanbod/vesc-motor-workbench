"""Independent read-only baseline and standstill check; never commands torque."""
import argparse
import json
from pathlib import Path

from vesc_workbench.locked_probe import ProbeClient
from vesc_workbench.synrm_repeatability import read_quiet_baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    with ProbeClient('COM10', timeout_s=.1, buffered_rx=True) as client:
        client.response_timeout_s = .1
        result = read_quiet_baseline(client, Path(args.baseline).read_bytes())
    (output/'final-readback.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
