"""Initialize an empty Lisp runtime with arithmetic only; never loads stored code."""
import argparse
import json
from pathlib import Path

from vesc_workbench.fixture import require_free
from vesc_workbench.locked_probe import ProbeClient
from vesc_workbench.native_counter_snapshot import checked_repl_ack
from vesc_workbench.synrm_repeatability import read_quiet_baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    require_free()
    baseline = Path(args.baseline).read_bytes()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=False)
    report = dict(ok=False, excitation_sent=False, flash_writes=False, configuration_writes=False,
                  expression='(+ 1 2)', stored_code_bytes=None)
    try:
        with ProbeClient('COM10', timeout_s=.1, buffered_rx=True) as client:
            client.response_timeout_s = .3
            entry = read_quiet_baseline(client, baseline)
            (root/'entry-readback.json').write_text(json.dumps(entry, indent=2), encoding='utf-8')
            client.send_payload(bytes((130,))+bytes(8))
            if client.read_response(130) != bytes((130,))+bytes(8):
                raise ValueError('Stored Lisp program must be empty')
            report['stored_code_bytes'] = 0
            checked_repl_ack(client, b'(+ 1 2)', 3)
            report['arithmetic_acknowledged'] = True
            final = read_quiet_baseline(client, baseline)
            (root/'final-readback.json').write_text(json.dumps(final, indent=2), encoding='utf-8')
            report['ok'] = True
    except Exception as exc:
        report['error'] = str(exc)
    (root/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
