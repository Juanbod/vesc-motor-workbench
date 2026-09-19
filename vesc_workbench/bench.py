"""Bounded, feedback-driven experiments for the direct-encoder motor bench."""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter as monotonic, sleep
import csv
import json
import math
import statistics
import re

from .raw_config import sha256
from .uart import VescUartClient
from .wire_config import decode_config, patch_config, export_xml
from .qualification import speed_steps, startup_coverage


@dataclass(frozen=True)
class BenchPlan:
    synrm_zero_flux: bool = False
    extended_diagnostics: bool = False
    qualify_speed: bool = False
    max_trials: int = 16
    max_duration_s: float = 300
    test_current_a: float = 3
    phase_limit_a: float = 5
    input_limit_a: float = 3
    trip_current_a: float = 8
    max_erpm: float = 600
    max_duty: float = 0.35
    min_voltage: float = 21
    max_voltage: float = 29
    max_mos_temp: float = 55
    max_motor_temp: float = 65
    allow_missing_motor_temp: bool = False
    trial_energy_j: float = 12
    total_energy_j: float = 60
    trial_i2t: float = 35
    sample_s: float = 0.025
    ramp_s: float = 0.4
    trial_s: float = 2
    stall_s: float = 0.65
    settle_timeout_s: float = 15
    rollback_timeout_s: float = 30
    cooldown_s: float = 4
    startup_erpm: float = 120
    direction: int = 1
    repeats: int = 3
    offset_deltas: tuple = (0, -15, 15, -30, 30)
    speed_targets: tuple = (150, 300)
    speed_hold_s: float = 1.2
    speed_ramp_erpm_s: float = 400

    def validate(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, bool) or isinstance(value, tuple):
                continue
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Invalid {f.name}")
            if f.name != "direction" and value <= 0:
                raise ValueError(f"{f.name} must be positive")
        for key in ("max_trials", "repeats"):
            if type(getattr(self, key)) is not int:
                raise ValueError(f"{key} must be an integer")
        if type(self.allow_missing_motor_temp) is not bool:
            raise ValueError("allow_missing_motor_temp must be boolean")
        if type(self.synrm_zero_flux) is not bool:
            raise ValueError("synrm_zero_flux must be boolean")
        if type(self.extended_diagnostics) is not bool:
            raise ValueError("extended_diagnostics must be boolean")
        if type(self.qualify_speed) is not bool:
            raise ValueError("qualify_speed must be boolean")
        if self.trial_s > 60 or self.speed_hold_s * len(self.speed_targets) > 60:
            raise ValueError("No powered trial may exceed 60 seconds")
        if self.qualify_speed and (self.speed_hold_s < 5 or
                                  self.speed_hold_s * len(self.speed_targets) > self.trial_s):
            raise ValueError("Speed qualification requires complete steps of at least 5 seconds")
        if self.cooldown_s >= self.settle_timeout_s:
            raise ValueError("Settle timeout must exceed cooldown")
        if not 1 <= self.rollback_timeout_s <= 60:
            raise ValueError("Rollback standstill timeout must be in 1..60 seconds")
        if not 100 <= self.speed_ramp_erpm_s <= 600:
            raise ValueError("Speed ramp must be in 100..600 eRPM/s")
        if self.direction not in (-1, 1) or self.repeats < 2 or self.max_trials > 40:
            raise ValueError("Direction must be +/-1; repeats >=2; at most 40 trials per campaign")
        if not (self.test_current_a <= self.phase_limit_a < self.trip_current_a <= 30):
            raise ValueError("Require test current <= phase limit < trip current <= 30A")
        if self.input_limit_a > self.phase_limit_a or not 0 < self.max_duty <= 0.8:
            raise ValueError("Invalid input current or duty limit")
        if not (0.01 <= self.sample_s <= 0.05 and self.ramp_s < self.trial_s):
            raise ValueError("Invalid sampling or ramp duration")
        if self.min_voltage >= self.max_voltage or self.startup_erpm >= self.max_erpm:
            raise ValueError("Invalid voltage/speed range")
        if not self.offset_deltas or len(self.offset_deltas) > 9 or any(not math.isfinite(x) or abs(x) > 90 for x in self.offset_deltas):
            raise ValueError("Offset search must contain 1..9 deltas within +/-90 degrees")
        if not self.speed_targets or any(not math.isfinite(x) or not 0 < x < self.max_erpm for x in self.speed_targets):
            raise ValueError("Speed targets must be positive and below max_erpm")
        if self.allow_missing_motor_temp:
            caps = (15, 5, 300, 100) if self.extended_diagnostics else (5, 2, 60, 12)
            if any(value > limit for value, limit in zip(
                    (self.phase_limit_a, self.trial_s, self.total_energy_j, self.trial_energy_j), caps)):
                raise ValueError(f"Missing-temperature diagnostic bounds exceeded: {caps}")
            if self.extended_diagnostics and (self.trial_i2t > 1200 or self.cooldown_s < 8):
                raise ValueError("Extended diagnostics require I2t <=1200 and at least 8s cooldown")
        if self.max_erpm > 2000:
            raise ValueError("This startup bench is limited to 2000 eRPM; high-speed validation is a separate stage")


