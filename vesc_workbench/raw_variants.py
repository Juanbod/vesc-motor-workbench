from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
import copy
import json
import shutil
import struct

from .raw_config import restore_raw_config, sha256


MCCONF_OFFSETS_FW6_02_MKSESC_84_100_HP = {
    "l_current_max": 8,
    "l_current_min": 12,
    "l_in_current_max": 16,
    "l_in_current_min": 20,
    "l_abs_current_max": 24,
    "foc_hall_table": 223,
    "foc_hall_interp_erpm": 231,
    "foc_sl_erpm": 235,
    "foc_mtpa_mode": 303,
}

DETECTED_HALL_TABLE = [255, 22, 90, 186, 162, 123, 43, 255]


@dataclass(frozen=True)
class RawVariantSpec:
    name: str
    foc_sl_erpm: float
    foc_hall_interp_erpm: float = 500.0
    hall_trim: int = 0
    reverse_hall_table: bool = False
    foc_mtpa_mode: int = 0
    phase_current_max: float = 75.0
    input_current_max: float = 100.0
    abs_current_max: float = 116.17


DEFAULT_VARIANTS = (
    RawVariantSpec("31_raw17_hall_i75_b100_sl6000_interp500", foc_sl_erpm=6000),
    RawVariantSpec("32_raw17_hall_i75_b100_sl6000_interp1000", foc_sl_erpm=6000, foc_hall_interp_erpm=1000),
    RawVariantSpec("33_raw17_hall_i75_b100_sl8000_interp500", foc_sl_erpm=8000),
    RawVariantSpec("34_raw17_hall_i75_b100_sl10000_interp500", foc_sl_erpm=10000),
    RawVariantSpec("35_raw17_hall_i75_b100_sl6000_trim_p5", foc_sl_erpm=6000, hall_trim=5),
    RawVariantSpec("36_raw17_hall_i75_b100_sl6000_trim_m5", foc_sl_erpm=6000, hall_trim=-5),
    RawVariantSpec("37_raw17_hall_i75_b100_sl6000_trim_p10", foc_sl_erpm=6000, hall_trim=10),
    RawVariantSpec("38_raw17_hall_i75_b100_sl6000_trim_m10", foc_sl_erpm=6000, hall_trim=-10),
    RawVariantSpec("39_raw17_hall_i75_b100_sl8000_trim_p5", foc_sl_erpm=8000, hall_trim=5),
    RawVariantSpec("40_raw17_hall_i75_b100_sl8000_trim_m5", foc_sl_erpm=8000, hall_trim=-5),
    RawVariantSpec("41_raw17_hall_i75_b100_sl6000_revtable", foc_sl_erpm=6000, reverse_hall_table=True),
    RawVariantSpec("42_raw17_hall_i75_b100_sl8000_revtable", foc_sl_erpm=8000, reverse_hall_table=True),
    RawVariantSpec("43_raw17_hall_i75_b100_sl10000_trim_p5", foc_sl_erpm=10000, hall_trim=5),
    RawVariantSpec("44_raw17_hall_i75_b100_sl10000_trim_m5", foc_sl_erpm=10000, hall_trim=-5),
    RawVariantSpec("45_raw17_hall_i75_b100_sl10000_trim_p10", foc_sl_erpm=10000, hall_trim=10),
    RawVariantSpec("46_raw17_hall_i75_b100_sl10000_trim_m10", foc_sl_erpm=10000, hall_trim=-10),
    RawVariantSpec("47_raw17_hall_i75_b100_sl12000_interp500", foc_sl_erpm=12000),
    RawVariantSpec("48_raw17_hall_i75_b100_sl12000_interp1000", foc_sl_erpm=12000, foc_hall_interp_erpm=1000),
    RawVariantSpec("49_raw17_hall_i75_b100_sl12000_trim_p5", foc_sl_erpm=12000, hall_trim=5),
    RawVariantSpec("50_raw17_hall_i75_b100_sl12000_trim_m5", foc_sl_erpm=12000, hall_trim=-5),
    RawVariantSpec("51_raw17_highspeed_i75_b100_sl1500_interp500", foc_sl_erpm=1500),
    RawVariantSpec("52_raw17_highspeed_i75_b100_sl2000_interp500", foc_sl_erpm=2000),
    RawVariantSpec("53_raw17_highspeed_i75_b100_sl3000_interp500", foc_sl_erpm=3000),
    RawVariantSpec("54_raw17_highspeed_i75_b100_sl4000_interp500", foc_sl_erpm=4000),
    RawVariantSpec("55_raw17_highspeed_i75_b100_sl3000_interp1000", foc_sl_erpm=3000, foc_hall_interp_erpm=1000),
    RawVariantSpec("56_raw17_highspeed_i75_b100_sl4000_interp1000", foc_sl_erpm=4000, foc_hall_interp_erpm=1000),
    RawVariantSpec("57_raw17_highspeed_i75_b100_sl3000_trim_p5", foc_sl_erpm=3000, hall_trim=5),
    RawVariantSpec("58_raw17_highspeed_i75_b100_sl3000_trim_m5", foc_sl_erpm=3000, hall_trim=-5),
    RawVariantSpec("59_raw17_best52_i75_b100_sl1800_interp500", foc_sl_erpm=1800),
    RawVariantSpec("60_raw17_best52_i75_b100_sl2200_interp500", foc_sl_erpm=2200),
    RawVariantSpec("61_raw17_best52_i75_b100_sl2500_interp500", foc_sl_erpm=2500),
    RawVariantSpec("62_raw17_best52_i75_b100_sl2000_interp250", foc_sl_erpm=2000, foc_hall_interp_erpm=250),
    RawVariantSpec("63_raw17_best52_i75_b100_sl2000_interp750", foc_sl_erpm=2000, foc_hall_interp_erpm=750),
    RawVariantSpec("64_raw17_best52_i75_b100_sl2000_interp1000", foc_sl_erpm=2000, foc_hall_interp_erpm=1000),
    RawVariantSpec("65_raw17_best52_i75_b100_sl2200_interp750", foc_sl_erpm=2200, foc_hall_interp_erpm=750),
    RawVariantSpec("66_raw17_best52_i75_b100_sl2500_interp750", foc_sl_erpm=2500, foc_hall_interp_erpm=750),
    RawVariantSpec("67_raw17_best52_i75_b100_sl2000_trim_p2", foc_sl_erpm=2000, hall_trim=2),
    RawVariantSpec("68_raw17_best52_i75_b100_sl2000_trim_m2", foc_sl_erpm=2000, hall_trim=-2),
    RawVariantSpec("69_raw17_mtpa_i75_b100_sl2000_interp500", foc_sl_erpm=2000, foc_mtpa_mode=1),
    RawVariantSpec("70_raw17_mtpa_i75_b100_sl1800_interp500", foc_sl_erpm=1800, foc_mtpa_mode=1),
    RawVariantSpec("71_raw17_mtpa_i75_b100_sl2000_interp250", foc_sl_erpm=2000, foc_hall_interp_erpm=250, foc_mtpa_mode=1),
    RawVariantSpec("72_raw17_mtpa_i75_b100_sl2000_interp750", foc_sl_erpm=2000, foc_hall_interp_erpm=750, foc_mtpa_mode=1),
    RawVariantSpec("73_raw17_mtpa_i75_b100_sl2200_interp500", foc_sl_erpm=2200, foc_mtpa_mode=1),
    RawVariantSpec("74_raw17_mtpa_i75_b100_sl1800_interp250", foc_sl_erpm=1800, foc_hall_interp_erpm=250, foc_mtpa_mode=1),
    RawVariantSpec("75_raw17_mtpa_i75_b100_sl1800_interp750", foc_sl_erpm=1800, foc_hall_interp_erpm=750, foc_mtpa_mode=1),
    RawVariantSpec("76_raw17_mtpa_i75_b100_sl2000_trim_p2", foc_sl_erpm=2000, hall_trim=2, foc_mtpa_mode=1),
    RawVariantSpec("77_raw17_mtpa_i75_b100_sl2000_trim_m2", foc_sl_erpm=2000, hall_trim=-2, foc_mtpa_mode=1),
    RawVariantSpec("78_raw17_mtpa_i75_b100_sl1500_interp500", foc_sl_erpm=1500, foc_mtpa_mode=1),
)


