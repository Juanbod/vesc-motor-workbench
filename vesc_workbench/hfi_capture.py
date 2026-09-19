"""Stock 6.02 raw HFI acquisition and independent saliency-axis analysis."""
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
from time import perf_counter as monotonic, sleep

from .fixture import locked_hfi_permit, require_locked, verify_encoder_quiet
from .locked_probe import ProbeClient, preflight_config
from .locked_rotor import _fit, _axial_mean, axial_delta


class PlotDecoder:
    """Normal finite float32_auto values use IEEE-754 big-endian encoding."""
    def __init__(self, mode=2):
        self.mode = mode
        self.graph = None
        self.generation = 0
        self.points = []
        self.names = []

    def feed(self, payload, stamp):
        if not payload:
            return
        if payload[0] == 75:  # COMM_PLOT_INIT
            self.generation += 1
            self.graph = None
            self.names = []
        elif payload[0] == 77:  # COMM_PLOT_ADD_GRAPH
            self.names.append(payload[1:].rstrip(b"\0").decode("utf-8", errors="replace"))
        elif payload[0] == 78:
            if len(payload) != 2 or payload[1] not in (range(5) if self.mode == 1 else range(2)):
                raise ValueError("Unexpected raw HFI plot graph")
            self.graph = payload[1]
        elif payload[0] == 76:
            if len(payload) != 9 or self.graph is None:
                raise ValueError("Malformed/unlabelled HFI plot point")
            x, y = struct.unpack(">ff", payload[1:])
            if not math.isfinite(x) or not math.isfinite(y) or x != int(x) or not 0 <= x < (100000 if self.mode == 1 else 32):
                raise ValueError("Invalid HFI sample index/value")
            self.points.append(dict(t=stamp, index=int(x), value=y, graph=self.graph,
                                    generation=self.generation))


class HfiClient(ProbeClient):
    def __init__(self, *args, plot_mode=2, **kwargs):
        self.plot = PlotDecoder(plot_mode)
        self.packet_log = None
        super().__init__(*args, **kwargs)

    def read_payload(self):
        payload = super().read_payload()
        stamp = monotonic()
        if self.packet_log:
            self.packet_log.write(json.dumps(dict(t=stamp, payload_hex=payload.hex())) + "\n")
            self.packet_log.flush()
        self.plot.feed(payload, stamp)
        return payload


def write_motor_verified(client, data):
    # The firmware sleeps 200 ms AFTER storing flash. This operation-specific
    # timeout must not be confused with the live telemetry latency limit.
    old = client.serial.timeout
    try:
        client.serial.timeout = 2
        client.set_raw_config("motor", data)
        client.read_response(13)
        actual = client.get_raw_config("motor")
    finally:
        client.serial.timeout = old
    if actual != data:
        raise ValueError("Exact configuration readback mismatch")
    return actual


def terminal_expect(client, command, expected):
    client.send_payload(b"\x14" + command.encode("ascii"))
    deadline = monotonic() + 2
    while monotonic() < deadline:
        payload = client.read_payload()
        if payload and payload[0] == 21:
            line = payload[1:].decode("utf-8", errors="replace").strip()
            if line == expected:
                return
            if line == "-> " + command:
                continue
            raise ValueError(f"Unexpected terminal response: {line}")
    raise ValueError(f"No terminal confirmation: {command}")


def guard_sample(row, origin):
    for key, value in row.items():
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Unavailable telemetry: {key}")
    if not 0 <= row["position_deg"] < 360 or abs((row["position_deg"] - origin + 180) % 360 - 180) > .5:
        raise ValueError("Encoder detected movement of locked rotor")
    if row["fault_code"] or not 18 <= row["v_in"] <= 30 or row["temp_mos_c"] > 50:
        raise ValueError("Fault, voltage or MOS temperature guard")
    if max(abs(row["current_motor_a"]), math.hypot(row["id_a"], row["iq_a"])) > 1.5:
        raise ValueError("Observed current exceeded 1.5 A")
    if abs(row["duty"]) > .1:
        raise ValueError("Observed duty exceeded protective limit")


