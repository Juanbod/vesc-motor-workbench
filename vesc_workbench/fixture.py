"""Local fixture interlock for this workbench, not a hardware safety device."""
import json
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
import math

from .wire_config import decode_config, patch_config


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "config" / "bench-fixture.json"
_probe = ContextVar("locked_probe", default=None)


class FixtureInterlock(RuntimeError):
    pass


def require_locked():
    try:
        state = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        if (state.get("schema") == "vesc-fixture-v1" and state.get("rotor") == "locked"
                and state.get("confirmed_by_user") is True):
            return
    except (OSError, ValueError, AttributeError):
        pass
    raise FixtureInterlock("A confirmed locked fixture is required for this probe")


def require_free():
    try:
        state = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        if (state.get("schema") == "vesc-fixture-v1" and state.get("rotor") == "free"
                and state.get("confirmed_by_user") is True):
            return
    except (OSError, ValueError, AttributeError):
        pass
    raise FixtureInterlock("User must confirm physical fixture removal before alignment")


PROBE_LIMITS = dict(l_current_max=2, l_current_min=-2, l_abs_current_max=3,
                    l_in_current_max=1, l_in_current_min=0, l_max_duty=.1)


class LockedProbePermit:
    """One timed terminal command, bracketed by exact limit/restore writes.

    This is deliberately not a free-rotor authorization. ADC acquisition and
    arbitrary terminal commands remain prohibited.
    """
    def __init__(self, baseline):
        require_locked()
        values = decode_config(baseline, "motor")
        if values["motor_type"] != 2 or values["foc_mtpa_mode"] != 0:
            raise FixtureInterlock("Probe requires FOC with MTPA disabled")
        if values["l_current_max"] < 2 or values["l_abs_current_max"] < 3:
            raise FixtureInterlock("Probe must not raise the existing current limits")
        self.baseline = baseline
        self.limited = patch_config(baseline, "motor", PROBE_LIMITS)
        self.pulse = b"\x14rotor_lock_openloop 0.500 0.040 0.000"
        self.setup_sent = self.verified = self.pulse_sent = self.restored = False
        self.stopped = False

    def verify_limits(self, actual):
        if not self.setup_sent or actual != self.limited:
            raise FixtureInterlock("Exact protective-limit readback required")
        self.verified = True

    def adopt_existing_limits(self, actual):
        require_locked()
        if self.setup_sent or actual != self.limited:
            raise FixtureInterlock("Resume requires an exact existing protective configuration")
        self.setup_sent = True
        self.verified = True

    def verify_stopped(self, samples):
        if len(samples) < 3 or samples[-1]["t"] - samples[0]["t"] < .3:
            raise FixtureInterlock("Need a fresh standstill interval before restore")
        origin = samples[0]["position_deg"]
        for row in samples:
            for key in ("t", "current_motor_a", "erpm", "duty", "position_deg", "fault_code"):
                if not math.isfinite(row[key]):
                    raise FixtureInterlock("Invalid standstill telemetry")
            if (abs(row["current_motor_a"]) > .1 or abs(row["erpm"]) > 5
                    or abs(row["duty"]) > .001 or row["fault_code"] != 0
                    or abs((row["position_deg"] - origin + 180) % 360 - 180) > .5):
                raise FixtureInterlock("Rotor/current not quiet; leave protective limits in place")
        self.stopped = True

    def accept(self, payload):
        require_locked()
        if payload == b"\x0d" + self.limited and not self.setup_sent:
            self.setup_sent = True
            return True
        if payload == self.pulse and self.verified and not self.pulse_sent and not self.restored:
            self.pulse_sent = True
            self.stopped = False
            return True
        if payload == b"\x0d" + self.baseline and self.setup_sent and self.stopped and not self.restored:
            self.restored = True
            return True
        return False


@contextmanager
def locked_probe_permit(baseline):
    if _probe.get() is not None:
        raise FixtureInterlock("Nested probe authorization is forbidden")
    permit = LockedProbePermit(baseline)
    token = _probe.set(permit)
    try:
        yield permit
    finally:
        _probe.reset(token)


