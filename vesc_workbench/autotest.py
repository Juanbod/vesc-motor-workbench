from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
import csv

from .uart import VescUartClient, VescValues


@dataclass(frozen=True)
class SafetyLimits:
    max_erpm: int = 1000
    max_erpm_delta: int = 500
    sample_period_s: float = 0.05
    max_motor_current_a: float = 100.0
    max_input_current_a: float = 110.0
    max_mos_temp_c: float = 80.0
    max_motor_temp_c: float = 100.0
    max_duty: float = 0.95


@dataclass(frozen=True)
class CurrentRampResult:
    log_path: Path
    completed: bool
    stop_reason: str


def parse_steps(value: str) -> tuple[float, ...]:
    steps = tuple(float(part.strip()) for part in value.split(",") if part.strip())
    if not steps:
        raise ValueError("At least one current step is required.")
    return steps


def _write_stop_row(writer: csv.DictWriter[str], reason: str) -> None:
    writer.writerow(
        {
            "time_s": "",
            "command_a": "",
            "erpm": "",
            "iq_a": "",
            "current_motor_a": "",
            "current_in_a": "",
            "id_a": "",
            "duty": "",
            "v_in": "",
            "temp_mos_c": "",
            "temp_motor_c": "",
            "fault_code": "",
            "event": "stop",
            "reason": reason,
        }
    )


def check_safety(values: VescValues, previous: VescValues | None, limits: SafetyLimits) -> str | None:
    if abs(values.erpm) > limits.max_erpm:
        return f"abs(eRPM) {abs(values.erpm)} exceeded limit {limits.max_erpm}"
    if previous is not None and abs(values.erpm - previous.erpm) > limits.max_erpm_delta:
        return (
            f"eRPM delta {abs(values.erpm - previous.erpm)} exceeded "
            f"limit {limits.max_erpm_delta}"
        )
    if values.fault_code:
        return f"VESC fault code {values.fault_code}"
    if abs(values.current_motor_a) > limits.max_motor_current_a:
        return (
            f"abs(motor current) {abs(values.current_motor_a):.2f}A exceeded "
            f"limit {limits.max_motor_current_a:.2f}A"
        )
    if abs(values.current_in_a) > limits.max_input_current_a:
        return (
            f"abs(input current) {abs(values.current_in_a):.2f}A exceeded "
            f"limit {limits.max_input_current_a:.2f}A"
        )
    if values.temp_mos_c > limits.max_mos_temp_c:
        return f"MOS temperature {values.temp_mos_c:.1f}C exceeded limit {limits.max_mos_temp_c:.1f}C"
    if values.temp_motor_c > limits.max_motor_temp_c:
        return f"Motor temperature {values.temp_motor_c:.1f}C exceeded limit {limits.max_motor_temp_c:.1f}C"
    if abs(values.duty) > limits.max_duty:
        return f"abs(duty) {abs(values.duty):.3f} exceeded limit {limits.max_duty:.3f}"
    return None


def run_current_ramp(
    port: str,
    baudrate: int,
    timeout_s: float,
    steps: tuple[float, ...],
    hold_s: float,
    limits: SafetyLimits,
    log_path: Path,
    armed: bool,
) -> CurrentRampResult:
    if not armed:
        return CurrentRampResult(
            log_path=log_path,
            completed=False,
            stop_reason="Refusing to move motor without armed=True.",
        )

    log_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "time_s",
        "command_a",
        "erpm",
        "iq_a",
        "current_motor_a",
        "current_in_a",
        "id_a",
        "duty",
        "v_in",
        "temp_mos_c",
        "temp_motor_c",
        "fault_code",
        "event",
        "reason",
    ]

    stop_reason = ""
    completed = False
    started = monotonic()
    previous: VescValues | None = None

    with VescUartClient(port, baudrate=baudrate, timeout_s=timeout_s) as client:
        with log_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            try:
                for command_a in steps:
                    step_started = monotonic()
                    while monotonic() - step_started < hold_s:
                        client.set_current(command_a)
                        values = client.get_values()
                        reason = check_safety(values, previous, limits)
                        writer.writerow(
                            {
                                "time_s": f"{monotonic() - started:.3f}",
                                "command_a": f"{command_a:.3f}",
                                "erpm": values.erpm,
                                "iq_a": f"{values.iq_a:.3f}",
                                "current_motor_a": f"{values.current_motor_a:.3f}",
                                "current_in_a": f"{values.current_in_a:.3f}",
                                "id_a": f"{values.id_a:.3f}",
                                "duty": f"{values.duty:.4f}",
                                "v_in": f"{values.v_in:.2f}",
                                "temp_mos_c": f"{values.temp_mos_c:.1f}",
                                "temp_motor_c": f"{values.temp_motor_c:.1f}",
                                "fault_code": values.fault_code,
                                "event": "sample",
                                "reason": "",
                            }
                        )
                        if reason:
                            stop_reason = reason
                            _write_stop_row(writer, reason)
                            return CurrentRampResult(log_path, completed=False, stop_reason=reason)
                        previous = values
                        sleep(limits.sample_period_s)
                completed = True
                stop_reason = "completed"
                _write_stop_row(writer, stop_reason)
                return CurrentRampResult(log_path, completed=completed, stop_reason=stop_reason)
            finally:
                client.set_current(0.0)