def analyze_hfi(points, encoder_deg, ratio, inverted, prior_offset):
    """HFI index phi excites the stator vector (sin(phi), -cos(phi))."""
    curves, current, paired = [], [], None
    for point in points:
        if point["graph"] == 0:
            paired = point
            continue
        if (paired is None or paired["index"] != point["index"]
                or paired["generation"] != point["generation"]
                or not 0 <= point["t"] - paired["t"] <= .02):
            current = []
            continue
        item = dict(index=point["index"], l_uh=point["value"], delta_i_a=paired["value"],
                    t=point["t"], generation=point["generation"])
        paired = None
        if item["index"] == 0:
            current = [item]
        elif current and item["index"] == len(current) and item["generation"] == current[0]["generation"]:
            current.append(item)
        else:
            current = []
        if len(current) == 32:
            curves.append(current)
            current = []
    accepted, rejected = [], []
    for curve in curves:
        try:
            if any(not 1 <= p["l_uh"] <= 2000 or not .01 < p["delta_i_a"] <= 1.5 for p in curve):
                raise ValueError("Invalid/stale raw inductance or delta-current sample")
            rows = [dict(phase_deg=p["index"] * 360 / 32 - 90,
                         response_inv_h=1e6 / p["l_uh"]) for p in curve]
            fit = _fit(rows)
            fit.update(start_t=curve[0]["t"], end_t=curve[-1]["t"],
                       min_delta_i_a=min(p["delta_i_a"] for p in curve),
                       max_delta_i_a=max(p["delta_i_a"] for p in curve))
            if fit["saliency"] < .05 or fit["relative_fit_error"] > .15:
                raise ValueError(f"Weak/non-sinusoidal HFI response: {fit}")
            accepted.append(fit)
        except ValueError as exc:
            rejected.append(str(exc))
    result = dict(full_curves=len(curves), accepted_curves=accepted, rejected_curves=rejected,
                  candidate=None, applied=False, ratio_direction_independently_validated=False,
                  assumptions=dict(encoder_ratio=ratio, encoder_inverted=inverted,
                                   d_axis="minimum_inductance", raw_encoder_deg=encoder_deg))
    if not accepted or rejected:
        result["status"] = "insufficient_or_invalid_data"
        return result
    axis, concentration = _axial_mean([p["min_l_axis_deg"] for p in accepted])
    spread = max(abs(axial_delta(p["min_l_axis_deg"], axis)) for p in accepted)
    if spread > 3 or concentration < .99:
        result["status"] = "inconsistent_axes"
        return result
    offset = (((-1 if inverted else 1) * ratio * encoder_deg) - axis) % 180
    choices = [offset, offset + 180]
    closest = min(choices, key=lambda a: abs((a - prior_offset + 180) % 360 - 180))
    result.update(status="single_pose_candidate", candidate=dict(
        minimum_inductance_axis_deg=axis, offset_candidates_deg=choices,
        nearest_prior_offset_deg=closest, repeat_axis_error_deg=spread,
        l_min_h=statistics.mean(p["l_min_h"] for p in accepted),
        l_max_h=statistics.mean(p["l_max_h"] for p in accepted)))
    return result


