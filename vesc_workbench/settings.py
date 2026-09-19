from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tomllib


@dataclass(frozen=True)
class SerialSettings:
    port: str = "COM3"
    baudrate: int = 115200
    timeout_s: float = 0.10


@dataclass(frozen=True)
class PathSettings:
    incoming: Path
    staged: Path
    applied: Path
    logs: Path


@dataclass(frozen=True)
class ApplySettings:
    backend: str = "dry-run"
    require_armed: bool = True
    vesc_tool_path: str = ""


@dataclass(frozen=True)
class SafetySettings:
    max_erpm: int = 1000
    max_erpm_delta: int = 500
    sample_period_s: float = 0.05
    default_current_steps: tuple[float, ...] = (0.5, 1.0, 1.5)


@dataclass(frozen=True)
class Settings:
    root: Path
    serial: SerialSettings
    paths: PathSettings
    apply: ApplySettings
    safety: SafetySettings


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    return value if isinstance(value, dict) else {}


def _path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_settings(root: Path | None = None, config_path: Path | None = None) -> Settings:
    project_root = (root or Path.cwd()).resolve()
    data: dict[str, Any] = {}

    if config_path is None:
        candidate = project_root / "config" / "settings.toml"
        config_path = candidate if candidate.exists() else None

    if config_path is not None and config_path.exists():
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)

    serial = _section(data, "serial")
    paths = _section(data, "paths")
    apply = _section(data, "apply")
    safety = _section(data, "safety")

    return Settings(
        root=project_root,
        serial=SerialSettings(
            port=str(serial.get("port", "COM3")),
            baudrate=int(serial.get("baudrate", 115200)),
            timeout_s=float(serial.get("timeout_s", 0.10)),
        ),
        paths=PathSettings(
            incoming=_path(project_root, str(paths.get("incoming", "profiles/incoming"))),
            staged=_path(project_root, str(paths.get("staged", "profiles/staged"))),
            applied=_path(project_root, str(paths.get("applied", "profiles/applied"))),
            logs=_path(project_root, str(paths.get("logs", "logs"))),
        ),
        apply=ApplySettings(
            backend=str(apply.get("backend", "dry-run")),
            require_armed=bool(apply.get("require_armed", True)),
            vesc_tool_path=str(apply.get("vesc_tool_path", "")),
        ),
        safety=SafetySettings(
            max_erpm=int(safety.get("max_erpm", 1000)),
            max_erpm_delta=int(safety.get("max_erpm_delta", 500)),
            sample_period_s=float(safety.get("sample_period_s", 0.05)),
            default_current_steps=tuple(
                float(item) for item in safety.get("default_current_steps", [0.5, 1.0, 1.5])
            ),
        ),
    )


def ensure_project_dirs(settings: Settings) -> None:
    for path in (
        settings.paths.incoming,
        settings.paths.staged,
        settings.paths.applied,
        settings.paths.logs,
        settings.root / ".vesc-workbench",
    ):
        path.mkdir(parents=True, exist_ok=True)