def verify_encoder_quiet(samples):
    """Standstill from independent encoder position, not observer ERPM."""
    if len(samples) < 10 or samples[-1]["t"] - samples[0]["t"] < .3:
        raise FixtureInterlock("A fresh encoder standstill interval is required")
    angles = []
    previous = None
    for row in samples:
        for key in ("t", "current_motor_a", "id_a", "iq_a", "duty", "position_deg", "fault_code"):
            if not isinstance(row[key], (int, float)) or not math.isfinite(row[key]):
                raise FixtureInterlock("Invalid standstill measurement")
        if previous is not None and not 0 < row["t"] - previous <= .1:
            raise FixtureInterlock("Encoder acquisition gap before restore")
        previous = row["t"]
        if (not 0 <= row["position_deg"] < 360 or abs(row["current_motor_a"]) > .1
                or math.hypot(row["id_a"], row["iq_a"]) > .2
                or abs(row["duty"]) > .001 or row["fault_code"] != 0):
            raise FixtureInterlock("Current/duty/fault not quiet before restore")
        angles.append((row["position_deg"] - samples[0]["position_deg"] + 180) % 360 - 180)
    if max(angles) - min(angles) > .5:
        raise FixtureInterlock("Encoder moved during standstill verification")


class LockedHfiPermit(LockedProbePermit):
    """One stock 400-sample HFI acquisition with bounded voltage and low trip."""
    def __init__(self, baseline, duty, plot_mode=2):
        super().__init__(baseline)
        if plot_mode not in (1, 2):
            raise FixtureInterlock("Unsupported HFI plot mode")
        self.plot_mode = plot_mode
        if duty not in (.005, .01, .02, .05, .1):
            raise FixtureInterlock("Only reviewed low HFI duty levels are permitted")
        changes = {**PROBE_LIMITS, "l_slow_abs_current": 0, "foc_f_zv": 30000}
        if plot_mode == 1:
            changes.update(foc_pll_kp=0, foc_pll_ki=0)
        self.limited = patch_config(baseline, "motor", changes)
        self.pulse = f"\x14measure_ind {duty:.3f}".encode("ascii")
        self.plot_enabled = False

    def verify_stopped(self, samples):
        verify_encoder_quiet(samples)
        self.stopped = True

    def accept(self, payload):
        require_locked()
        if payload == b"\x14foc_plot_hfi_en 0":
            return True
        if payload == f"\x14foc_plot_hfi_en {self.plot_mode}".encode() and self.verified and not self.pulse_sent and not self.restored:
            self.plot_enabled = True
            return True
        if payload == self.pulse and not self.plot_enabled:
            return False
        return super().accept(payload)


@contextmanager
def locked_hfi_permit(baseline, duty, plot_mode=2):
    if _probe.get() is not None:
        raise FixtureInterlock("Nested measurement authorization is forbidden")
    permit = LockedHfiPermit(baseline, duty, plot_mode)
    token = _probe.set(permit)
    try:
        yield permit
    finally:
        _probe.reset(token)


class LockedIsolationPermit:
    """Disable external drive in RAM once; never restore it while locked."""
    def __init__(self, app, samples):
        require_locked()
        verify_encoder_quiet(samples)
        self.isolated = patch_config(app, "app", dict(
            app_to_use=0, timeout_msec=300, timeout_brake_current=0))
        self.sent = False

    def accept(self, payload):
        require_locked()
        if payload == b"\x95" + self.isolated and not self.sent:
            self.sent = True
            return True
        return False


@contextmanager
def locked_isolation_permit(app, samples):
    if _probe.get() is not None:
        raise FixtureInterlock("Nested authorization is forbidden")
    permit = LockedIsolationPermit(app, samples)
    token = _probe.set(permit)
    try:
        yield permit
    finally:
        _probe.reset(token)


def check_payload(payload):
    # Keep zero-current stop available even if the state file is unreadable.
    # RPM=0, duty=0 and brake commands are deliberately NOT treated as stop.
    if payload == b"\x06\x00\x00\x00\x00":
        return
    if payload in (b"\x00", b"\x04", b"\x0e", b"\x11", b"\x14encoder",
                   b"\x14rotor_lock_openloop", b"\x14measure_ind", b"\x14foc_plot_hfi_en"):
        return
    permit = _probe.get()
    if permit is not None and permit.accept(payload):
        return
    try:
        state = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        if (state.get("schema") == "vesc-fixture-v1" and state.get("rotor") == "free"
                and state.get("confirmed_by_user") is True):
            return
    except (OSError, ValueError, AttributeError):
        pass
    raise FixtureInterlock(
        "Rotor is locked or its fixture state is unknown. Only read-only queries "
        "and zero-current stop are permitted. Do not clear the fixture state until "
        "the user confirms physical removal. Locked-rotor acquisition is not enabled.")
