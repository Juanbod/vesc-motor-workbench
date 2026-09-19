import copy
from dataclasses import replace
import importlib.util
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vesc_workbench.locked_rotor import (
    LockedRotorPlan, analyze, analyze_pose, axial_delta, canonical_digest,
    preparation, report_text, simulated_dataset,
)


ROOT = Path(__file__).resolve().parents[1]


class LockedRotorTests(unittest.TestCase):
    def setUp(self):
        self.data = simulated_dataset(noise=0)

    def reject_sample(self, key, value):
        data = copy.deepcopy(self.data)
        data["poses"][0]["samples"][0][key] = value
        self.assertEqual(analyze(data)["status"], "rejected")

    def test_default_plan_grid_and_bounds(self):
        p = LockedRotorPlan()
        self.assertEqual(len(p.schedule()), 36)
        for changes in ({"angle_count": 11}, {"repeats": 2}, {"max_pole_pairs": True},
                        {"max_current_a": 3.1}, {"max_burst_s": .051},
                        {"min_cooldown_s": 7.9}, {"d_axis": "observer"},
                        {"max_rotor_drift_deg": math.nan}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(p, **changes).validate()

    def test_recovers_ratio_direction_and_offset_modulo_180(self):
        result = analyze(self.data)
        self.assertEqual(result["status"], "candidate_only")
        c = result["candidate"]
        self.assertEqual(c["pole_pairs"], 2)
        self.assertFalse(c["encoder_inverted"])
        self.assertAlmostEqual(axial_delta(c["offset_mod_180_deg"], 357.52764892578125), 0)
        self.assertAlmostEqual(c["offset_candidates_deg"][1] - c["offset_candidates_deg"][0], 180)
        self.assertFalse(result["hardware_validated"])
        self.assertFalse(result["auto_apply_allowed"])

    def test_direction_ratio_and_wraparound(self):
        for pairs in (1, 2, 7, 8):
            for inverted in (False, True):
                for offset in (0, .1, 179.9, 359.9):
                    with self.subTest(pairs=pairs, inverted=inverted, offset=offset):
                        r = analyze(simulated_dataset(pole_pairs=pairs, inverted=inverted,
                                                      offset_deg=offset, noise=0))
                        self.assertEqual(r["status"], "candidate_only")
                        c = r["candidate"]
                        self.assertEqual(c["pole_pairs"], pairs)
                        self.assertEqual(c["encoder_inverted"], inverted)
                        self.assertAlmostEqual(axial_delta(c["offset_mod_180_deg"], offset), 0)

    def test_max_l_d_axis_convention(self):
        p = replace(LockedRotorPlan(), d_axis="maximum_inductance")
        r = analyze(simulated_dataset(p, offset_deg=41, noise=0))
        self.assertAlmostEqual(r["candidate"]["offset_mod_180_deg"], 41)
        self.assertEqual(r["candidate"]["d_axis"], "maximum_inductance")

    def test_inverse_inductance_extrema(self):
        pose = analyze_pose(self.data["poses"][0], LockedRotorPlan())
        self.assertAlmostEqual(pose["l_min_h"], 1 / 67000)
        self.assertAlmostEqual(pose["l_max_h"], 1 / 33000)

    def test_low_noise_is_accepted(self):
        r = analyze(simulated_dataset(noise=.004))
        self.assertEqual(r["status"], "candidate_only")
        self.assertLess(abs(axial_delta(r["candidate"]["offset_mod_180_deg"], 357.52765)), .2)

    def test_high_noise_is_rejected(self):
        self.assertEqual(analyze(simulated_dataset(noise=.3))["status"], "rejected")

    def test_no_saliency_is_rejected(self):
        for row in self.data["poses"][0]["samples"]:
            row["response_inv_h"] = 50000
        self.assertEqual(analyze(self.data)["status"], "rejected")

    def test_weak_saliency_is_rejected(self):
        for row in self.data["poses"][0]["samples"]:
            row["response_inv_h"] = 50000 + .01 * (row["response_inv_h"] - 50000)
        self.assertEqual(analyze(self.data)["status"], "rejected")

    def test_higher_harmonic_rejected(self):
        for row in self.data["poses"][0]["samples"]:
            row["response_inv_h"] += 5000 * math.cos(math.radians(4 * row["phase_deg"]))
        self.assertEqual(analyze(self.data)["status"], "rejected")

    def test_disagreeing_repeats_rejected(self):
        rows = self.data["poses"][0]["samples"]
        for row in rows:
            if row["repeat"] == 1:
                row["response_inv_h"] = 50000 + 17000 * math.cos(math.radians(2 * row["phase_deg"]))
        self.assertEqual(analyze(self.data)["status"], "rejected")

    def test_incomplete_duplicate_and_offgrid_measurements(self):
        for kind in ("missing", "duplicate", "offgrid"):
            data = copy.deepcopy(self.data)
            rows = data["poses"][0]["samples"]
            if kind == "missing":
                rows.pop()
            elif kind == "duplicate":
                rows[0] = copy.deepcopy(rows[1])
            else:
                rows[0]["phase_deg"] = 3
            self.assertEqual(analyze(data)["status"], "rejected")

    def test_fault_current_staleness_and_pulse_limits(self):
        for key, value in (("fault", 1), ("fault", False), ("encoder_age_s", .11),
                           ("encoder_age_s", -.1), ("peak_current_a", 3.1),
                           ("peak_current_a", -1), ("peak_current_a", 0),
                           ("i2t_a2s", 0), ("burst_s", .06), ("burst_s", 0),
                           ("energy_j", 2.1), ("i2t_a2s", 5.1), ("encoder_deg", 360),
                           ("response_inv_h", -1), ("repeat", False)):
            with self.subTest(key=key, value=value):
                self.reject_sample(key, value)

    def test_nonfinite_input_never_emits_candidate_or_nonfinite_json(self):
        for value in (math.nan, math.inf, -math.inf, "nan", None, True):
            for key in ("response_inv_h", "peak_current_a", "encoder_deg"):
                self.reject_sample(key, value)
        self.data["simulated"] = math.nan
        r = analyze(self.data)
        self.assertEqual(r["status"], "rejected")
        json.dumps(r, allow_nan=False)

    def test_pose_energy_and_i2t_budget(self):
        for key, value in (("energy_j", .1), ("i2t_a2s", .2)):
            data = copy.deepcopy(self.data)
            for row in data["poses"][0]["samples"]:
                row[key] = value
            self.assertEqual(analyze(data)["status"], "rejected")

    def test_movement_rejected(self):
        self.reject_sample("encoder_deg", 351.6)

    def test_encoder_wrap_small_motion_is_not_a_full_turn(self):
        pose = self.data["poses"][0]
        for i, row in enumerate(pose["samples"]):
            row["encoder_deg"] = .1 if i % 2 else 359.9
        self.assertAlmostEqual(analyze_pose(pose, LockedRotorPlan())["rotor_drift_deg"], .2)

    def test_one_pose_cannot_calibrate_direction(self):
        self.data["poses"] = self.data["poses"][:1]
        self.assertEqual(analyze(self.data)["status"], "rejected")

    def test_repeated_pose_does_not_falsely_confirm_ratio(self):
        first = self.data["poses"][0]
        self.data["poses"] = [{**copy.deepcopy(first), "pose_id": str(i)} for i in range(4)]
        r = analyze(self.data)
        self.assertEqual(r["status"], "ambiguous")
        self.assertIsNone(r["candidate"])

    def test_bad_frame_schema_flag_and_pose_ids(self):
        for key, value in (("schema", "other"), ("frame", "rotor_dq"),
                           ("quantity", "get_values_current"), ("simulated", 1)):
            data = {**self.data, key: value}
            self.assertEqual(analyze(data)["status"], "rejected")
        self.data["poses"][1]["pose_id"] = self.data["poses"][0]["pose_id"]
        self.assertEqual(analyze(self.data)["status"], "rejected")

    def test_malformed_payloads_rejected(self):
        for data in (None, [], {}, {"simulated": False}, {**self.data, "plan": {"typo": 1}}):
            self.assertEqual(analyze(data)["status"], "rejected")

    def test_preparation_never_enables_hardware(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline = Path(temp) / "mcconf.bin"
            baseline.write_bytes(b"baseline")
            prepared = preparation(baseline=baseline)
            self.assertEqual(len(prepared["baseline_sha256"]), 64)
            self.assertEqual(baseline.read_bytes(), b"baseline")
        self.assertFalse(prepared["controller_connected"])
        self.assertFalse(prepared["acquisition_enabled"])
        self.assertGreater(len(prepared["gates"]), 0)

    def test_deterministic_hash_and_report_warning(self):
        self.assertEqual(canonical_digest(self.data), canonical_digest(copy.deepcopy(self.data)))
        self.assertEqual(simulated_dataset(), simulated_dataset())
        self.assertIn("SYNTHETIC DATA", report_text(analyze(self.data)))
        self.data["simulated"] = False
        r = analyze(self.data)
        self.assertFalse(r["hardware_validated"])
        self.assertFalse(r["auto_apply_allowed"])

    def test_cli_simulation_replay_and_no_overwrite(self):
        spec = importlib.util.spec_from_file_location("locked_cli", ROOT / "scripts/calibrate-locked-rotor.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as temp, patch("serial.Serial", side_effect=AssertionError("Serial forbidden")), \
                patch("sys.stdout", new_callable=io.StringIO):
            output, replay = Path(temp) / "sim", Path(temp) / "replay"
            self.assertEqual(cli.main(["simulate", "--output", str(output)]), 0)
            self.assertEqual(cli.main(["analyze", "--input", str(output / "dataset.json"), "--output", str(replay)]), 0)
            self.assertEqual((output / "result.json").read_bytes(), (replay / "result.json").read_bytes())
            with self.assertRaises(FileExistsError):
                cli.main(["simulate", "--output", str(output)])
            with patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
                cli.main(["simulate", "--output", str(output), "--armed"])


if __name__ == "__main__":
    unittest.main()
