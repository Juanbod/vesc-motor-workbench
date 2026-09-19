"""Zero-current verification and exact baseline recovery. Never sends a pulse."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter as monotonic, sleep

from vesc_workbench.fixture import locked_probe_permit, require_locked
from vesc_workbench.locked_probe import ProbeClient, preflight_config


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    require_locked()
    baseline = Path(args.baseline).read_bytes()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    result = dict(pulse_sent=False, motor_restored=False)
    try:
        with ProbeClient("COM10", timeout_s=.25) as client:
            client.response_timeout_s = 2
            fw = asdict(client.fw_version())
            current, app = client.get_raw_config("motor"), client.get_raw_config("app")
            preflight_config(fw, baseline, app)
            (output / "entry.bin").write_bytes(current)
            with locked_probe_permit(baseline) as permit:
                if current != baseline:
                    permit.adopt_existing_limits(current)
                quiet = []
                until = monotonic() + .65
                while monotonic() < until:
                    client.set_current(0)
                    row = asdict(client.get_values())
                    row.update(position_deg=client.pid_position, t=monotonic())
                    quiet.append(row)
                    sleep(.015)
                result["samples"] = quiet
                permit.verify_stopped(quiet)
                if current != baseline:
                    client.set_raw_config("motor", baseline)
                    client.read_response(13)
                actual = client.get_raw_config("motor")
                (output / "restored.bin").write_bytes(actual)
                result["motor_restored"] = actual == baseline
                result["app_unchanged"] = client.get_raw_config("app") == app
                client.set_current(0)
                result["final_values"] = asdict(client.get_values())
                result["final_position_deg"] = client.pid_position
    except (Exception, KeyboardInterrupt) as exc:
        result["error"] = str(exc) or type(exc).__name__
    (output / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "samples"}, indent=2))
    return 0 if result["motor_restored"] and result.get("app_unchanged") and not result.get("error") else 2


if __name__ == "__main__":
    raise SystemExit(main())
