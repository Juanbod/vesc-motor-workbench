#!/usr/bin/env python3
"""Small, safety-first VESC UART monitor and stepped-current tester.

It never writes motor/app configuration to flash. The only command capable of
moving the motor is enabled by the explicit --armed flag. A zero-current command
is sent on every normal exit and on Ctrl+C.
"""

from __future__ import annotations

import argparse
import csv
import glob
import statistics
import struct
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import serial
    from serial.tools import list_ports
except ImportError as error:
    raise SystemExit("Missing dependency. Install Python 3.11+ and run: py -m pip install pyserial") from error


COMM_GET_VALUES = 4
COMM_SET_CURRENT = 6


def crc16_ccitt(data: bytes) -> int:
    crc = 0
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def packet(payload: bytes) -> bytes:
    size = len(payload)
    if size <= 255:
        head = bytes((2, size))
    elif size <= 65535:
        head = bytes((3, size >> 8, size & 0xFF))
    else:
        raise ValueError("Payload is too long")
    return head + payload + struct.pack(">H", crc16_ccitt(payload)) + bytes((3,))


@dataclass
class Values:
    timestamp: float
    fet_temp_c: float
    motor_temp_c: float
    motor_current_a: float
    input_current_a: float
    id_a: float
    iq_a: float
    duty: float
    erpm: int
    input_voltage_v: float
    fault_code: int = 0


class VescUart:
    def __init__(self, port: str, baud: int, timeout: float = 0.25):
        self.serial = serial.Serial(port, baudrate=baud, timeout=timeout)

    def close(self) -> None:
        self.serial.close()

    def send(self, payload: bytes) -> None:
        self.serial.write(packet(payload))
        self.serial.flush()

    def receive(self) -> bytes:
        deadline = time.monotonic() + self.serial.timeout
        while time.monotonic() < deadline:
            start = self.serial.read(1)
            if not start:
                continue
            if start == b"\x02":
                length = self.serial.read(1)
                if not length:
                    continue
                size = length[0]
            elif start == b"\x03":
                length = self.serial.read(2)
                if len(length) != 2:
                    continue
                size = int.from_bytes(length, "big")
            else:
                continue
            body = self.serial.read(size + 3)
            if len(body) != size + 3 or body[-1] != 3:
                continue
            payload, received_crc = body[:size], int.from_bytes(body[size:size + 2], "big")
            if crc16_ccitt(payload) == received_crc:
                return payload
        raise TimeoutError("No valid VESC response")

    def set_current(self, amps: float) -> None:
        value = round(amps * 1000.0)
        self.send(bytes((COMM_SET_CURRENT,)) + struct.pack(">i", value))

    def values(self) -> Values:
        self.send(bytes((COMM_GET_VALUES,)))
        response = self.receive()
        if not response or response[0] != COMM_GET_VALUES or len(response) < 29:
            raise RuntimeError("Unexpected GET_VALUES response")
        # Standard VESC GET_VALUES layout. Firmware can append fields, but these
        # first fields are kept compatible by VESC firmware.
        fet, motor, motor_i, input_i, id_a, iq_a, duty, erpm, vin = struct.unpack(
            ">hhiiiihih", response[1:29]
        )
        fault_code = response[53] if len(response) >= 54 else 0
        return Values(time.time(), fet / 10, motor / 10, motor_i / 100, input_i / 100,
                      id_a / 100, iq_a / 100, duty / 1000, erpm, vin / 10, fault_code)


def print_values(values: Values) -> None:
    print(f"{values.erpm:7d} eRPM | Iq {values.iq_a:6.2f} A | Id {values.id_a:6.2f} A | "
          f"motor {values.motor_current_a:6.2f} A | input {values.input_current_a:6.2f} A | "
          f"duty {values.duty:5.3f} | {values.input_voltage_v:.1f} V | fault {values.fault_code}")


def assert_safe(values: Values, args: argparse.Namespace, previous: Values | None = None) -> None:
    if abs(values.motor_current_a) > args.max_motor_current:
        raise RuntimeError(f"Motor-current stop: {values.motor_current_a:.1f} A")
    if abs(values.input_current_a) > args.max_input_current:
        raise RuntimeError(f"Input-current stop: {values.input_current_a:.1f} A")
    if abs(values.erpm) > args.max_erpm:
        raise RuntimeError(f"Speed stop: {values.erpm} eRPM")
    if previous and abs(values.erpm - previous.erpm) > args.max_erpm_delta:
        raise RuntimeError(
            f"eRPM jump stop: {previous.erpm} -> {values.erpm} "
            f"(limit {args.max_erpm_delta})"
        )
    if values.fet_temp_c > args.max_fet_temp:
        raise RuntimeError(f"FET-temperature stop: {values.fet_temp_c:.1f} C")
    if values.fault_code:
        raise RuntimeError(f"VESC fault stop: fault code {values.fault_code}")


