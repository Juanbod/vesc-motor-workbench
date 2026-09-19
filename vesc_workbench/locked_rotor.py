"""Offline saliency-axis calibration. This module cannot open a motor transport.

Input response is directional incremental inverse inductance, in 1/H, measured
in the fixed stator alpha/beta frame. Slow GET_VALUES telemetry is NOT suitable
for constructing this input. A bounded, controller-side acquisition is required.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import random
import statistics


SCHEMA = "vesc-locked-rotor-v1"
SOURCE_COMMIT = "f7c2b34e1cff2234cae98be3abf0cd50e249558f"
ALGORITHM = "inverse-inductance-harmonic-v1"


def axial_delta(a, b):
    return (a - b + 90) % 180 - 90


def angular_delta(a, b):
    return (a - b + 180) % 360 - 180


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LockedRotorPlan:
    angle_count: int = 12
    repeats: int = 3
    min_poses: int = 4
    max_pole_pairs: int = 8
    d_axis: str = "minimum_inductance"
    max_rotor_drift_deg: float = 0.5
    max_sample_age_s: float = 0.1
    max_current_a: float = 3.0
    max_phase_error_deg: float = 3.0
    min_saliency: float = 0.05
    max_relative_fit_error: float = 0.08
    # These are requirements for a FUTURE on-controller acquisition, not
    # pulse settings sent by this offline program.
    max_burst_s: float = 0.05
    max_pose_energy_j: float = 2.0
    max_pose_i2t_a2s: float = 5.0
    min_cooldown_s: float = 8.0

    def validate(self):
        for name, lo, hi in (("angle_count", 12, 36), ("repeats", 3, 8),
                             ("min_poses", 4, 12), ("max_pole_pairs", 1, 16)):
            value = getattr(self, name)
            if type(value) is not int or not lo <= value <= hi:
                raise ValueError(f"{name} outside {lo}..{hi}")
        bounds = {"max_rotor_drift_deg": (0, 0.5), "max_sample_age_s": (0, 0.1),
                  "max_current_a": (0, 3), "max_phase_error_deg": (0, 3),
                  "min_saliency": (0, 0.5), "max_relative_fit_error": (0, 0.08),
                  "max_burst_s": (0, 0.05), "max_pose_energy_j": (0, 2),
                  "max_pose_i2t_a2s": (0, 5)}
        for name, (lo, hi) in bounds.items():
            if not lo < finite(getattr(self, name), name) <= hi:
                raise ValueError(f"{name} outside ({lo}, {hi}]")
        if not 8 <= finite(self.min_cooldown_s, "min_cooldown_s") <= 120:
            raise ValueError("min_cooldown_s outside 8..120")
        if self.d_axis not in ("minimum_inductance", "maximum_inductance"):
            raise ValueError("Explicit d-axis convention required")

    def schedule(self):
        self.validate()
        return [dict(repeat=r, phase_deg=k * 180 / self.angle_count)
                for r in range(self.repeats) for k in range(self.angle_count)]


def _axial_mean(angles):
    s = statistics.mean(math.sin(math.radians(2 * a)) for a in angles)
    c = statistics.mean(math.cos(math.radians(2 * a)) for a in angles)
    return (math.degrees(math.atan2(s, c)) / 2) % 180, math.hypot(s, c)


def _fit(rows):
    # The validated balanced grid makes the Fourier basis orthogonal.
    values = [r["response_inv_h"] for r in rows]
    mean = statistics.mean(values)
    c = 2 * statistics.mean(r["response_inv_h"] * math.cos(math.radians(2 * r["phase_deg"]))
                            for r in rows)
    s = 2 * statistics.mean(r["response_inv_h"] * math.sin(math.radians(2 * r["phase_deg"]))
                            for r in rows)
    amplitude = math.hypot(c, s)
    residual = math.sqrt(statistics.mean(
        (r["response_inv_h"] - mean - c * math.cos(math.radians(2 * r["phase_deg"]))
         - s * math.sin(math.radians(2 * r["phase_deg"]))) ** 2 for r in rows))
    if mean <= amplitude or amplitude <= 0:
        raise ValueError("Nonphysical or absent saliency response")
    return dict(min_l_axis_deg=(math.degrees(math.atan2(s, c)) / 2) % 180,
                l_min_h=1 / (mean + amplitude), l_max_h=1 / (mean - amplitude),
                saliency=amplitude / mean, relative_fit_error=residual / amplitude)


def analyze_pose(pose, plan):
    plan.validate()
    rows = pose["samples"]
    schedule = plan.schedule()
    if len(rows) != len(schedule):
        raise ValueError("Incomplete pose: every angle and repeat is required")
    expected = {(s["repeat"], round(s["phase_deg"], 6)) for s in schedule}
    seen = set()
    encoder = []
    for row in rows:
        for name in ("phase_deg", "response_inv_h", "encoder_deg", "encoder_age_s",
                     "peak_current_a", "burst_s", "energy_j", "i2t_a2s"):
            finite(row[name], name)
        if type(row["repeat"]) is not int:
            raise ValueError("Repeat index must be an integer")
        key = (row["repeat"], round(row["phase_deg"], 6))
        if key not in expected or key in seen:
            raise ValueError("Duplicate or off-grid measurement")
        seen.add(key)
        if not 0 <= row["encoder_deg"] < 360 or row["response_inv_h"] <= 0:
            raise ValueError("Invalid encoder angle or response")
        if type(row["fault"]) is not int or row["fault"] != 0:
            raise ValueError("Controller fault during acquisition")
        for name, maximum in (("encoder_age_s", plan.max_sample_age_s),
                              ("peak_current_a", plan.max_current_a),
                              ("burst_s", plan.max_burst_s),
                              ("energy_j", plan.max_pose_energy_j),
                              ("i2t_a2s", plan.max_pose_i2t_a2s)):
            if not 0 <= row[name] <= maximum:
                raise ValueError(f"Acquisition limit exceeded: {name}")
        if row["burst_s"] == 0:
            raise ValueError("Missing acquisition duration")
        if row["peak_current_a"] == 0 or row["i2t_a2s"] == 0:
            raise ValueError("No measured excitation for the inductance response")
        encoder.append(row["encoder_deg"])
    unwrapped = [encoder[0] + angular_delta(a, encoder[0]) for a in encoder]
    drift = max(unwrapped) - min(unwrapped)
    if drift > plan.max_rotor_drift_deg:
        raise ValueError("Rotor moved within the locked pose")
    for key, limit in (("energy_j", plan.max_pose_energy_j), ("i2t_a2s", plan.max_pose_i2t_a2s)):
        if sum(row[key] for row in rows) > limit:
            raise ValueError(f"Pose budget exceeded: {key}")
    fits = [_fit([r for r in rows if r["repeat"] == repeat]) for repeat in range(plan.repeats)]
    for fit in fits:
        if fit["saliency"] < plan.min_saliency:
            raise ValueError("Saliency signal too weak")
        if fit["relative_fit_error"] > plan.max_relative_fit_error:
            raise ValueError("Response is not a repeatable second harmonic")
    axis, concentration = _axial_mean([f["min_l_axis_deg"] for f in fits])
    repeat_error = max(abs(axial_delta(f["min_l_axis_deg"], axis)) for f in fits)
    if repeat_error > plan.max_phase_error_deg or concentration < .99:
        raise ValueError("Axis estimates disagree between repeats")
    return dict(pose_id=pose["pose_id"], encoder_deg=statistics.mean(unwrapped) % 360,
                rotor_drift_deg=drift, min_l_axis_deg=axis,
                d_axis_deg=(axis + (90 if plan.d_axis == "maximum_inductance" else 0)) % 180,
                repeat_error_deg=repeat_error, repeats=fits,
                l_min_h=statistics.mean(f["l_min_h"] for f in fits),
                l_max_h=statistics.mean(f["l_max_h"] for f in fits))


def _analyze(data):
    if data["schema"] != SCHEMA:
        raise ValueError("Unsupported dataset schema")
    if type(data["simulated"]) is not bool:
        raise ValueError("Explicit simulated flag required")
    if data["frame"] != "stator_alpha_beta" or data["quantity"] != "directional_inverse_inductance_h-1":
        raise ValueError("Unverified acquisition frame or response quantity")
    plan = LockedRotorPlan(**data["plan"])
    plan.validate()
    if not plan.min_poses <= len(data["poses"]) <= 24:
        raise ValueError("Need multiple locked poses to determine ratio and direction")
    ids = [p["pose_id"] for p in data["poses"]]
    if any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Unique nonempty pose IDs required")
    poses = [analyze_pose(p, plan) for p in data["poses"]]
    hypotheses = []
    for pairs in range(1, plan.max_pole_pairs + 1):
        for direction in (1, -1):
            offsets = [(direction * pairs * p["encoder_deg"] - p["d_axis_deg"]) % 180 for p in poses]
            offset, resultant = _axial_mean(offsets)
            errors = [axial_delta(a, offset) for a in offsets]
            hypotheses.append(dict(pole_pairs=pairs, encoder_inverted=direction < 0,
                                   offset_mod_180_deg=offset, resultant=resultant,
                                   rms_error_deg=math.sqrt(statistics.mean(e * e for e in errors)),
                                   max_error_deg=max(abs(e) for e in errors)))
    hypotheses.sort(key=lambda h: h["rms_error_deg"])
    qualified = [h for h in hypotheses if h["max_error_deg"] <= plan.max_phase_error_deg
                 and h["resultant"] >= .99]
    separated = len(qualified) == 1 and hypotheses[1]["rms_error_deg"] - hypotheses[0]["rms_error_deg"] > plan.max_phase_error_deg
    result = dict(poses=poses, hypotheses=hypotheses, candidate=None,
                  status="ambiguous" if not separated else "candidate_only",
                  reason="Ratio/direction hypotheses are not uniquely separated" if not separated
                  else "Axis is resolved modulo 180 electrical degrees; verify before applying")
    if separated:
        best = hypotheses[0]
        result["candidate"] = {**best, "offset_candidates_deg": [best["offset_mod_180_deg"],
                                                                  best["offset_mod_180_deg"] + 180],
                               "d_axis": plan.d_axis}
    return result


def analyze(data):
    """Return a report, never a write-ready motor configuration."""
    result = dict(algorithm=ALGORITHM, hardware_validated=False, auto_apply_allowed=False,
                  simulated=data.get("simulated") if isinstance(data, dict)
                  and type(data.get("simulated")) is bool else None,
                  candidate=None)
    try:
        result["dataset_sha256"] = canonical_digest(data)
        result.update(_analyze(data))
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        result.update(status="rejected", reason=str(exc))
    return result


def simulated_dataset(plan=None, *, offset_deg=357.52764892578125, pole_pairs=2,
                      inverted=False, noise=0.002, seed=17):
    plan = plan or LockedRotorPlan()
    plan.validate()
    rng = random.Random(seed)
    poses = []
    for index, mechanical in enumerate((351.0, 8.0, 34.0, 70.0)):
        d_axis = ((-1 if inverted else 1) * pole_pairs * mechanical - offset_deg) % 180
        min_axis = d_axis - (90 if plan.d_axis == "maximum_inductance" else 0)
        rows = []
        for item in plan.schedule():
            response = 50000 + 17000 * math.cos(math.radians(2 * (item["phase_deg"] - min_axis)))
            rows.append({**item, "response_inv_h": response + rng.gauss(0, noise * 17000),
                         "encoder_deg": mechanical, "encoder_age_s": .001,
                         "peak_current_a": 1.0, "burst_s": .01, "energy_j": .001,
                         "i2t_a2s": .01, "fault": 0})
        poses.append(dict(pose_id=f"pose-{index + 1}", samples=rows))
    return dict(schema=SCHEMA, simulated=True, frame="stator_alpha_beta",
                quantity="directional_inverse_inductance_h-1", plan=asdict(plan), poses=poses,
                provenance={"source": "synthetic second-harmonic response", "seed": seed})


def preparation(plan=None, baseline=None):
    plan = plan or LockedRotorPlan()
    plan.validate()
    return dict(schema=SCHEMA, plan=asdict(plan), acquisition_schedule=plan.schedule(),
                acquisition_enabled=False, controller_connected=False,
                source_reference_commit=SOURCE_COMMIT,
                baseline_sha256=hashlib.sha256(Path(baseline).read_bytes()).hexdigest() if baseline else None,
                suggested_manual_pose_deltas_deg=[0, 17, 43, 79],
                gates=["Controller-side bounded acquisition adapter not yet validated",
                       "Confirm fixture and permission for each powered session",
                       "Reposition only with power disconnected; verify fixture again",
                       "Verify stator phase origin/sign and inverse-inductance scaling",
                       "Capture current, encoder, fault and energy guards on controller",
                       "Abort on movement, stale samples, disconnect, STOP or budget exhaustion",
                       "No auto-apply; resolve candidates and independently verify free-rotor startup"])


def save_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def report_text(result):
    lines = ["# Locked-Rotor Calibration", "",
             "SYNTHETIC DATA: NOT A MOTOR CALIBRATION" if result["simulated"] else "Imported data: hardware acquisition not verified",
             "", f"Status: {result['status']}", f"Reason: {result['reason']}",
             "Hardware writes: disabled", ""]
    candidate = result.get("candidate")
    if candidate:
        lines.extend([f"Pole pairs: {candidate['pole_pairs']}",
                      f"Encoder inverted: {candidate['encoder_inverted']}",
                      f"D axis: {candidate['d_axis']}",
                      f"Offset alternatives (electrical deg): {candidate['offset_candidates_deg']}",
                      f"Fit RMS (electrical deg): {candidate['rms_error_deg']:.4f}", ""])
    lines.extend(["These are axis candidates, not a validated startup or speed configuration.",
                  "Locked-rotor saliency cannot resolve the 180-degree axis ambiguity.",
                  "The observer angle is not used as a calibration reference.", ""])
    return "\n".join(lines)