def load_plan(path: Path) -> BenchPlan:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("offset_deltas", "speed_targets"):
        if key in data:
            data[key] = tuple(data[key])
    plan = BenchPlan(**data)
    plan.validate()
    return plan


def write_json(path: Path, data: object) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)


class BenchStop(RuntimeError):
    pass


def find_port() -> str:
    from serial.tools.list_ports import comports
    ports = [p.device for p in comports() if p.vid == 0x0483 and p.pid == 0x5740]
    if len(ports) != 1:
        raise ValueError(f"Expected one VESC USB device, found {ports}; specify --port")
    return ports[0]


class EncoderMotion:
    def __init__(self, ratio: float, sign: int):
        self.ratio, self.sign = ratio, sign
        self.last = None
        self.turns = 0.0
        self.history = deque()
        self.speed = 0.0

    def update(self, samples: list[tuple[float, float]], batched: bool = False) -> None:
        for index, (stamp, angle) in enumerate(samples):
            if not math.isfinite(angle) or not 0 <= angle <= 360:
                raise BenchStop("Invalid encoder angle")
            if self.last is not None:
                self.turns += ((angle - self.last + 180) % 360 - 180) / 360 * self.sign
            self.last = angle
            # USB queues several angles before one RPC completes. Their host
            # arrival timestamps are not acquisition times: keep all travel,
            # but use only the latest point of each batch for speed estimation.
            if batched and index < len(samples) - 1:
                continue
            self.history.append((stamp, self.turns))
            while len(self.history) > 2 and stamp - self.history[0][0] > 0.15:
                self.history.popleft()
            dt = stamp - self.history[0][0]
            if dt > 0.06:
                self.speed = (self.turns - self.history[0][1]) * 60 * self.ratio / dt


