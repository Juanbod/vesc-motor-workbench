from dataclasses import dataclass
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from vesc_workbench.fixture import FixtureInterlock, PROBE_LIMITS, check_payload, locked_probe_permit
from vesc_workbench.locked_probe import check_sample, preflight_config, run_probe
from vesc_workbench.uart import VescFirmwareVersion, VescValues
from vesc_workbench.wire_config import LAYOUTS, decode_config, patch_config


def config(kind, changes):
    layout = LAYOUTS[kind]
    raw = struct.pack(">I", layout["signature"]) + bytes(layout["size"] - 4)
    return patch_config(raw, kind, changes)


def motor():
    return config("motor", dict(motor_type=2, foc_mtpa_mode=0, l_current_max=10,
                                l_current_min=-10, l_abs_current_max=15, l_in_current_max=10,
                                l_in_current_min=-1, l_max_duty=.5, foc_sensor_mode=1,
                                m_sensor_port_mode=2, p_pid_ang_div=1, cc_min_current=.05,
                                foc_current_kp=.022, foc_current_ki=13.4,
                                foc_motor_l=.000022, foc_motor_r=.0134))


def app():
    return config("app", dict(app_to_use=0, timeout_msec=300, timeout_brake_current=0))


def quiet_samples():
    return [dict(t=i*.02, position_deg=30, current_motor_a=0, erpm=0, duty=0, fault_code=0)
            for i in range(21)]


class FakeClient:
    def __init__(self, clock, mismatch=False, current=.5):
        self.clock = clock
        self.motor, self.app = motor(), app()
        self.prints = []
        self.pid_position = 30.0
        self.pulse_at = None
        self.mismatch = mismatch
        self.current = current
        self.motor_writes = 0
        self.pulse_count = 0
        self.complete_printed = False
        self.usage_echoed = False

    def fw_version(self):
        return VescFirmwareVersion(6, 2, "MKSESC_84_100_HP")

    def get_raw_config(self, kind):
        if kind == "motor" and self.mismatch and self.motor_writes == 1:
            return motor()
        return self.motor if kind == "motor" else self.app

    def set_raw_config(self, kind, data):
        check_payload(bytes((13,)) + data)
        self.motor_writes += 1
        self.motor = data

    def send_payload(self, payload):
        check_payload(payload)
        if payload.startswith(b"\x14rotor_lock_openloop "):
            self.pulse_at = self.clock[0]
            self.pulse_count += 1
            self.prints.append(dict(t=self.clock[0], text="Locking rotor with openloop..."))

    def read_response(self, command):
        if command == 21:
            if not self.usage_echoed:
                self.usage_echoed = True
                return b"\x15-> rotor_lock_openloop"
            return b"\x15This command requires three arguments. [current time angle]\n"
        return bytes((command,))

    def set_current(self, value):
        if value != 0:
            raise AssertionError("No direct nonzero current allowed")
        check_payload(b"\x06\x00\x00\x00\x00")

    def get_values(self):
        self.clock[0] += .0005
        age = 1 if self.pulse_at is None else self.clock[0] - self.pulse_at
        current = self.current if self.pulse_at is not None and age < .04 else 0
        if self.pulse_at is not None and age >= .04 and not self.complete_printed:
            self.prints.append(dict(t=self.clock[0], text="Done"))
            self.complete_printed = True
        return VescValues(27, -50, current, .01 if current else 0, 0, current,
                          .005 if current else 0, 0, 25, 0)


class LockedProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fixture.json"
        self.path.write_text(json.dumps(dict(schema="vesc-fixture-v1", rotor="locked", confirmed_by_user=True)))
        p = patch("vesc_workbench.fixture.FIXTURE_PATH", self.path)
        p.start()
        self.addCleanup(p.stop)

    def test_exact_setup_verified_single_pulse_and_quiet_restore(self):
        baseline = motor()
        with locked_probe_permit(baseline) as permit:
            with self.assertRaises(FixtureInterlock):
                check_payload(permit.pulse)
            check_payload(b"\x0d" + permit.limited)
            with self.assertRaises(FixtureInterlock):
                check_payload(permit.pulse)
            permit.verify_limits(permit.limited)
            check_payload(permit.pulse)
            with self.assertRaises(FixtureInterlock):
                check_payload(permit.pulse)
            with self.assertRaises(FixtureInterlock):
                check_payload(b"\x0d" + baseline)
            permit.verify_stopped(quiet_samples())
            check_payload(b"\x0d" + baseline)
            with self.assertRaises(FixtureInterlock):
                check_payload(permit.pulse)
        with self.assertRaises(FixtureInterlock):
            check_payload(permit.pulse)

    def test_no_arbitrary_commands_or_mutated_limits(self):
        with locked_probe_permit(motor()) as permit:
            for packet in (b"\x14rotor_lock_openloop 1 0.1 0", b"\x08\x00\x00\x00\x00",
                           b"\x14foc_openloop .5 10", b"\x14measure_ind 0.01",
                           b"\x0d" + patch_config(permit.limited, "motor", {"l_current_max": 4})):
                with self.assertRaises(FixtureInterlock):
                    check_payload(packet)
            with self.assertRaises(FixtureInterlock):
                with locked_probe_permit(motor()):
                    pass

    def test_bad_readback_and_moving_restore_are_blocked(self):
        with locked_probe_permit(motor()) as permit:
            check_payload(b"\x0d" + permit.limited)
            with self.assertRaises(FixtureInterlock):
                permit.verify_limits(motor())
            rows = quiet_samples()
            rows[-1]["current_motor_a"] = .2
            with self.assertRaises(FixtureInterlock):
                permit.verify_stopped(rows)

    def test_resume_requires_exact_protective_bytes(self):
        with locked_probe_permit(motor()) as permit:
            with self.assertRaises(FixtureInterlock):
                permit.adopt_existing_limits(motor())
            permit.adopt_existing_limits(permit.limited)
            check_payload(permit.pulse)
            with self.assertRaises(FixtureInterlock):
                permit.adopt_existing_limits(permit.limited)

    def test_normal_commands_stay_blocked_when_fixture_changes(self):
        with locked_probe_permit(motor()) as permit:
            self.path.write_text("{}")
            with self.assertRaises(FixtureInterlock):
                check_payload(b"\x0d" + permit.limited)

    def test_config_preflight(self):
        fw = dict(major=6, minor=2, hardware="MKSESC_84_100_HP")
        preflight_config(fw, motor(), app())
        for changes in ({"app_to_use": 5}, {"timeout_msec": 1000}, {"timeout_brake_current": 1}):
            with self.assertRaises(ValueError):
                preflight_config(fw, motor(), patch_config(app(), "app", changes))
        for changes in ({"foc_mtpa_mode": 1}, {"foc_sensor_mode": 0}, {"cc_min_current": 1},
                        {"foc_current_ki": 100}, {"p_pid_ang_div": 2}):
            with self.assertRaises(ValueError):
                preflight_config(fw, patch_config(motor(), "motor", changes), app())

    def test_probe_does_not_raise_tight_current_limits(self):
        with self.assertRaises(FixtureInterlock):
            with locked_probe_permit(patch_config(motor(), "motor", {"l_current_max": 1})):
                pass

    def test_sample_trip_conditions(self):
        row = dict(t=0, position_deg=30, current_motor_a=.5, current_in_a=.01,
                   id_a=0, iq_a=.5, erpm=0, duty=.005, fault_code=0, temp_mos_c=27,
                   temp_motor_c=-50, v_in=25)
        check_sample(row, 30)
        for changes in ({"iq_a": 2}, {"position_deg": 31}, {"v_in": 40},
                        {"fault_code": 1}, {"temp_mos_c": 60}, {"erpm": 30}):
            with self.assertRaises(ValueError):
                check_sample({**row, **changes}, 30)

    def run_fake(self, **kwargs):
        clock = [0.0]
        client = FakeClient(clock, **kwargs)
        with patch("vesc_workbench.locked_probe.monotonic", side_effect=lambda: clock[0]), \
             patch("vesc_workbench.locked_probe.sleep", side_effect=lambda dt: clock.__setitem__(0, clock[0] + dt)):
            result = run_probe(client, Path(self.temp.name) / "output")
        return result, client

    def test_complete_probe_sends_once_and_restores_exactly(self):
        result, client = self.run_fake()
        self.assertTrue(result["ok"], result)
        self.assertEqual(client.pulse_count, 1)
        self.assertEqual(client.motor_writes, 2)
        self.assertEqual(client.motor, motor())
        self.assertTrue(result["physical_excitation_verified"])

    def test_failed_protective_readback_never_excites(self):
        result, client = self.run_fake(mismatch=True)
        self.assertFalse(result["ok"])
        self.assertEqual(client.pulse_count, 0)
        self.assertTrue(result["motor_restored"])

    def test_zero_current_is_not_called_a_physical_success(self):
        result, client = self.run_fake(current=0)
        self.assertEqual(client.pulse_count, 1)
        self.assertFalse(result["ok"])
        self.assertFalse(result["physical_excitation_verified"])
        self.assertTrue(result["motor_restored"])