def analyze_dft(points, encoder_deg, ratio, inverted, prior_offset):
    groups = {}
    for p in points:
        key = (p["generation"], p["index"])
        groups.setdefault(key, {})[p["graph"]] = p
    frames = []
    for group in groups.values():
        if set(group) != set(range(5)):
            continue
        angle, amplitude, average = group[0]["value"], group[2]["value"], group[4]["value"]
        if not all(math.isfinite(v) for v in (angle, amplitude, average)) or abs(angle) > 2*math.pi + .001:
            continue
        if amplitude <= 0 or average <= amplitude or average > 2000:
            continue
        frames.append(dict(t=group[0]["t"], angle_deg=math.degrees(angle) % 180,
                           amplitude_uh=amplitude, average_uh=average))
    result = dict(status="insufficient_dft_data", candidate=None, frames=frames,
                  ratio_direction_independently_validated=False, applied=False,
                  assumptions=dict(encoder_ratio=ratio, encoder_inverted=inverted,
                                   raw_encoder_deg=encoder_deg, d_axis="minimum_inductance",
                                   speed_compensation_removed_by_zero_speed_pll=True))
    if len(frames) < 40:
        return result
    # Discard the initial ~50 ms. Each angle is already a DFT over a full HFI
    # buffer, unlike the slow index-by-index raw plot.
    frames = [f for f in frames if f["t"] >= frames[0]["t"] + .05]
    if len(frames) < 30:
        return result

    def vector_mean(items):
        c = statistics.mean(f["amplitude_uh"] * math.cos(math.radians(2*f["angle_deg"])) for f in items)
        s = statistics.mean(f["amplitude_uh"] * math.sin(math.radians(2*f["angle_deg"])) for f in items)
        angle = math.degrees(math.atan2(s, c))/2 % 180
        concentration = math.hypot(c, s) / statistics.mean(f["amplitude_uh"] for f in items)
        return angle, concentration

    axis, concentration = vector_mean(frames)
    blocks = [frames[len(frames)*i//4:len(frames)*(i+1)//4] for i in range(4)]
    block_axes = [vector_mean(b)[0] for b in blocks]
    block_error = max(abs(axial_delta(a, axis)) for a in block_axes)
    result.update(evaluated_frames=len(frames), concentration=concentration,
                  minimum_inductance_axis_deg=axis, block_axes_deg=block_axes,
                  max_block_axis_error_deg=block_error)
    if concentration < .9 or block_error > 3:
        result["status"] = "dft_axis_not_repeatable"
        return result
    offset = (((-1 if inverted else 1)*ratio*encoder_deg) - axis) % 180
    choices = [offset, offset+180]
    result.update(status="single_pose_candidate", candidate=dict(
        minimum_inductance_axis_deg=axis, offset_candidates_deg=choices,
        nearest_prior_offset_deg=min(choices, key=lambda a: abs((a-prior_offset+180)%360-180)),
        repeat_axis_error_deg=block_error))
    return result


def summarize_dft_runs(runs, reference_offset):
    """Combine independent physical repetitions; never claim multi-pose validation."""
    if len(runs) < 3 or len({r.get("dispatch_t") for r in runs}) != len(runs):
        raise ValueError("At least three distinct physical acquisitions are required")
    if len({r.get("baseline_sha256") for r in runs}) != 1:
        raise ValueError("Different baseline configurations cannot be pooled")
    settings, mechanical, offsets = [], [], []
    for r in runs:
        if not (r.get("ok") and r.get("plot_mode") == 1 and r.get("excitation_sent")
                and r.get("zero_current_verified") and r.get("baseline_restored")
                and r.get("app_unchanged") and r.get("no_faults")):
            raise ValueError("An acquisition did not pass measurement and recovery checks")
        a = r["analysis"]
        if a.get("status") != "single_pose_candidate" or not a.get("candidate"):
            raise ValueError("No qualified axis candidate")
        s = a["assumptions"]
        if not s.get("speed_compensation_removed_by_zero_speed_pll"):
            raise ValueError("DFT speed correction not isolated")
        settings.append((s["encoder_ratio"], s["encoder_inverted"], s["d_axis"], r["duty"]))
        mechanical.append(s["raw_encoder_deg"])
        offsets.append(a["candidate"]["offset_candidates_deg"][0])
    if len(set(settings)) != 1:
        raise ValueError("Different measurement/encoder settings")
    if max(abs((p-mechanical[0]+180)%360-180) for p in mechanical) > .5:
        raise ValueError("These are not repetitions at the same rotor pose")
    mean, concentration = _axial_mean(offsets)
    error = max(abs(axial_delta(v, mean)) for v in offsets)
    if error > 3 or concentration < .99:
        raise ValueError("Independent acquisitions disagree on offset")
    candidates = [mean, mean+180]
    nearest = min(candidates, key=lambda v: abs((v-reference_offset+180)%360-180))
    return dict(status="repeatable_single_pose_offset", acquisitions=len(runs),
                offset_candidates_deg=candidates, preferred_branch_deg=nearest,
                reference_offset_deg=reference_offset,
                change_from_reference_deg=(nearest-reference_offset+180)%360-180,
                individual_preferred_offsets_deg=[min([v, v+180], key=lambda x: abs((x-reference_offset+180)%360-180))
                                                   for v in offsets],
                max_repeat_deviation_deg=error,
                repeat_range_deg=max(axial_delta(v, mean) for v in offsets)-min(axial_delta(v, mean) for v in offsets),
                max_within_run_block_error_deg=max(r["analysis"]["max_block_axis_error_deg"] for r in runs),
                encoder_ratio=settings[0][0], encoder_inverted=settings[0][1],
                d_axis=settings[0][2], duty=settings[0][3], raw_encoder_positions_deg=mechanical,
                evaluated_dft_frames=sum(r["analysis"]["evaluated_frames"] for r in runs),
                baseline_sha256=runs[0]["baseline_sha256"],
                applied=False, multi_pose_validated=False, startup_validated=False,
                required_next_step="Repeat at another locked mechanical pose with power removed during repositioning",
                limitation="Repeatability is not absolute accuracy; ratio/direction and phase convention need independent validation")


def run_capture(client, output, baseline_required, duty=.01):
    require_locked()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    plot_mode = client.plot.mode
    result = dict(test="stock_hfi_locked", plot_mode=plot_mode, duty=duty, excitation_sent=False,
                  baseline_restored=False, no_faults=False, offset_applied=False)
    samples, errors = [], []
    original = None
    app = None
    started = monotonic()
    with (output / "packets.jsonl").open("x", encoding="utf-8") as packets, \
         (output / "samples.jsonl").open("x", encoding="utf-8") as telemetry:
        client.packet_log = packets

        def sample(stage, origin=None, enforce=True):
            before = monotonic()
            row = asdict(client.get_values())
            row.update(position_deg=client.pid_position, t=monotonic())
            latency = monotonic() - before
            telemetry.write(json.dumps({**row, "stage": stage, "latency_s": latency}, allow_nan=False) + "\n")
            telemetry.flush()
            samples.append(row)
            if enforce:
                if latency > .1:
                    raise ValueError("Encoder/current telemetry gap exceeded 100 ms")
                guard_sample(row, row["position_deg"] if origin is None else origin)
            return row

        def stopped_interval(origin, seconds=.4):
            quiet = []
            end = monotonic() + seconds
            while monotonic() < end:
                client.set_current(0)
                quiet.append(sample("quiet", origin))
                sleep(.01)
            verify_encoder_quiet(quiet)
            return quiet

        try:
            fw = asdict(client.fw_version())
            original, app = client.get_raw_config("motor"), client.get_raw_config("app")
            if original != Path(baseline_required).read_bytes():
                raise ValueError("Live configuration differs from required baseline")
            motor, _ = preflight_config(fw, original, app)
            result["firmware"] = fw
            result["baseline_sha256"] = hashlib.sha256(original).hexdigest()
            (output / "mcconf-before.bin").write_bytes(original)
            (output / "appconf-before.bin").write_bytes(app)
            terminal_expect(client, "measure_ind", "This command requires one argument. [duty]")
            terminal_expect(client, "foc_plot_hfi_en", "This command requires one argument.")
            origin = sample("initial")["position_deg"]
            stopped_interval(origin)
            if plot_mode == 1 and abs(samples[-1]["erpm"]) > 1:
                raise ValueError("PLL must be at zero speed before freezing its gains")
            with locked_hfi_permit(original, duty, plot_mode) as permit:
                try:
                    (output / "mcconf-limited.bin").write_bytes(permit.limited)
                    permit.verify_limits(write_motor_verified(client, permit.limited))
                    if client.get_raw_config("app") != app:
                        raise ValueError("Application changed before HFI")
                    stopped_interval(origin)
                    terminal_expect(client, f"foc_plot_hfi_en {plot_mode}", "HFI plot enabled")
                    expected_names = (["Current (A)", "Inductance (uH)"] if plot_mode == 2 else
                                      ["Phase", "Phase bin2", "Ld - Lq (uH", "L Diff Sat (uH)", "L Avg (uH)"])
                    if client.plot.names != expected_names:
                        raise ValueError(f"Unexpected raw plot graph names: {client.plot.names}")
                    if (output / "STOP").exists():
                        raise ValueError("STOP present before excitation")
                    dispatch = monotonic()
                    result["dispatch_t"] = dispatch
                    (output / "dispatch.json").write_text(json.dumps(dict(
                        command=permit.pulse[1:].decode(), t=dispatch, duty=duty)), encoding="utf-8")
                    client.send_payload(permit.pulse)
                    result["excitation_sent"] = True
                    result["command"] = permit.pulse[1:].decode()
                    end = monotonic() + .9
                    while monotonic() < end:
                        if (output / "STOP").exists():
                            raise ValueError("STOP requested")
                        row = sample("hfi", origin)
                        if plot_mode == 1 and abs(row["erpm"]) > 1:
                            raise ValueError("PLL speed is not frozen; DFT angle contains speed compensation")
                        sleep(.003)
                    complete = [p for p in client.prints if p["t"] >= dispatch and p["text"].startswith("Inductance:")]
                    if not complete:
                        raise ValueError("No measurement completion response")
                    result["measurement_response"] = complete[-1]
                finally:
                    # A measurement failure must NEVER stop the zero-current
                    # cleanup loop. The stock HFI command can run for ~0.5 s;
                    # do not assume a host zero cancels its internal loop.
                    quiet = []
                    end = monotonic() + 1.0
                    while monotonic() < end:
                        try:
                            client.set_current(0)
                            row = sample("stopping", origin, enforce=False)
                            quiet.append(row)
                        except Exception as exc:
                            errors.append(f"stop/read: {exc}")
                            quiet = []
                        sleep(.01)
                    terminal_expect(client, "foc_plot_hfi_en 0", "HFI plot disabled")
                    result["plot_disabled"] = True
                    # Verify only the final quiet tail, keeping ERPM in the log
                    # but never substituting it for the real encoder signal.
                    tail = [s for s in quiet if s["t"] >= monotonic() - .45]
                    permit.verify_stopped(tail)
                    result["zero_current_verified"] = True
                    if permit.setup_sent:
                        write_motor_verified(client, original)
                    result["baseline_restored"] = client.get_raw_config("motor") == original
                    result["app_unchanged"] = client.get_raw_config("app") == app
                    sample("final", origin)
            response_t = result.get("measurement_response", {}).get("t", 0)
            points = [p for p in client.plot.points if result["dispatch_t"] <= p["t"] <= response_t]
            during = [s for s in samples if result["dispatch_t"] <= s["t"] <= response_t]
            mechanical = statistics.mean(s["position_deg"] for s in during)
            analyzer = analyze_dft if plot_mode == 1 else analyze_hfi
            result["analysis"] = analyzer(points, mechanical, motor["foc_encoder_ratio"],
                                          bool(motor["foc_encoder_inverted"]), motor["foc_encoder_offset"])
        except (Exception, KeyboardInterrupt) as exc:
            errors.append(str(exc) or type(exc).__name__)
            try:
                client.set_current(0)
            except Exception as stop_exc:
                errors.append(f"Final stop: {stop_exc}")
        finally:
            client.packet_log = None
            result.update(errors=errors, terminal_output=client.prints, elapsed_s=monotonic()-started,
                          no_faults=bool(samples) and all(s["fault_code"] == 0 for s in samples),
                          sampled_peak_current_a=max((max(abs(s["current_motor_a"]), math.hypot(s["id_a"], s["iq_a"]))
                                                      for s in samples), default=0),
                          encoder_span_deg=max((s["position_deg"] for s in samples), default=0)
                          - min((s["position_deg"] for s in samples), default=0))
            result["ok"] = bool(not errors and result["baseline_restored"] and result.get("app_unchanged")
                                and result["no_faults"] and result.get("analysis", {}).get("candidate"))
            (output / "plot-points.json").write_text(json.dumps(client.plot.points, indent=2, allow_nan=False), encoding="utf-8")
            (output / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result
