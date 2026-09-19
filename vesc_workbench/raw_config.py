from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
import hashlib
import json
import shutil

from .uart import VescUartClient


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def backup_raw_config(
    port: str,
    baudrate: int,
    timeout_s: float,
    output_dir: Path,
    name: str,
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_dir = output_dir / f"{stamp}_{name}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    try:
        with VescUartClient(port=port, baudrate=baudrate, timeout_s=timeout_s) as client:
            firmware = client.fw_version()
            sleep(0.1)
            motor = client.get_raw_config("motor")
            app = client.get_raw_config("app")

        (backup_dir / "mcconf.bin").write_bytes(motor)
        (backup_dir / "appconf.bin").write_bytes(app)
        manifest = {
            "name": name,
            "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "port": port,
            "baudrate": baudrate,
            "firmware": asdict(firmware),
            "files": {
                "motor": {
                    "path": "mcconf.bin",
                    "bytes": len(motor),
                    "sha256": sha256(motor),
                },
                "app": {
                    "path": "appconf.bin",
                    "bytes": len(app),
                    "sha256": sha256(app),
                },
            },
        }
        with (backup_dir / "manifest.json").open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except Exception:
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise
    return backup_dir


def restore_raw_config(
    port: str,
    baudrate: int,
    timeout_s: float,
    backup_dir: Path,
    kinds: tuple[str, ...],
    armed: bool,
    delay_s: float = 0.25,
    verify: bool = True,
) -> dict[str, object]:
    if not armed:
        raise RuntimeError("Refusing to restore raw VESC config without --armed.")

    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Missing raw config manifest: {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    with VescUartClient(port=port, baudrate=baudrate, timeout_s=timeout_s) as client:
        current_fw = client.fw_version()
        backup_fw = manifest.get("firmware", {})
        if backup_fw and (
            backup_fw.get("major") != current_fw.major
            or backup_fw.get("minor") != current_fw.minor
            or backup_fw.get("hardware") != current_fw.hardware
        ):
            raise RuntimeError(
                "Firmware/hardware mismatch: "
                f"backup={backup_fw}, current={asdict(current_fw)}"
            )

        restored: list[str] = []
        for kind in kinds:
            if kind not in {"motor", "app"}:
                raise RuntimeError(f"Unknown config kind: {kind}")
            item = manifest["files"][kind]
            data = (backup_dir / item["path"]).read_bytes()
            if sha256(data) != item["sha256"]:
                raise RuntimeError(f"Hash mismatch for {kind} backup.")
            client.set_raw_config(kind, data)
            restored.append(kind)
            sleep(delay_s)
            if verify:
                written = client.get_raw_config(kind)
                if sha256(written) != item["sha256"]:
                    raise RuntimeError(f"Read-back verification failed for {kind} config.")

    return {
        "backup": str(backup_dir),
        "restored": restored,
        "verified": verify,
    }
