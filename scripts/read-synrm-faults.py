"""Read fault history and quiet baseline; no current or configuration writes."""
import argparse
import json
from pathlib import Path
from time import perf_counter

from vesc_workbench.locked_probe import ProbeClient
from vesc_workbench.synrm_repeatability import read_quiet_baseline
from vesc_workbench.uart import VescPacketError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    baseline = Path(args.baseline).read_bytes()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    lines = []
    with ProbeClient('COM10', timeout_s=.1, buffered_rx=True) as client:
        before = read_quiet_baseline(client, baseline)
        client.send_payload(b'\x14faults')
        deadline = perf_counter() + 4
        idle = False
        while perf_counter() < deadline and len(lines) < 1024:
            try:
                payload = client.read_payload()
            except VescPacketError as exc:
                if str(exc) != 'Timed out waiting for VESC packet.':
                    raise
                idle = True
                break
            if payload and payload[0] == 21:
                lines.append(payload[1:].decode('utf-8', errors='strict').strip())
        if not idle or not lines:
            raise ValueError('Incomplete fault-history response')
        final = read_quiet_baseline(client, baseline)
    report = dict(read_only=True, excitation_sent=False, configuration_writes=False,
                  capture_ended_on_idle=idle, lines=lines)
    for name, value in (('faults.json', report), ('entry-readback.json', before), ('final-readback.json', final)):
        with (output/name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