class HardwareBench:
    def __init__(self, port: str):
        self.client = VescUartClient(port, timeout_s=0.25)
        try:
            self._initialize()
        except BaseException:
            self.client.close()
            raise

    def _initialize(self):
        self.client.response_timeout_s = 2
        self.fw = asdict(self.client.fw_version())
        if self.fw != {"major": 6, "minor": 2, "hardware": "MKSESC_84_100_HP"}:
            self.client.close()
            raise ValueError(f"Unsupported controller: {self.fw}")
        self.motor = self.client.get_raw_config("motor")
        self.app = self.client.get_raw_config("app")
        self.values = decode_config(self.motor, "motor")
        decode_config(self.app, "app")
        self.motion = EncoderMotion(self.values["foc_encoder_ratio"], -1 if self.values["foc_encoder_inverted"] else 1)
        self.active = False
        self.isolated = False
        self.modified = False

    def encoder_diagnostics(self) -> str:
        self.client.send_payload(bytes((20,)) + b"encoder")
        lines = []
        deadline = monotonic() + 2
        while monotonic() < deadline:
            line = self.client.read_response(21)[1:].decode("utf-8", errors="replace").strip()
            if not line:
                break
            lines.append(line)
        return "\n".join(lines)

    def snapshot(self, path: Path) -> None:
        path.mkdir()
        (path / "mcconf.bin").write_bytes(self.motor)
        (path / "appconf.bin").write_bytes(self.app)
        for kind, data in (("motor", self.motor), ("app", self.app)):
            export_xml(data, kind, path / f"vesc_{'mcconf' if kind == 'motor' else 'appconf'}.xml")
        write_json(path / "manifest.json", {"firmware": self.fw, "files": {
            "motor": {"path": "mcconf.bin", "sha256": sha256(self.motor)},
            "app": {"path": "appconf.bin", "sha256": sha256(self.app)},
        }})

    def prepare(self, plan: BenchPlan) -> None:
        plan.validate()
        self.rollback_timeout_s = plan.rollback_timeout_s
        v = self.values
        if v["motor_type"] != 2 or v["foc_sensor_mode"] != 1 or v["m_sensor_port_mode"] != 2:
            raise BenchStop("This campaign requires FOC with an AS504x SPI encoder")
        if not 1 <= v["foc_encoder_ratio"] <= 30:
            raise BenchStop("Invalid encoder ratio")
        if v["foc_motor_l"] <= 0 or v["foc_motor_r"] <= 0 or v["foc_motor_ld_lq_diff"] == 0:
            raise BenchStop("Missing motor R/L/saliency measurements")
        if plan.max_erpm >= v["foc_sl_erpm"] * 0.75:
            raise BenchStop("Test speed must stay below encoder-to-observer transition")
        if v["foc_fw_current_max"] != 0:
            raise BenchStop("Disable field weakening before startup tests")
        self.client.stream_encoder(True)
        self.active = True
        # No ADC/PPM writer can compete with USB commands during an experiment.
        app = patch_config(self.app, "app", {"app_to_use": 0, "timeout_msec": 300, "timeout_brake_current": 0})
        self.client.set_app_config_temporary(app)
        if self.client.get_raw_config("app") != app:
            raise BenchStop("Temporary application configuration read-back mismatch")
        self.isolated = True
        self.stop()
        diagnostics = self.encoder_diagnostics()
        match = re.search(r"error rate:\s*([\d.]+)\s*%", diagnostics)
        if not match or float(match[1]) > 1:
            raise BenchStop(f"Encoder SPI diagnostics failed: {diagnostics}")

    def apply(self, changes: dict) -> None:
        data = patch_config(self.motor, "motor", changes)
        validate_motor_math(decode_config(data, "motor"))
        self.modified = True
        self.client.set_raw_config("motor", data)
        self.client.read_response(13)
        if self.client.get_raw_config("motor") != data:
            raise BenchStop("Motor configuration read-back mismatch")

    def current(self, value: float) -> None:
        self.client.set_current(value)

    def rpm(self, value: float) -> None:
        self.client.set_rpm(value)

    def openloop(self, current: float, erpm: float) -> None:
        if not 0 <= current <= 15 or not 0 < erpm <= 180:
            raise ValueError("Open-loop diagnostic bounds exceeded")
        if current < .05:
            self.stop()
        else:
            command = f"foc_openloop {current:.3f} {erpm:.3f}".encode("ascii")
            self.client.send_payload(bytes((20,)) + command)

    def stop(self) -> None:
        self.client.set_current(0)

    def sample(self) -> dict:
        v = asdict(self.client.get_values())
        points = list(self.client.rotor_samples)
        self.client.rotor_samples.clear()
        self.motion.update(points, batched=True)
        v.update(encoder_angle=self.client.rotor_angle,
                 encoder_age=monotonic() - self.client.rotor_received_at,
                 encoder_erpm=self.motion.speed, turns=self.motion.turns)
        return v

    def export(self, changes: dict, path: Path) -> None:
        path.mkdir(exist_ok=True)
        data = patch_config(self.motor, "motor", changes)
        (path / "mcconf.bin").write_bytes(data)
        export_xml(data, "motor", path / "vesc_mcconf.xml")
        write_json(path / "manifest.json", {"firmware": self.fw, "changes": changes, "files": {
            "motor": {"path": "mcconf.bin", "sha256": sha256(data)},
        }})

    def close(self) -> dict:
        output_state = "disabled until power cycle" if self.isolated else ("unverified" if self.active else "unchanged")
        report = {"motor_restored": not self.modified, "app_output": output_state}
        try:
            if self.active:
                self.stop()
            if self.modified:
                # Never rewrite motor parameters while the rotor is coasting.
                timeout = getattr(self, 'rollback_timeout_s', 30)
                report['standstill_timeout_s'] = timeout
                deadline = monotonic() + timeout
                stationary_since = None
                while monotonic() < deadline:
                    self.stop()
                    sleep(.03)
                    v = self.sample()
                    if v["encoder_age"] > .25:
                        raise BenchStop("Cannot verify standstill for rollback: stale encoder")
                    if abs(v["encoder_erpm"]) < 20 and abs(v["current_motor_a"]) < .5:
                        stationary_since = stationary_since or monotonic()
                        if monotonic() - stationary_since >= .4:
                            break
                    else:
                        stationary_since = None
                else:
                    raise BenchStop("Cannot verify standstill for rollback")
                self.client.set_raw_config("motor", self.motor)
                self.client.read_response(13)
                report["motor_restored"] = self.client.get_raw_config("motor") == self.motor
                if not report["motor_restored"]:
                    report["error"] = "Motor rollback read-back mismatch"
            if self.active:
                self.client.stream_encoder(False)
        except Exception as exc:
            report["error"] = str(exc)
        finally:
            self.client.close()
        return report