def run_monitor(vesc: VescUart, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        print_values(vesc.values())
        time.sleep(0.1)


def ramp_targets(start: float, target: float, step: float) -> list[float]:
    if step <= 0:
        raise ValueError("--ramp-step must be positive")
    result = []
    current = start
    while abs(target - current) > 1e-9:
        if target > current:
            current = min(target, current + step)
        else:
            current = max(target, current - step)
        result.append(current)
    return result


def run_test(vesc: VescUart, args: argparse.Namespace) -> Path:
    steps = [float(item) for item in args.steps.split(",")]
    if any(step <= 0 for step in steps):
        raise ValueError("All current steps must be positive")
    log_path = Path(args.log).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[*Values.__annotations__.keys(), "target_current_a", "profile", "event", "stop_reason"],
        )
        writer.writeheader()
        previous_values: Values | None = None
        current_command = 0.0
        try:
            for target in steps:
                print(f"Target: {target:.1f} A for {args.hold:.1f} s")
                for ramp_step in ramp_targets(current_command, target, args.ramp_step):
                    vesc.set_current(ramp_step)
                    values = vesc.values()
                    assert_safe(values, args, previous_values)
                    writer.writerow(
                        asdict(values)
                        | {
                            "target_current_a": ramp_step,
                            "profile": args.profile,
                            "event": "ramp",
                            "stop_reason": "",
                        }
                    )
                    stream.flush()
                    print_values(values)
                    previous_values = values
                    time.sleep(args.ramp_delay)
                current_command = target

                deadline = time.monotonic() + args.hold
                while time.monotonic() < deadline:
                    vesc.set_current(target)
                    values = vesc.values()
                    assert_safe(values, args, previous_values)
                    writer.writerow(
                        asdict(values)
                        | {
                            "target_current_a": target,
                            "profile": args.profile,
                            "event": "sample",
                            "stop_reason": "",
                        }
                    )
                    stream.flush()
                    print_values(values)
                    previous_values = values
                    time.sleep(0.05)
                vesc.set_current(0.0)
                current_command = 0.0
                previous_values = None
                time.sleep(args.pause)
        except Exception as error:
            writer.writerow(
                {
                    "timestamp": time.time(),
                    "target_current_a": current_command,
                    "profile": args.profile,
                    "event": "stop",
                    "stop_reason": str(error),
                }
            )
            stream.flush()
            raise
    return log_path


def compare_logs(pattern: str, output: str) -> Path:
    files = [Path(path) for path in glob.glob(pattern)]
    if not files:
        raise FileNotFoundError(f"No CSV files match: {pattern}")
    rows = []
    for path in files:
        with path.open(newline="", encoding="utf-8") as stream:
            samples = list(csv.DictReader(stream))
        if not samples:
            continue
        by_step: dict[str, list[dict[str, str]]] = {}
        for sample in samples:
            if sample.get("event") == "stop" or not sample.get("target_current_a"):
                continue
            by_step.setdefault(sample["target_current_a"], []).append(sample)
        for target, group in by_step.items():
            erpm = [float(item["erpm"]) for item in group]
            motor_i = [float(item["motor_current_a"]) for item in group]
            input_i = [float(item["input_current_a"]) for item in group]
            profile = group[0].get("profile") or path.stem
            rows.append({
                "profile": profile, "source": path.name, "target_current_a": target,
                "samples": len(group), "mean_erpm": round(statistics.fmean(erpm), 1),
                "erpm_stddev": round(statistics.pstdev(erpm), 1),
                "mean_motor_current_a": round(statistics.fmean(motor_i), 2),
                "mean_input_current_a": round(statistics.fmean(input_i), 2),
            })
    out = Path(output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ["profile"])
        writer.writeheader()
        writer.writerows(rows)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ports", help="List available serial ports")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--port", required=True, help="VESC USB/UART COM port, e.g. COM5")
    common.add_argument("--baud", type=int, default=115200)
    monitor = sub.add_parser("monitor", parents=[common])
    monitor.add_argument("--seconds", type=float, default=10)
    test = sub.add_parser("test", parents=[common])
    test.add_argument("--armed", action="store_true", help="Required before current can be sent")
    test.add_argument("--steps", default="0.5,1.0,1.5", help="Positive current steps in A")
    test.add_argument("--hold", type=float, default=2.0)
    test.add_argument("--pause", type=float, default=1.0)
    test.add_argument("--ramp-step", type=float, default=0.5)
    test.add_argument("--ramp-delay", type=float, default=0.05)
    test.add_argument("--max-motor-current", type=float, default=20.0)
    test.add_argument("--max-input-current", type=float, default=15.0)
    test.add_argument("--max-erpm", type=int, default=1000)
    test.add_argument("--max-erpm-delta", type=int, default=500)
    test.add_argument("--max-fet-temp", type=float, default=70.0)
    test.add_argument("--log", default=f"vesc-test-{int(time.time())}.csv")
    test.add_argument("--profile", default="manual", help="Name of the VESC XML profile currently loaded")
    compare = sub.add_parser("compare", help="Summarise one or more test CSV logs")
    compare.add_argument("--logs", required=True, help='Glob, e.g. "C:\\logs\\test-*.csv"')
    compare.add_argument("--output", default="vesc-summary.csv")
    args = parser.parse_args()
    if args.command == "ports":
        for port in list_ports.comports():
            print(f"{port.device}: {port.description}")
        return
    if args.command == "compare":
        print(f"Summary written to {compare_logs(args.logs, args.output)}")
        return
    if args.command == "test" and not args.armed:
        raise SystemExit("Dry run only. Re-run with --armed after securing the motor and fitting a physical E-stop.")
    vesc = VescUart(args.port, args.baud)
    try:
        if args.command == "monitor":
            run_monitor(vesc, args.seconds)
        else:
            log = run_test(vesc, args)
            print(f"Log written to {log}")
    except KeyboardInterrupt:
        print("Stopped by user")
    finally:
        try:
            vesc.set_current(0.0)
        except Exception:
            pass
        vesc.close()


if __name__ == "__main__":
    main()
