from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from collections import deque
import io
import json
import math
import struct

from vesc_workbench.bench import BenchPlan, BenchStop, Campaign, EncoderMotion, SimulatedBench, guard, HardwareBench, validate_motor_math
from vesc_workbench.uart import VescUartClient, VescPacketError, encode_packet
from vesc_workbench.wire_config import LAYOUTS, decode_config, patch_config


class BenchTests(TestCase):
    def test_extended_diagnostics_remain_bounded(self):
        p = replace(BenchPlan(), allow_missing_motor_temp=True, extended_diagnostics=True,
                    test_current_a=10, phase_limit_a=12, trip_current_a=18,
                    trial_s=5, trial_i2t=650, cooldown_s=8, total_energy_j=300, trial_energy_j=100)
        p.validate()
        for changed in (replace(p, phase_limit_a=16), replace(p, trial_s=6), replace(p, cooldown_s=1), replace(p, extended_diagnostics=False)):
            with self.assertRaises(ValueError):
                changed.validate()
    def test_negative_flux_and_zero_division_rejected(self):
        v = dict(foc_motor_flux_linkage=-4.24e-5, foc_mtpa_mode=1, foc_sat_comp_mode=2, foc_observer_type=3)
        with self.assertRaises(BenchStop):
            validate_motor_math(v)
        with self.assertRaises(BenchStop):
            validate_motor_math({**v, 'foc_motor_flux_linkage': 0})
        validate_motor_math({**v, 'foc_motor_flux_linkage': 0, 'foc_sat_comp_mode': 0, 'foc_observer_type': 0})

    def campaign(self, root, fault="", plan=None, cls=SimulatedBench):
        bench = cls(fault)
        p = plan or replace(BenchPlan(), allow_missing_motor_temp=True, cooldown_s=.5)
        c = Campaign(bench, p, root / "run", simulated=True)
        c.run()
        return c, bench, json.loads((c.output / "status.json").read_text())

    def test_full_campaign_and_best_export(self):
        with TemporaryDirectory() as tmp:
            c, b, status = self.campaign(Path(tmp))
            self.assertEqual(status["state"], "completed", status)
            self.assertEqual(status["best"]["changes"]["foc_mtpa_mode"], 1)
            self.assertTrue((c.output / "recommended" / "simulation-only.json").exists())
            self.assertTrue(b.stopped)
            self.assertGreaterEqual(sum(r["name"].startswith("repeat") for r in status["results"]), 2)

    def test_lock_is_not_a_success_and_queue_can_continue(self):
        with TemporaryDirectory() as tmp:
            c, b, status = self.campaign(Path(tmp), "stall")
            self.assertEqual(status["state"], "no_reliable_start")
            self.assertIsNone(status["best"])
            self.assertEqual(len(status["results"]), 6)
            self.assertTrue(all(r["status"] == "stalled" for r in status["results"]))
            self.assertTrue(b.stopped)

    def test_reverse_rejected(self):
        with TemporaryDirectory() as tmp:
            c, b, status = self.campaign(Path(tmp), "reverse")
            self.assertIsNone(status["best"])
            self.assertTrue(any(r["status"] == "wrong_direction" for r in status["results"]))

    def test_faults_disconnect_and_stale_stop_campaign(self):
        for failure in ("fault", "disconnect", "hot", "stale", "no_current"):
            with self.subTest(failure=failure), TemporaryDirectory() as tmp:
                c, b, status = self.campaign(Path(tmp), failure)
                self.assertEqual(status["state"], "stopped")
                self.assertIsNone(status["best"])
                self.assertTrue(b.stopped)
                self.assertTrue((c.output / "summary.csv").exists())

    def test_readback_failure_never_commands_nonzero(self):
        class BadWrite(SimulatedBench):
            def apply(self, changes):
                raise BenchStop("Readback failed")
            def current(self, value):
                if value:
                    raise AssertionError("Motor commanded after failed write")
                super().current(value)
        with TemporaryDirectory() as tmp:
            c, b, status = self.campaign(Path(tmp), cls=BadWrite)
            self.assertEqual(status["state"], "stopped")
            self.assertEqual(status["results"][0]["error"], "Readback failed")

    def test_stop_file_interrupts_after_preflight(self):
        class StopBench(SimulatedBench):
            def prepare(self, plan):
                super().prepare(plan)
                (root / "run" / "STOP").touch()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            c, b, status = self.campaign(root, cls=StopBench)
            self.assertEqual(status["state"], "stopped")
            self.assertEqual(status["results"], [])

    def test_energy_budget_and_trial_limit(self):
        for p in (replace(BenchPlan(), total_energy_j=.2), replace(BenchPlan(), max_trials=1)):
            with TemporaryDirectory() as tmp:
                c, b, status = self.campaign(Path(tmp), plan=p)
                self.assertEqual(status["state"], "stopped")
                self.assertLessEqual(len(status["results"]), 1)
                self.assertTrue(b.stopped)

    def test_no_temperature_prevents_high_power_plan(self):
        for p in (replace(BenchPlan(), test_current_a=math.nan), replace(BenchPlan(), allow_missing_motor_temp=True, phase_limit_a=7), replace(BenchPlan(), direction=0)):
            with self.assertRaises(ValueError):
                p.validate()

    def test_motion_wraparound_and_direction(self):
        m = EncoderMotion(2, 1)
        m.update([(0, 350), (.1, 10), (.2, 30)])
        self.assertAlmostEqual(m.turns, 40 / 360)
        self.assertGreater(m.speed, 0)
        inv = EncoderMotion(2, -1)
        inv.update([(0, 350), (.1, 10)])
        self.assertLess(inv.speed, 0)

    def test_unavailable_temperature_and_nan_are_rejected(self):
        b = SimulatedBench()
        b.prepare(BenchPlan())
        v = b.sample()
        for changes in ({"temp_motor_c": -49.8}, {"encoder_angle": None}, {"iq_a": math.nan}):
            with self.assertRaises(BenchStop):
                guard({**v, **changes}, BenchPlan())

    def test_schema_patch_changes_only_named_fields(self):
        for kind, layout in LAYOUTS.items():
            data = struct.pack(">I", layout["signature"]) + bytes(layout["size"] - 4)
            key, value = ("foc_encoder_offset", 267.53) if kind == "motor" else ("timeout_msec", 300)
            modified = patch_config(data, kind, {key: value})
            self.assertAlmostEqual(decode_config(modified, kind)[key], value, places=4)
            off = layout["fields"][key]["offset"]
            self.assertEqual(modified[:off], data[:off])
            self.assertEqual(modified[off+4:], data[off+4:])
            with self.assertRaises(ValueError):
                patch_config(data[:-1], kind, {key: value})
            with self.assertRaises(ValueError):
                patch_config(bytes(4) + data[4:], kind, {key: value})

    def test_unsolicited_encoder_packets_do_not_break_rpc(self):
        client = VescUartClient.__new__(VescUartClient)
        client.serial = io.BytesIO(encode_packet(bytes((22,)) + struct.pack(">i", 12300000)) + encode_packet(b"\x0econfig"))
        client.rotor_samples = deque()
        client.response_timeout_s = .5
        self.assertEqual(client.read_response(14), b"\x0econfig")
        self.assertEqual(client.rotor_angle, 123)

    def test_cleanup_reports_failed_rollback(self):
        class FakeClient:
            def set_current(self, value): pass
            def set_raw_config(self, kind, data): raise OSError("USB gone")
            def close(self): self.closed = True
        b = HardwareBench.__new__(HardwareBench)
        b.client, b.active, b.modified, b.motor = FakeClient(), True, True, b"original"
        b.isolated = True
        b.sample = lambda: (_ for _ in ()).throw(OSError("USB gone"))
        result = b.close()
        self.assertFalse(result["motor_restored"])
        self.assertIn("USB gone", result["error"])
        self.assertTrue(b.client.closed)

    def test_speed_profile_uses_corrected_speed(self):
        c = Campaign(SimulatedBench(), BenchPlan(), Path("unused"), True)
        self.assertEqual(c.common()["foc_speed_soure"], 0)

    def test_rollback_waits_for_coast_and_never_writes_while_moving(self):
        for coast_seconds, restored in ((12, True), (40, False)):
            with self.subTest(coast_seconds=coast_seconds):
                now = [0.0]
                writes = []
                class Client:
                    def set_current(self, value):
                        if value != 0:
                            raise AssertionError('Recovery must never drive')
                    def set_raw_config(self, kind, data):
                        if now[0] < coast_seconds + .4:
                            raise AssertionError('Configuration written before verified standstill')
                        writes.append(data)
                    def read_response(self, command): pass
                    def get_raw_config(self, kind): return b'baseline'
                    def stream_encoder(self, enabled): pass
                    def close(self): pass
                b = HardwareBench.__new__(HardwareBench)
                b.client, b.active, b.isolated = Client(), True, True
                b.modified, b.motor, b.rollback_timeout_s = True, b'baseline', 30
                b.sample = lambda: dict(encoder_age=0, current_motor_a=0,
                                       encoder_erpm=50 if now[0] < coast_seconds else 0)
                with patch('vesc_workbench.bench.monotonic', side_effect=lambda: now[0]), \
                     patch('vesc_workbench.bench.sleep', side_effect=lambda dt: now.__setitem__(0, now[0]+dt)):
                    result = b.close()
                self.assertEqual(result['motor_restored'], restored)
                self.assertEqual(bool(writes), restored)
                if not restored:
                    self.assertIn('standstill', result['error'])

    def test_rollback_timeout_is_bounded(self):
        for seconds in (.5, 61):
            with self.assertRaises(ValueError):
                replace(BenchPlan(), rollback_timeout_s=seconds).validate()

    def test_speed_ramp_is_explicit_and_bounded(self):
        p = replace(BenchPlan(), speed_ramp_erpm_s=600)
        p.validate()
        c = Campaign(SimulatedBench(), p, Path('unused'), True)
        self.assertEqual(c.common()['s_pid_ramp_erpms_s'], 600)
        for value in (99, 601, float('nan')):
            with self.assertRaises(ValueError):
                replace(p, speed_ramp_erpm_s=value).validate()
