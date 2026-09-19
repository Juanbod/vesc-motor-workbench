"""A single 0.5 A / 40 ms fixed-phase physical excitation, never a speed test."""
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter as monotonic, sleep

from .fixture import PROBE_LIMITS, locked_probe_permit, require_locked
from .uart import VescUartClient
from .wire_config import decode_config


class ProbeClient(VescUartClient):
    def __init__(self, *args, **kwargs):
        self.prints = []
        super().__init__(*args, **kwargs)

    def read_payload(self):
        payload = super().read_payload()
        if payload and payload[0] == 21:
            self.prints.append(dict(t=monotonic(), text=payload[1:].decode("utf-8", errors="replace").strip()))
        return payload


def preflight_config(fw, motor, app):
    if fw != dict(major=6, minor=2, hardware="MKSESC_84_100_HP"):
        raise ValueError("Unexpected firmware/hardware; no probe")
    m, a = decode_config(motor, "motor"), decode_config(app, "app")
    if a["app_to_use"] != 0 or not 50 <= a["timeout_msec"] <= 300 or a["timeout_brake_current"] != 0:
        raise ValueError("Application must already be isolated with <=300 ms zero-brake watchdog")
    if (m["motor_type"] != 2 or m["foc_mtpa_mode"] != 0 or m["foc_sensor_mode"] != 1
            or m["m_sensor_port_mode"] != 2 or m["p_pid_ang_div"] != 1):
        raise ValueError("Expected FOC + AS504x encoder, divider 1 and no MTPA")
    if not 0 < m["cc_min_current"] < .5:
        raise ValueError("Probe command would be below minimum current")
    if not .015 <= m["foc_current_kp"] <= .03 or not 10 <= m["foc_current_ki"] <= 16:
        raise ValueError("Current gains differ from the reviewed low-energy setup")
    if not 1e-5 <= m["foc_motor_l"] <= 4e-5 or not .005 <= m["foc_motor_r"] <= .03:
        raise ValueError("Unexpected motor R/L")
    return m, a


def check_sample(row, origin):
    for key, value in row.items():
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Unavailable/nonfinite telemetry: {key}")
    if row["fault_code"] != 0:
        raise ValueError(f"Controller fault {row['fault_code']}")
    if not 18 <= row["v_in"] <= 30 or row["temp_mos_c"] > 50:
        raise ValueError("Unexpected bus voltage or controller temperature")
    if max(abs(row["current_motor_a"]), math.hypot(row["id_a"], row["iq_a"])) > 1.5:
        raise ValueError("Observed current exceeds 1.5 A diagnostic threshold")
    if abs(row["duty"]) > .1 or abs(row["erpm"]) > 20:
        raise ValueError("Unexpected duty/speed for locked probe")
    if not 0 <= row["position_deg"] < 360:
        raise ValueError("Invalid encoder position")
    if abs((row["position_deg"] - origin + 180) % 360 - 180) > .5:
        raise ValueError("Locked rotor moved more than 0.5 mechanical degrees")