class SimulatedBench:
    """Deterministic plant for exercising the same controller and journal code."""
    def __init__(self, fault: str = ""):
        self.fault = fault
        self.values = {"foc_encoder_offset": 267.53, "s_pid_kp": .004, "s_pid_ki": .004, "foc_encoder_ratio": 2}
        self.settings = {}
        self.speed = self.turns = self.command = self.target = 0.0
        self.mode = "current"
        self.time = 0.0
        self.stopped = False

    def snapshot(self, path: Path) -> None:
        path.mkdir()
        write_json(path / "simulation.json", {"simulated": True, "fault": self.fault})

    def prepare(self, plan: BenchPlan) -> None:
        self.plan = plan

    def apply(self, changes: dict) -> None:
        self.settings = changes

    def current(self, value: float) -> None:
        self.mode, self.command = "current", value

    def rpm(self, value: float) -> None:
        self.mode, self.target = "rpm", value

    def stop(self) -> None:
        self.current(0)
        self.stopped = True

    def sample(self) -> dict:
        dt = self.plan.sample_s
        self.time += dt
        if self.fault == "disconnect" and self.command:
            raise OSError("Simulated USB disconnect")
        gain = 1 if self.settings.get("foc_mtpa_mode") else 0
        offset = self.settings.get("foc_encoder_offset", 267.53) - 267.53
        gain *= max(0, math.cos(math.radians(offset - 15)))
        current = self.command
        if self.mode == "rpm":
            current = max(-self.plan.phase_limit_a, min(self.plan.phase_limit_a, (self.target - self.speed) * .03))
        if self.fault == "stall":
            gain = 0
        if self.fault == "no_current":
            current = 0
        direction = -1 if self.fault == "reverse" else 1
        self.speed += (direction * current * 150 * gain - self.speed * 1.5) * dt
        self.turns += self.speed * dt / 120
        return dict(temp_mos_c=75 if self.fault == "hot" else 28, temp_motor_c=30,
                    current_motor_a=current, current_in_a=abs(current)*.08,
                    id_a=-abs(current)*.707*gain, iq_a=current*.707,
                    duty=abs(self.speed)/3000, erpm=round(self.speed), v_in=24.7,
                    fault_code=3 if self.fault == "fault" else 0,
                    encoder_angle=self.turns*360 % 360, encoder_age=1 if self.fault == "stale" else 0,
                    encoder_erpm=self.speed, turns=self.turns)

    def export(self, changes: dict, path: Path) -> None:
        path.mkdir(exist_ok=True)
        write_json(path / "simulation-only.json", changes)

    def close(self) -> dict:
        self.stop()
        return {"motor_restored": True, "simulated": True}


def guard(v: dict, p: BenchPlan) -> None:
    if any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in v.values()):
        raise BenchStop("Missing or non-finite telemetry")
    if v["encoder_age"] > .25:
        raise BenchStop("Encoder stream stale")
    if 'observer_error_age' in v:
        if v['observer_error_age'] > .1 or abs(v['observer_error_deg']) > 180:
            raise BenchStop('Observer angle stream stale or invalid')
    if v["fault_code"]:
        raise BenchStop(f"VESC fault {v['fault_code']}")
    if max(abs(v["current_motor_a"]), math.hypot(v["id_a"], v["iq_a"])) > p.trip_current_a:
        raise BenchStop("Phase current trip")
    if abs(v["current_in_a"]) > p.input_limit_a * 1.3 + .5:
        raise BenchStop("Input current trip")
    if max(abs(v["erpm"]), abs(v["encoder_erpm"])) > p.max_erpm:
        raise BenchStop("Overspeed")
    if abs(v["duty"]) > p.max_duty or not p.min_voltage <= v["v_in"] <= p.max_voltage:
        raise BenchStop("Duty or bus voltage outside limits")
    if v["temp_mos_c"] > p.max_mos_temp or v["temp_motor_c"] > p.max_motor_temp:
        raise BenchStop("Overtemperature")
    if v["temp_motor_c"] < -20 and not p.allow_missing_motor_temp:
        raise BenchStop("Motor temperature sensor unavailable")