def patch_float32(data: bytearray, offset: int, value: float) -> None:
    data[offset : offset + 4] = struct.pack(">f", float(value))


def patch_int32(data: bytearray, offset: int, value: int) -> None:
    data[offset : offset + 4] = struct.pack(">i", int(value))


def trimmed_hall_table(trim: int, reverse: bool = False) -> bytes:
    values = []
    for item in DETECTED_HALL_TABLE:
        if item == 255:
            values.append(255)
        elif reverse:
            values.append((200 - item + trim) % 200)
        else:
            values.append((item + trim) % 200)
    return bytes(values)


def patch_mcconf_for_variant(base_mcconf: bytes, spec: RawVariantSpec) -> bytes:
    data = bytearray(base_mcconf)
    offsets = MCCONF_OFFSETS_FW6_02_MKSESC_84_100_HP
    patch_float32(data, offsets["l_current_max"], spec.phase_current_max)
    patch_float32(data, offsets["l_in_current_max"], spec.input_current_max)
    patch_float32(data, offsets["l_abs_current_max"], spec.abs_current_max)
    data[offsets["foc_hall_table"] : offsets["foc_hall_table"] + 8] = trimmed_hall_table(
        spec.hall_trim,
        spec.reverse_hall_table,
    )
    patch_float32(data, offsets["foc_hall_interp_erpm"], spec.foc_hall_interp_erpm)
    patch_float32(data, offsets["foc_sl_erpm"], spec.foc_sl_erpm)
    data[offsets["foc_mtpa_mode"]] = spec.foc_mtpa_mode & 0xFF
    return bytes(data)


