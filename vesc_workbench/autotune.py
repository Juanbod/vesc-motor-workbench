from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from typing import Any
import copy
import csv
import json
import math
import shutil
import struct

from .autotest import CurrentRampResult, SafetyLimits, run_current_ramp
from .raw_config import restore_raw_config, sha256
from .raw_variants import MCCONF_OFFSETS_FW6_02_MKSESC_84_100_HP, load_manifest


@dataclass(frozen=True)
class TuneSpec:
    name: str
    foc_mtpa_mode: int
    phase_current_max: float
    input_current_max: float
    abs_current_max: float


@dataclass(frozen=True)
class AutotunePlan:
    current_steps: tuple[float, ...]
    hold_s: float
    cooldown_s: float
    expected_direction: int = 0


def _finite_positive(name: str, value: object, *, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if not math.isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        raise ValueError(f"{name} must be a positive finite number.")
    return number


def load_autotune_matrix(path: Path) -> tuple[AutotunePlan, tuple[TuneSpec, ...]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Autotune matrix must be a JSON object.")

    test = data.get("test", {})
    if not isinstance(test, dict):
        raise ValueError("Matrix test section must be an object.")
    raw_steps = test.get("current_steps", [2.0, 5.0, 10.0])
    if not isinstance(raw_steps, list):
        raise ValueError("test.current_steps must be an array.")
    steps = tuple(_finite_positive("test.current_steps", item, allow_zero=True) for item in raw_steps)
    if not steps:
        raise ValueError("test.current_steps cannot be empty.")
    plan = AutotunePlan(
        current_steps=steps,
        hold_s=_finite_positive("test.hold_s", test.get("hold_s", 1.5)),
        cooldown_s=_finite_positive("test.cooldown_s", test.get("cooldown_s", 1.0), allow_zero=True),
        expected_direction=int(test.get("expected_direction", 0)),
    )
    if plan.expected_direction not in {-1, 0, 1}:
        raise ValueError("test.expected_direction must be -1, 0, or 1.")

    raw_variants = data.get("variants")
    if not isinstance(raw_variants, list) or not raw_variants:
        raise ValueError("Matrix needs a non-empty variants array.")
    variants: list[TuneSpec] = []
    names: set[str] = set()
    for item in raw_variants:
        if not isinstance(item, dict):
            raise ValueError("Each variant must be an object.")
        name = str(item.get("name", "")).strip()
        if not name or name in names:
            raise ValueError("Each variant needs a unique non-empty name.")
        names.add(name)
        mtpa = int(item.get("foc_mtpa_mode", 0))
        if mtpa not in {0, 1}:
            raise ValueError(f"{name}: foc_mtpa_mode must be 0 or 1 in the first sweep.")
        phase = _finite_positive(f"{name}.phase_current_max", item.get("phase_current_max"))
        input_current = _finite_positive(f"{name}.input_current_max", item.get("input_current_max"))
        abs_current = _finite_positive(f"{name}.abs_current_max", item.get("abs_current_max"))
        if abs_current < phase:
            raise ValueError(f"{name}: abs_current_max must be >= phase_current_max.")
        variants.append(TuneSpec(name, mtpa, phase, input_current, abs_current))
    return plan, tuple(variants)


def _patch_float32(data: bytearray, offset: int, value: float) -> None:
    data[offset : offset + 4] = struct.pack(">f", float(value))


def patch_verified_tuning_fields(base_mcconf: bytes, spec: TuneSpec) -> bytes:
    """Patch only offsets verified against this firmware/hardware raw format."""
    data = bytearray(base_mcconf)
    offsets = MCCONF_OFFSETS_FW6_02_MKSESC_84_100_HP
    _patch_float32(data, offsets["l_current_max"], spec.phase_current_max)
    _patch_float32(data, offsets["l_in_current_max"], spec.input_current_max)
    _patch_float32(data, offsets["l_abs_current_max"], spec.abs_current_max)
    data[offsets["foc_mtpa_mode"]] = spec.foc_mtpa_mode
    return bytes(data)


def generate_autotune_queue(base_backup: Path, matrix_path: Path, output_root: Path) -> tuple[Path, ...]:
    plan, specs = load_autotune_matrix(matrix_path)
    manifest = load_manifest(base_backup)
    motor_info = manifest.get("files", {}).get("motor")
    app_info = manifest.get("files", {}).get("app")
    if not isinstance(motor_info, dict) or not isinstance(app_info, dict):
        raise ValueError("Raw backup manifest must contain motor and app files.")
    motor = (base_backup / str(motor_info["path"])).read_bytes()
    app = (base_backup / str(app_info["path"])).read_bytes()
    if len(motor) <= max(MCCONF_OFFSETS_FW6_02_MKSESC_84_100_HP.values()):
        raise ValueError("Raw motor configuration is too short for verified offsets.")
    output_root.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []
    for index, spec in enumerate(specs, start=1):
        output = output_root / f"{index:02d}_{spec.name}"
        if output.exists():
            shutil.rmtree(output)
        output.mkdir()
        patched = patch_verified_tuning_fields(motor, spec)
        (output / "mcconf.bin").write_bytes(patched)
        (output / "appconf.bin").write_bytes(app)
        variant_manifest = copy.deepcopy(manifest)
        variant_manifest["name"] = output.name
        variant_manifest["created_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        variant_manifest["base_backup"] = str(base_backup)
        variant_manifest["autotune"] = {
            "schema": "direct-encoder-v1",
            "safe_patch_fields": ["l_current_max", "l_in_current_max", "l_abs_current_max", "foc_mtpa_mode"],
            "spec": asdict(spec),
            "test": asdict(plan),
        }
        variant_manifest["files"]["motor"] = {
            "path": "mcconf.bin",
            "bytes": len(patched),
            "sha256": sha256(patched),
        }
        variant_manifest["files"]["app"] = {
            "path": "appconf.bin",
            "bytes": len(app),
            "sha256": sha256(app),
        }
        (output / "manifest.json").write_text(
            json.dumps(variant_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        generated.append(output)
    return tuple(generated)


def _samples_from_log(path: Path) -> list[dict[str, float]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    samples: list[dict[str, float]] = []
    for row in rows:
        if row.get("event") != "sample":
            continue
        try:
            samples.append({
                "erpm": float(row["erpm"]),
                "motor": float(row["current_motor_a"]),
                "input": float(row["current_in_a"]),
                "id": float(row["id_a"]),
                "iq": float(row["iq_a"]),
                "duty": float(row["duty"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return samples


def score_telemetry(log_path: Path, completed: bool, expected_direction: int = 0) -> dict[str, object]:
    samples = _samples_from_log(log_path)
    if not samples:
        return {"score": -100000.0, "samples": 0, "max_abs_erpm": 0.0, "reason": "no telemetry"}
    max_abs_erpm = max(abs(item["erpm"]) for item in samples)
    max_abs_duty = max(abs(item["duty"]) for item in samples)
    mean_abs_id = sum(abs(item["id"]) for item in samples) / len(samples)
    wrong_direction = expected_direction and any(item["erpm"] * expected_direction < -50.0 for item in samples)
    score = max_abs_erpm - mean_abs_id * 5.0 - max_abs_duty * 100.0
    if not completed:
        score -= 50000.0
    if wrong_direction:
        score -= 100000.0
    return {
        "score": round(score, 3),
        "samples": len(samples),
        "max_abs_erpm": round(max_abs_erpm, 3),
        "max_abs_duty": round(max_abs_duty, 4),
        "mean_abs_id_a": round(mean_abs_id, 3),
        "wrong_direction": bool(wrong_direction),
    }


def run_autotune_queue(
    queue_root: Path,
    plan: AutotunePlan,
    port: str,
    baudrate: int,
    timeout_s: float,
    limits: SafetyLimits,
    logs_root: Path,
    armed: bool,
    max_profiles: int | None = None,
) -> Path:
    variants = sorted(path for path in queue_root.iterdir() if path.is_dir() and (path / "manifest.json").exists())
    if not variants:
        raise RuntimeError(f"No variants found in {queue_root}")
    if max_profiles is not None:
        variants = variants[:max_profiles]
    run_dir = logs_root / f"autotune-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True)
    summary: list[dict[str, object]] = []
    for index, variant in enumerate(variants, start=1):
        manifest = load_manifest(variant)
        row: dict[str, object] = {"order": index, "profile": variant.name, "armed": armed}
        if not armed:
            row.update({"status": "dry-run", "settings": manifest.get("autotune", {})})
            summary.append(row)
            continue
        try:
            restore = restore_raw_config(
                port=port,
                baudrate=baudrate,
                timeout_s=timeout_s,
                backup_dir=variant,
                kinds=("motor",),
                armed=True,
                verify=True,
            )
            telemetry_path = run_dir / f"{index:02d}_{variant.name}.csv"
            result: CurrentRampResult = run_current_ramp(
                port=port,
                baudrate=baudrate,
                timeout_s=timeout_s,
                steps=plan.current_steps,
                hold_s=plan.hold_s,
                limits=limits,
                log_path=telemetry_path,
                armed=True,
            )
            row.update({
                "status": "completed" if result.completed else "stopped",
                "restore": restore,
                "telemetry": telemetry_path.name,
                "stop_reason": result.stop_reason,
                **score_telemetry(telemetry_path, result.completed, plan.expected_direction),
            })
            if not result.completed:
                summary.append(row)
                break
            summary.append(row)
            if plan.cooldown_s:
                sleep(plan.cooldown_s)
        except Exception as exc:
            row.update({"status": "error", "error": str(exc)})
            summary.append(row)
            break
    (run_dir / "summary.json").write_text(
        json.dumps({"plan": asdict(plan), "results": summary}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with (run_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["order", "profile", "armed", "status", "stop_reason", "score", "max_abs_erpm", "max_abs_duty", "mean_abs_id_a", "wrong_direction", "telemetry", "error"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary)
    return run_dir