def validate_motor_math(values: dict) -> None:
    flux = values["foc_motor_flux_linkage"]
    if values["foc_mtpa_mode"] and flux < 0:
        raise BenchStop("Negative flux linkage makes low-current MTPA undefined in firmware 6.02")
    if flux == 0 and values["foc_sat_comp_mode"] in (2, 3) and values["foc_observer_type"] >= 2:
        raise BenchStop("Zero flux with lambda saturation compensation divides by zero")


class Campaign:
    def __init__(self, bench, plan: BenchPlan, output: Path, simulated: bool = False):
        plan.validate()
        self.bench, self.p, self.output, self.simulated = bench, plan, output, simulated
        self.results = []
        self.energy = 0.0
        self.start = monotonic()
        self.state = "created"
        self.best = None
        self.sequence = 0

    def journal(self, **extra) -> None:
        write_json(self.output / "status.json", {"state": self.state, "simulated": self.simulated,
            "energy_j": self.energy, "results": self.results, "best": self.best,
            "startup_coverage": startup_coverage(self.results), **extra})

    def check_stop(self) -> None:
        if (self.output / "STOP").exists():
            raise BenchStop("Operator STOP file")
        if monotonic() - self.start > self.p.max_duration_s:
            raise BenchStop("Campaign time budget reached")
        if self.energy >= self.p.total_energy_j:
            raise BenchStop("Campaign energy budget reached")

    def pause(self) -> None:
        if not self.simulated:
            sleep(self.p.sample_s)

    def settle(self) -> None:
        self.bench.stop()
        quiet = 0.0
        last_turn = None
        count = math.ceil(self.p.settle_timeout_s / self.p.sample_s)
        for _ in range(count):
            self.check_stop()
            self.bench.stop()
            self.pause()
            v = self.bench.sample()
            guard(v, self.p)
            moved = last_turn is not None and abs(v["turns"] - last_turn) > .001
            last_turn = v["turns"]
            quiet = quiet + self.p.sample_s if not moved and abs(v["encoder_erpm"]) < 20 and abs(v["current_motor_a"]) < .5 else 0
            if quiet >= max(.4, self.p.cooldown_s):
                return
        raise BenchStop("Rotor did not stop before the next configuration")

    def trial(self, name: str, changes: dict, speed: bool = False, openloop_erpm: float | None = None) -> dict:
        self.check_stop()
        if self.sequence >= self.p.max_trials:
            raise BenchStop("Trial budget reached")
        self.settle()
        self.sequence += 1
        self.state = "testing"
        self.journal(active=name)
        folder = self.output / f"{self.sequence:02d}_{name}"
        folder.mkdir()
        write_json(folder / "changes.json", changes)
        self.bench.export(changes, folder / "profile")
        row = {"name": name, "changes": changes, "stage": "openloop" if openloop_erpm else ("speed" if speed else "startup"), "ok": False}
        samples = []
        energy = i2t = quiet = moving = no_current = 0.0
        elapsed = 0.0
        started_at = monotonic()
        previous_at = started_at
        origin = None
        max_turn = 0.0
        success_at = None
        status = "no_start"
        duration = self.p.speed_hold_s * len(self.p.speed_targets) if speed else self.p.trial_s
        duration = min(duration, self.p.trial_s)
        try:
            self.bench.apply(changes)
            initial = self.bench.sample()
            guard(initial, self.p)
            origin = initial['turns']
            row['start_angle'] = initial['encoder_angle']
            started_at = previous_at = monotonic()
            while elapsed < duration:
                self.check_stop()
                if openloop_erpm:
                    command = self.p.test_current_a * min(1, elapsed / self.p.ramp_s)
                    target = openloop_erpm
                    self.bench.openloop(command, target)
                elif speed:
                    segment_s = duration / len(self.p.speed_targets)
                    target = self.p.speed_targets[min(int(elapsed / segment_s), len(self.p.speed_targets)-1)] * self.p.direction
                    self.bench.rpm(target)
                    command = 0.0
                else:
                    command = self.p.direction * self.p.test_current_a * min(1, elapsed / self.p.ramp_s)
                    target = self.p.startup_erpm * self.p.direction
                    self.bench.current(command)
                self.pause()
                v = self.bench.sample()
                now = monotonic()
                dt = self.p.sample_s if self.simulated else now - previous_at
                previous_at = now
                elapsed += dt
                energy += max(0, v["v_in"] * v["current_in_a"]) * dt
                self.energy += max(0, v["v_in"] * v["current_in_a"]) * dt
                i2t += (v["id_a"]**2 + v["iq_a"]**2) * dt
                sample = {"t": elapsed, "command_a": command, "target_erpm": target, **v}
                samples.append(sample)
                guard(v, self.p)
                if not self.simulated and dt > .2:
                    raise BenchStop("Telemetry latency exceeds control deadline")
                if energy > self.p.trial_energy_j or i2t > self.p.trial_i2t:
                    raise BenchStop("Trial energy or I2t budget exceeded")
                measured_current = math.hypot(v["id_a"], v["iq_a"])
                if not speed and abs(command) >= 1 and measured_current < .15:
                    no_current += dt
                    if no_current >= .4:
                        raise BenchStop("Command not realized: motor current remains near zero")
                else:
                    no_current = 0
                if not openloop_erpm and v["encoder_erpm"] * self.p.direction < -40:
                    status = "wrong_direction"
                    break
                if origin is None:
                    origin = v["turns"]
                    row["start_angle"] = v["encoder_angle"]
                travel = (v["turns"] - origin) * self.p.direction
                row["signed_turns"] = v["turns"] - origin
                if openloop_erpm:
                    travel = abs(travel)
                if travel > max_turn + .005:
                    max_turn, quiet = travel, 0
                elif elapsed > self.p.ramp_s:
                    quiet += dt
                if quiet > self.p.stall_s:
                    status = "stalled"
                    break
                moving = moving + dt if v["encoder_erpm"] * self.p.direction >= self.p.startup_erpm else 0
                if not speed and not openloop_erpm and moving >= .2 and travel >= .1:
                    success_at, status = elapsed, "completed"
                    break
                if speed and elapsed >= duration:
                    status = "completed"
                if openloop_erpm and elapsed >= duration:
                    status = "observed_motion" if travel >= .1 else "no_start"
            row.update(status=status, ok=status == "completed", startup_s=success_at, energy_j=energy,
                       i2t=i2t, turns=max_turn, samples=len(samples), duration_s=elapsed,
                       max_measured_current_a=max((math.hypot(s["id_a"], s["iq_a"]) for s in samples), default=0))
            if speed and samples:
                errors = [s["encoder_erpm"] - s["target_erpm"] for s in samples]
                row["rmse_erpm"] = math.sqrt(statistics.mean(e*e for e in errors))
                row["rms_current_a"] = math.sqrt(statistics.mean(s["id_a"]**2 + s["iq_a"]**2 for s in samples))
                row["ok"] = row["ok"] and row["rmse_erpm"] < max(self.p.speed_targets) * .35
                row['speed_steps'] = speed_steps(samples)
                row['speed_qualified'] = (status == 'completed'
                    and len(row['speed_steps']) == len(self.p.speed_targets)
                    and all(step['qualified'] for step in row['speed_steps']))
                if self.p.qualify_speed:
                    row['ok'] = row['speed_qualified']
                    if status == 'completed' and not row['ok']:
                        row['status'] = 'speed_unqualified'
            if samples and 'observer_error_deg' in samples[0]:
                from .observer_bench import summarize_observer_error
                row['observer_comparison'] = summarize_observer_error(samples)
            return row
        except BaseException as exc:
            row.update(status="aborted", error=str(exc) or type(exc).__name__, energy_j=energy, i2t=i2t)
            raise
        finally:
            try:
                self.bench.stop()
            finally:
                if samples:
                    with (folder / "telemetry.csv").open("w", newline="", encoding="utf-8") as handle:
                        writer = csv.DictWriter(handle, fieldnames=list(samples[0]))
                        writer.writeheader()
                        writer.writerows(samples)
                self.results.append(row)
                write_json(folder / "result.json", row)
                self.journal()

    def common(self) -> dict:
        model = {"foc_motor_flux_linkage": 0, "foc_sat_comp_mode": 0, "foc_observer_type": 0} if self.p.synrm_zero_flux else {}
        return {**model, "l_current_max": self.p.phase_limit_a, "l_current_min": -self.p.phase_limit_a,
                "l_in_current_max": self.p.input_limit_a, "l_in_current_min": 0,
                "l_abs_current_max": self.p.trip_current_a,
                "l_min_erpm": -self.p.max_erpm, "l_max_erpm": self.p.max_erpm,
                "l_max_duty": self.p.max_duty, "s_pid_min_erpm": 30,
                "s_pid_allow_braking": 0, "s_pid_ramp_erpms_s": self.p.speed_ramp_erpm_s,
                "foc_speed_soure": 0}

    def run(self) -> Path:
        self.output.mkdir(parents=True, exist_ok=False)
        failure = None
        try:
            write_json(self.output / "plan.json", asdict(self.p))
            self.bench.snapshot(self.output / "baseline")
            self.state = "preflight"
            self.journal()
            self.bench.prepare(self.p)
            self.settle()
            base = self.common()
            candidates = []
            # Try MTPA before offset changes. Only promote successful starts.
            for delta in self.p.offset_deltas:
                modes = (0, 1) if delta == 0 else (1,)
                for mode in modes:
                    c = {**base, "foc_mtpa_mode": mode,
                         "foc_encoder_offset": (self.bench.values["foc_encoder_offset"] + delta) % 360}
                    result = self.trial(f"start_m{mode}_offset{delta:+g}", c)
                    if result["ok"]:
                        candidates.append(result)
            if not candidates:
                self.state = "no_reliable_start"
                return self.output
            candidates.sort(key=lambda r: (r["startup_s"], r["energy_j"]))
            validated = None
            for candidate in candidates[:2]:
                repeats = [candidate]
                for n in range(self.p.repeats - 1):
                    r = self.trial(f"repeat{n+1}_{candidate['name']}", candidate["changes"])
                    repeats.append(r)
                    if not r["ok"]:
                        break
                if len(repeats) == self.p.repeats and all(r["ok"] for r in repeats):
                    validated = candidate
                    break
            if validated is None:
                self.state = "no_repeatable_start"
                return self.output
            self.best = {"stage": "startup", "changes": validated["changes"], "validated_repeats": self.p.repeats}
            self.bench.export(self.best["changes"], self.output / "best-startup")
            speed_results = []
            for scale in (.5, 1.0, 1.5):
                if speed_results and self.p.total_energy_j - self.energy < speed_results[-1]["energy_j"] * 2.2:
                    break
                c = {**validated["changes"],
                     "s_pid_kp": self.bench.values["s_pid_kp"] * scale,
                     "s_pid_ki": self.bench.values["s_pid_ki"] * scale}
                r = self.trial(f"speed_gain{scale:g}", c, speed=True)
                if r["ok"]:
                    speed_results.append(r)
            if speed_results:
                winner = min(speed_results, key=lambda r: (r["rmse_erpm"], r["energy_j"]))
                confirmation = self.trial("speed_confirmation", winner["changes"], speed=True)
                if confirmation["ok"]:
                    self.best = {"stage": "speed", "changes": winner["changes"],
                                 "rmse_erpm": confirmation["rmse_erpm"], "validated_repeats": self.p.repeats}
                    self.bench.export(self.best["changes"], self.output / "recommended")
            self.state = "completed" if self.best["stage"] == "speed" else "startup_only"
        except (Exception, KeyboardInterrupt) as exc:
            failure = str(exc) or type(exc).__name__
            self.state = "stopped"
        finally:
            cleanup = self.bench.close()
            if cleanup.get("error") or not cleanup.get("motor_restored"):
                self.state = "recovery_required"
            self.journal(reason=failure, cleanup=cleanup)
            self.report(failure, cleanup)
            with (self.output / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["name", "stage", "ok", "status", "startup_s", "energy_j", "i2t", "rmse_erpm", "rms_current_a", "start_angle", "error"], extrasaction="ignore")
                writer.writeheader()
                writer.writerows(self.results)
        return self.output

    def report(self, reason, cleanup):
        lines = ["# Encoder Bench Report", "", f"State: {self.state}",
                 f"Simulated: {self.simulated}", f"Energy: {self.energy:.3f} J", "",
                 "| Trial | Result | Start (s) | Energy (J) |", "|---|---|---:|---:|"]
        for r in self.results:
            start = r.get("startup_s")
            lines.append(f"| {r['name']} | {r.get('status', 'unknown')} | {start if start is not None else '-'} | {r.get('energy_j', 0):.3f} |")
        lines += ['', '## Startup coverage', '',
                  '```json', json.dumps(startup_coverage(self.results), indent=2), '```', '',
                  '## Steady speed steps', '',
                  '| Trial | Target eRPM | Mean eRPM | Peak error | Drift eRPM/s | Qualified |',
                  '|---|---:|---:|---:|---:|---|']
        for r in self.results:
            for step in r.get('speed_steps', []):
                lines.append(f"| {r['name']} | {step['target_erpm']} | {step['mean_erpm']:.2f} | "
                             f"{step['peak_error_erpm']:.2f} | {step['drift_erpm_s']:.2f} | {step['qualified']} |")
        comparisons = [r for r in self.results if 'observer_comparison' in r]
        if comparisons:
            lines += ['', '## Observer angle screening', '',
                      '| Trial | Circular concentration | P95 absolute error (deg) | Angle screen |',
                      '|---|---:|---:|---|']
            for r in comparisons:
                o = r['observer_comparison']
                lines.append(f"| {r['name']} | {o.get('resultant', 'n/a')} | "
                             f"{o.get('p95_absolute_error_deg', 'n/a')} | {o.get('passes_angle_screen', False)} |")
            lines += ['', 'Successful speed control does not qualify the observer. Sensorless was not selected.']
        lines += ["", f"Stop reason: {reason or 'none'}", f"Rollback: {json.dumps(cleanup)}", "",
                  "A recommended profile is valid only within the tested speed/current envelope.",
                  "These trials measure no-load startup and speed response, not shaft torque or motor efficiency.",
                  "The original motor settings are restored at exit when standstill is confirmed.",
                  "On hardware, ADC/PPM output remains temporarily disabled until power cycle."]
        (self.output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def add_commands(subparsers) -> None:
    cmd = subparsers.add_parser("bench", help="Direct-encoder experiment controller")
    sub = cmd.add_subparsers(dest="bench_action", required=True)
    inspect = sub.add_parser("inspect", help="Read firmware, raw configuration and telemetry without driving")
    inspect.add_argument("--port", default="auto")
    inspect.add_argument("--output", required=True)
    inspect.set_defaults(func=cli_inspect)
    run = sub.add_parser("run", help="Run a bounded startup and speed campaign")
    run.add_argument("--plan", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--port", default="auto")
    modes = run.add_mutually_exclusive_group(required=True)
    modes.add_argument("--simulate", action="store_true")
    modes.add_argument("--armed", action="store_true")
    run.set_defaults(func=cli_run)
    for action in ("status", "stop"):
        p = sub.add_parser(action)
        p.add_argument("output")
        p.set_defaults(func=cli_status_stop)


def cli_inspect(args) -> int:
    bench = HardwareBench(find_port() if args.port == "auto" else args.port)
    try:
        bench.snapshot(Path(args.output))
        data = {"firmware": bench.fw, "motor": bench.values, "telemetry": asdict(bench.client.get_values())}
        write_json(Path(args.output) / "inspection.json", data)
        print(json.dumps(data, indent=2))
    finally:
        bench.close()
    return 0


def cli_run(args) -> int:
    plan = load_plan(Path(args.plan))
    output = Path(args.output)
    if output.exists():
        raise ValueError("Use a new output directory for every campaign")
    bench = SimulatedBench() if args.simulate else HardwareBench(find_port() if args.port == "auto" else args.port)
    try:
        result = Campaign(bench, plan, output, args.simulate).run()
    except BaseException:
        bench.close()
        raise
    status = json.loads((result / "status.json").read_text(encoding="utf-8"))
    print(json.dumps({"output": str(result), "state": status["state"], "best": status["best"]}, indent=2))
    return 0 if status["state"] in ("completed", "startup_only") else 2


def cli_status_stop(args) -> int:
    path = Path(args.output)
    if args.bench_action == "stop":
        if not (path / "status.json").exists():
            raise ValueError("Not a campaign directory")
        (path / "STOP").touch()
        print("Stop requested; the runner will release motor current.")
    else:
        print((path / "status.json").read_text(encoding="utf-8"))
    return 0