def run_probe(client, output, resume_baseline=None):
    """Own cleanup for the one probe; caller owns and closes the serial handle."""
    require_locked()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(test="locked_fixed_phase_0p5a_40ms", simulated=False,
                  pulse_sent=False, motor_restored=False, motor_write_attempted=False,
                  current_returned_to_zero=False,
                  inductance_measured=False, offset_calibrated=False,
                  limits=PROBE_LIMITS, measured_current_threshold_a=1.5)
    start = monotonic()
    samples = []
    baseline = app = None
    failure = None

    with (output / "samples.jsonl").open("x", encoding="utf-8") as log:
        def sample(stage, origin=None):
            requested = monotonic()
            values = asdict(client.get_values())
            row = {**values, "position_deg": client.pid_position, "t": monotonic() - start}
            record = {**row, "stage": stage, "request_latency_s": monotonic() - requested}
            log.write(json.dumps(record, allow_nan=False) + "\n")
            log.flush()
            samples.append(record)
            if record["request_latency_s"] > .1:
                raise ValueError("Telemetry latency exceeded 100 ms")
            check_sample(row, row["position_deg"] if origin is None else origin)
            return row

        try:
            fw = asdict(client.fw_version())
            entry, app = client.get_raw_config("motor"), client.get_raw_config("app")
            baseline = Path(resume_baseline).read_bytes() if resume_baseline else entry
            preflight_config(fw, baseline, app)
            preflight_config(fw, entry, app)
            (output / "mcconf-entry.bin").write_bytes(entry)
            report["firmware"] = fw
            report["baseline_sha256"] = hashlib.sha256(baseline).hexdigest()
            (output / "mcconf-before.bin").write_bytes(baseline)
            (output / "appconf-before.bin").write_bytes(app)
            # No-argument invocation only queries the command's usage; it cannot
            # reach the excitation branch in the reviewed firmware.
            client.send_payload(b"\x14rotor_lock_openloop")
            for _ in range(3):
                reply = client.read_response(21)[1:].decode("utf-8", errors="replace").strip()
                if reply == "This command requires three arguments. [current time angle]":
                    break
                if reply != "-> rotor_lock_openloop":
                    raise ValueError(f"Timed command not recognized: {reply}")
            else:
                raise ValueError("No usage confirmation after terminal echo")
            report["command_usage_verified"] = True
            origin = sample("preflight")["position_deg"]
            quiet = []
            until = monotonic() + .4
            while monotonic() < until:
                quiet.append(sample("preflight", origin))
                sleep(.015)
            with locked_probe_permit(baseline) as permit:
                permit.verify_stopped(quiet)
                if resume_baseline:
                    permit.adopt_existing_limits(entry)
                    report["resumed_protective_config"] = True
                    report["motor_write_attempted"] = True
                try:
                    (output / "mcconf-protective.bin").write_bytes(permit.limited)
                    if not resume_baseline:
                        report["motor_write_attempted"] = True
                        client.set_raw_config("motor", permit.limited)
                        client.read_response(13)
                    permit.verify_limits(client.get_raw_config("motor"))
                    if client.get_raw_config("app") != app:
                        raise ValueError("Application changed before the probe")
                    # Leave time after the flash/configuration operation and
                    # verify quiet telemetry again before the single command.
                    quiet = []
                    until = monotonic() + .4
                    while monotonic() < until:
                        quiet.append(sample("limited_idle", origin))
                        sleep(.015)
                    permit.verify_stopped(quiet)
                    if (output / "STOP").exists():
                        raise ValueError("STOP file is present")
                    report["pulse_command"] = permit.pulse[1:].decode("ascii")
                    report["pulse_t"] = monotonic() - start
                    # Persist the attempted dispatch before serial I/O. A failed
                    # write can still mean the controller received the command.
                    report["dispatch_attempted"] = True
                    (output / "dispatch.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                    client.send_payload(permit.pulse)
                    report["pulse_sent"] = True
                    until = monotonic() + .6
                    while monotonic() < until:
                        if (output / "STOP").exists():
                            raise ValueError("STOP requested")
                        sample("probe", origin)
                        sleep(.001)
                    pulse_prints = [p for p in client.prints if p["t"] >= start + report["pulse_t"]]
                    report["firmware_completion_received"] = any(p["text"] == "Done" for p in pulse_prints)
                    if not report["firmware_completion_received"]:
                        raise ValueError("Timed command did not report completion")
                finally:
                    # The timed command may reassert current until its short
                    # loop ends. Repeated zero commands cover that bounded tail;
                    # never send ALIVE and never start a second excitation.
                    report["pulse_consumed_by_interlock"] = permit.pulse_sent
                    zero_samples = []
                    until = monotonic() + .65
                    while monotonic() < until:
                        client.set_current(0)
                        row = sample("stopping", origin)
                        if abs(row["current_motor_a"]) <= .1 and abs(row["duty"]) <= .001:
                            zero_samples.append(row)
                        else:
                            zero_samples.clear()
                        sleep(.015)
                    permit.verify_stopped(zero_samples)
                    report["current_returned_to_zero"] = True
                    if permit.setup_sent:
                        client.set_raw_config("motor", baseline)
                        client.read_response(13)
                        report["motor_restored"] = client.get_raw_config("motor") == baseline
                        if not report["motor_restored"]:
                            raise ValueError("Baseline restoration readback mismatch")
                    report["app_unchanged"] = client.get_raw_config("app") == app
                    if not report["app_unchanged"]:
                        raise ValueError("Application configuration changed")
        except (Exception, KeyboardInterrupt) as exc:
            failure = str(exc) or type(exc).__name__
            # Even failures before the limited-write scope get an explicit
            # zero-current attempt. This does not renew an excitation command.
            try:
                client.set_current(0)
            except Exception as stop_exc:
                report["stop_error"] = str(stop_exc)
        finally:
            report["motor_unchanged"] = not report["motor_write_attempted"]
            if report["motor_unchanged"]:
                report["motor_restored"] = True
            report["failure"] = failure
            report["terminal_output"] = client.prints
            probe_samples = [s for s in samples if s["stage"] == "probe"]
            peak = max((max(abs(s["current_motor_a"]), math.hypot(s["id_a"], s["iq_a"]))
                        for s in probe_samples), default=0)
            report["peak_sampled_current_a"] = peak
            report["sample_count"] = len(samples)
            report["nonzero_current_observed"] = peak >= .1
            report["physical_excitation_verified"] = bool(report["pulse_sent"] and peak >= .1)
            report["ok"] = bool(not failure and report["physical_excitation_verified"]
                                and report["current_returned_to_zero"] and report["motor_restored"])
            if not failure and not report["physical_excitation_verified"]:
                report["failure"] = "No nonzero current captured; do not call this a verified physical excitation"
            (output / "result.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report
