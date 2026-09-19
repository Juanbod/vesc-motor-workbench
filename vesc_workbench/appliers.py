from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from .configs import ConfigBundle


class ConfigApplyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConfigApplyResult:
    backend: str
    applied: bool
    message: str
    bundle_id: str
    profile: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ConfigApplier(Protocol):
    backend: str

    def apply(self, bundle: ConfigBundle, armed: bool = False) -> ConfigApplyResult:
        ...


class DryRunApplier:
    backend = "dry-run"

    def apply(self, bundle: ConfigBundle, armed: bool = False) -> ConfigApplyResult:
        kinds = ", ".join(sorted({item.kind for item in bundle.files}))
        return ConfigApplyResult(
            backend=self.backend,
            applied=False,
            message=(
                f"Dry run only. Bundle {bundle.bundle_id} contains {len(bundle.files)} "
                f"file(s), kinds: {kinds or 'none'}."
            ),
            bundle_id=bundle.bundle_id,
            profile=bundle.profile,
        )


class GuardedUartXmlApplier:
    backend = "uart-xml"

    def apply(self, bundle: ConfigBundle, armed: bool = False) -> ConfigApplyResult:
        if not armed:
            raise ConfigApplyError("Refusing UART XML apply without --armed.")
        raise ConfigApplyError(
            "Full VESC XML apply over UART is blocked until firmware version detection "
            "and a compatible binary config serializer are implemented."
        )


class VescToolOpenApplier:
    backend = "vesc-tool-open"

    def __init__(self, vesc_tool_path: str) -> None:
        self.vesc_tool_path = Path(vesc_tool_path) if vesc_tool_path else Path()

    def apply(self, bundle: ConfigBundle, armed: bool = False) -> ConfigApplyResult:
        if not self.vesc_tool_path.exists():
            raise ConfigApplyError(f"VESC Tool was not found: {self.vesc_tool_path}")
        return ConfigApplyResult(
            backend=self.backend,
            applied=False,
            message=(
                "VESC Tool backend is intentionally read-only for now. "
                f"Open VESC Tool and load staged files from {bundle.path}."
            ),
            bundle_id=bundle.bundle_id,
            profile=bundle.profile,
        )


def make_applier(backend: str, vesc_tool_path: str = "") -> ConfigApplier:
    normalized = backend.strip().lower()
    if normalized == "dry-run":
        return DryRunApplier()
    if normalized == "uart-xml":
        return GuardedUartXmlApplier()
    if normalized == "vesc-tool-open":
        return VescToolOpenApplier(vesc_tool_path)
    raise ConfigApplyError(f"Unknown apply backend: {backend}")

