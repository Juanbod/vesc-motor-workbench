from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConfigFile:
    path: Path
    kind: str
    sha256: str
    size_bytes: int
    modified_at: str
    root_tag: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConfigBundle:
    bundle_id: str
    profile: str
    path: Path
    files: tuple[ConfigFile, ...]
    created_at: str

    def to_manifest(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "profile": self.profile,
            "path": str(self.path),
            "created_at": self.created_at,
            "files": [
                {
                    **asdict(item),
                    "path": str(item.path),
                    "warnings": list(item.warnings),
                }
                for item in self.files
            ],
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return slug or "profile"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def profile_signature(files: list[ConfigFile]) -> str:
    digest = hashlib.sha256()
    for item in sorted(files, key=lambda config: config.path.name):
        digest.update(item.path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.kind.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.sha256.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def detect_config_kind(root: ET.Element) -> str:
    tags = {_strip_ns(element.tag) for element in root.iter()}
    text = " ".join(tags)

    app_markers = {
        "app_to_use",
        "app_adc_conf",
        "app_ppm_conf",
        "app_uart_baudrate",
        "ctrl_type",
    }
    motor_markers = {
        "l_current_max",
        "l_in_current_max",
        "foc_motor_r",
        "foc_motor_l",
        "foc_hfi_start_voltage",
        "foc_hfi_voltage_run",
        "si_motor_poles",
    }

    if tags & app_markers or "appconf" in text:
        return "app"
    if tags & motor_markers or "mcconf" in text or "motor" in text:
        return "motor"
    return "unknown"


def profile_name_from_path(path: Path) -> str:
    stem = path.stem
    lowered = stem.lower()
    suffixes = (
        "_motor",
        "-motor",
        "_mc",
        "-mc",
        "_mcconf",
        "-mcconf",
        "_app",
        "-app",
        "_appconf",
        "-appconf",
    )
    for suffix in suffixes:
        if lowered.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def profile_name_for_source(path: Path, incoming_root: Path) -> str:
    try:
        relative = path.resolve().relative_to(incoming_root.resolve())
    except ValueError:
        return profile_name_from_path(path)
    if len(relative.parts) > 1:
        return relative.parts[0]
    return profile_name_from_path(path)


def validate_xml_file(path: Path, forced_kind: str = "auto") -> ConfigFile:
    if not path.exists():
        raise ConfigError(f"Config file does not exist: {path}")
    if path.suffix.lower() != ".xml":
        raise ConfigError(f"Expected .xml config file: {path}")

    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise ConfigError(f"Invalid XML in {path}: {exc}") from exc

    root = tree.getroot()
    detected = detect_config_kind(root)
    kind = detected if forced_kind == "auto" else forced_kind
    if kind not in {"auto", "app", "motor", "unknown"}:
        raise ConfigError(f"Unsupported config kind: {kind}")

    warnings: list[str] = []
    if detected == "unknown" and forced_kind == "auto":
        warnings.append("Config type was not recognized automatically.")
    if forced_kind != "auto" and detected != "unknown" and forced_kind != detected:
        warnings.append(f"Forced kind {forced_kind!r} differs from detected kind {detected!r}.")

    stat = path.stat()
    return ConfigFile(
        path=path.resolve(),
        kind=kind,
        sha256=file_sha256(path),
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        root_tag=_strip_ns(root.tag),
        warnings=tuple(warnings),
    )


class ConfigManager:
    def __init__(
        self,
        root: Path,
        incoming: Path,
        staged: Path,
        applied: Path,
        state_file: Path | None = None,
    ) -> None:
        self.root = root
        self.incoming = incoming
        self.staged = staged
        self.applied = applied
        self.state_file = state_file or root / ".vesc-workbench" / "state.json"

    def ensure_dirs(self) -> None:
        for path in (self.incoming, self.staged, self.applied, self.state_file.parent):
            path.mkdir(parents=True, exist_ok=True)

    def load_state(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {"known_hashes": {}, "known_profiles": {}, "bundles": {}, "applied": {}}
        with self.state_file.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def migrate_known_profiles(self, state: dict[str, Any]) -> None:
        known_profiles: dict[str, str] = state.setdefault("known_profiles", {})
        if known_profiles:
            return
        for manifest in state.get("bundles", {}).values():
            files = [
                ConfigFile(
                    path=Path(item["path"]),
                    kind=str(item["kind"]),
                    sha256=str(item["sha256"]),
                    size_bytes=int(item["size_bytes"]),
                    modified_at=str(item["modified_at"]),
                    root_tag=str(item["root_tag"]),
                    warnings=tuple(item.get("warnings", ())),
                )
                for item in manifest.get("files", [])
            ]
            if files:
                known_profiles[str(manifest["profile"])] = profile_signature(files)

    def save_state(self, state: dict[str, Any]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    def import_config(self, source: Path, profile: str | None = None) -> Path:
        self.ensure_dirs()
        config = validate_xml_file(source)
        name = safe_slug(profile or profile_name_from_path(source))
        destination = self.incoming / f"{name}_{config.kind}_{config.sha256[:8]}.xml"
        shutil.copy2(source, destination)
        return destination

    def scan_incoming(self) -> tuple[ConfigFile, ...]:
        self.ensure_dirs()
        configs: list[ConfigFile] = []
        for path in sorted(self.incoming.rglob("*.xml")):
            configs.append(validate_xml_file(path))
        return tuple(configs)

    def stage_new_configs(self) -> tuple[ConfigBundle, ...]:
        self.ensure_dirs()
        state = self.load_state()
        self.migrate_known_profiles(state)
        known_hashes: dict[str, Any] = state.setdefault("known_hashes", {})
        known_profiles: dict[str, str] = state.setdefault("known_profiles", {})
        grouped: dict[str, list[ConfigFile]] = {}

        for config in self.scan_incoming():
            profile = profile_name_for_source(config.path, self.incoming)
            grouped.setdefault(profile, []).append(config)

        bundles: list[ConfigBundle] = []
        for profile, files in grouped.items():
            signature = profile_signature(files)
            if known_profiles.get(profile) == signature:
                continue
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            bundle_id = f"{stamp}_{safe_slug(profile)}"
            bundle_path = self.staged / bundle_id
            bundle_path.mkdir(parents=True, exist_ok=False)

            staged_files: list[ConfigFile] = []
            for item in files:
                destination = bundle_path / item.path.name
                shutil.copy2(item.path, destination)
                staged_files.append(validate_xml_file(destination, forced_kind=item.kind))
                known_hashes[item.sha256] = {
                    "first_seen_at": utc_now(),
                    "source": str(item.path),
                    "bundle_id": bundle_id,
                    "profile": profile,
                }
            known_profiles[profile] = signature

            bundle = ConfigBundle(
                bundle_id=bundle_id,
                profile=profile,
                path=bundle_path.resolve(),
                files=tuple(staged_files),
                created_at=utc_now(),
            )
            manifest = bundle.to_manifest()
            with (bundle_path / "manifest.json").open("w", encoding="utf-8") as handle:
                json.dump(manifest, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            state.setdefault("bundles", {})[bundle_id] = manifest
            bundles.append(bundle)

        self.save_state(state)
        return tuple(bundles)

    def load_bundle(self, bundle_ref: str | Path) -> ConfigBundle:
        ref = Path(bundle_ref)
        candidates: list[Path] = []
        if ref.exists():
            candidates.append(ref)
        else:
            candidates.extend([self.staged / str(bundle_ref), self.applied / str(bundle_ref)])

        for candidate in candidates:
            manifest_path = candidate / "manifest.json" if candidate.is_dir() else candidate
            if not manifest_path.exists():
                continue
            with manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            return ConfigBundle(
                bundle_id=str(manifest["bundle_id"]),
                profile=str(manifest["profile"]),
                path=Path(manifest["path"]),
                created_at=str(manifest["created_at"]),
                files=tuple(
                    ConfigFile(
                        path=Path(item["path"]),
                        kind=str(item["kind"]),
                        sha256=str(item["sha256"]),
                        size_bytes=int(item["size_bytes"]),
                        modified_at=str(item["modified_at"]),
                        root_tag=str(item["root_tag"]),
                        warnings=tuple(item.get("warnings", ())),
                    )
                    for item in manifest["files"]
                ),
            )
        raise ConfigError(f"Bundle was not found: {bundle_ref}")

    def mark_applied(self, bundle: ConfigBundle, result: dict[str, Any]) -> None:
        state = self.load_state()
        state.setdefault("applied", {})[bundle.bundle_id] = {
            "applied_at": utc_now(),
            "result": result,
        }
        self.save_state(state)