def load_manifest(path: Path) -> dict[str, object]:
    with (path / "manifest.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_raw_variant(base_backup: Path, output_root: Path, spec: RawVariantSpec) -> Path:
    manifest = load_manifest(base_backup)
    output = output_root / spec.name
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    motor = (base_backup / manifest["files"]["motor"]["path"]).read_bytes()  # type: ignore[index]
    app = (base_backup / manifest["files"]["app"]["path"]).read_bytes()  # type: ignore[index]
    patched_motor = patch_mcconf_for_variant(motor, spec)

    (output / "mcconf.bin").write_bytes(patched_motor)
    (output / "appconf.bin").write_bytes(app)

    variant_manifest = copy.deepcopy(manifest)
    variant_manifest["name"] = spec.name
    variant_manifest["created_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    variant_manifest["base_backup"] = str(base_backup)
    variant_manifest["variant"] = {
        "foc_sensor_mode": 2,
        "phase_current_max": spec.phase_current_max,
        "input_current_max": spec.input_current_max,
        "abs_current_max": spec.abs_current_max,
        "foc_mtpa_mode": spec.foc_mtpa_mode,
        "foc_sl_erpm": spec.foc_sl_erpm,
        "foc_hall_interp_erpm": spec.foc_hall_interp_erpm,
        "hall_trim": spec.hall_trim,
        "reverse_hall_table": spec.reverse_hall_table,
        "hall_table": list(trimmed_hall_table(spec.hall_trim, spec.reverse_hall_table)),
    }
    variant_manifest["files"]["motor"] = {  # type: ignore[index]
        "path": "mcconf.bin",
        "bytes": len(patched_motor),
        "sha256": sha256(patched_motor),
    }
    variant_manifest["files"]["app"] = {  # type: ignore[index]
        "path": "appconf.bin",
        "bytes": len(app),
        "sha256": sha256(app),
    }
    with (output / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(variant_manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    return output


def generate_default_raw_variants(base_backup: Path, output_root: Path) -> tuple[Path, ...]:
    return tuple(write_raw_variant(base_backup, output_root, spec) for spec in DEFAULT_VARIANTS)


def upload_raw_variant_queue(
    queue_root: Path,
    port: str,
    baudrate: int,
    timeout_s: float,
    armed: bool,
    wait_s: float,
    kinds: tuple[str, ...] = ("motor", "app"),
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    variants = sorted(path for path in queue_root.iterdir() if path.is_dir() and (path / "manifest.json").exists())
    if not variants:
        raise RuntimeError(f"No raw variants found in {queue_root}")
    for variant in variants:
        manifest = load_manifest(variant)
        if not armed:
            results.append(
                {
                    "variant": variant.name,
                    "dry_run": True,
                    "would_restore": list(kinds),
                    "settings": manifest.get("variant", {}),
                }
            )
            continue
        result = restore_raw_config(
            port=port,
            baudrate=baudrate,
            timeout_s=timeout_s,
            backup_dir=variant,
            kinds=kinds,
            armed=True,
        )
        result["variant"] = variant.name
        result["settings"] = manifest.get("variant", {})
        results.append(result)
        sleep(wait_s)
    return results
