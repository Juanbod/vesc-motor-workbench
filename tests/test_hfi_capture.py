import json
import math
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from vesc_workbench.fixture import FixtureInterlock, check_payload, locked_hfi_permit, verify_encoder_quiet
from vesc_workbench.hfi_capture import PlotDecoder, analyze_hfi, analyze_dft, summarize_dft_runs, guard_sample, write_motor_verified
from test_locked_probe import motor, quiet_samples


def raw_points(axis=43, generation=1, cycles=2, noise=0):
    points = []
    for n in range(32 * cycles):
        k = n % 32
        phi = k * 360 / 32 - 90
        response = 50000 + 17000 * math.cos(math.radians(2*(phi-axis)))
        l_uh = 1e6 / response + noise * math.cos(math.radians(4*phi))
        for graph, value in ((0, .3), (1, l_uh)):
            points.append(dict(t=n*.005 + graph*.0001, index=k, value=value,
                               graph=graph, generation=generation))
    return points


class HfiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / "fixture.json"
        path.write_text(json.dumps(dict(schema="vesc-fixture-v1", rotor="locked", confirmed_by_user=True)))
        p = patch("vesc_workbench.fixture.FIXTURE_PATH", path)
        p.start()
        self.addCleanup(p.stop)

    def test_plot_packet_decode_and_graph_pair(self):
        d = PlotDecoder()
        d.feed(b"\x4bSample\0Value\0", 0)
        d.feed(b"\x4dCurrent (A)\0", 0)
        d.feed(b"\x4e\x00", 0)
        d.feed(b"\x4c" + struct.pack(">ff", 3, .25), .1)
        self.assertEqual(d.points[0]["index"], 3)
        self.assertAlmostEqual(d.points[0]["value"], .25)
        self.assertEqual(d.names, ["Current (A)"])

    def test_malformed_or_unlabelled_points_rejected(self):
        for payload in (b"\x4c" + struct.pack(">ff", 0, 1), b"\x4e\x02"):
            with self.assertRaises(ValueError):
                PlotDecoder().feed(payload, 0)
        for x, y in ((32, 1), (-1, 1), (.5, 1), (0, math.nan), (0, math.inf)):
            d = PlotDecoder()
            d.feed(b"\x4e\x01", 0)
            with self.assertRaises(ValueError):
                d.feed(b"\x4c" + struct.pack(">ff", x, y), 0)

    def test_axis_mapping_accounts_for_minus_90_degree_excitation(self):
        for axis in (0, 43, 89, 135, 179):
            r = analyze_hfi(raw_points(axis), 307.8, 2, False, 267.5)
            self.assertEqual(r["status"], "single_pose_candidate")
            c = r["candidate"]
            self.assertLess(abs((c["minimum_inductance_axis_deg"] - axis + 90) % 180 - 90), 1e-8)
            expected = (2*307.8 - axis) % 180
            self.assertAlmostEqual(c["offset_candidates_deg"][0], expected)
            self.assertFalse(r["applied"])
            self.assertFalse(r["ratio_direction_independently_validated"])

    def test_inverted_offset_convention(self):
        r = analyze_hfi(raw_points(43), 307.8, 2, True, 267.5)
        self.assertAlmostEqual(r["candidate"]["offset_candidates_deg"][0], (-2*307.8-43) % 180)

    def test_partial_missing_duplicate_and_unpaired_curves(self):
        for points in (raw_points(cycles=1)[2:], raw_points(cycles=1)[:-2],
                       raw_points(cycles=1)[::2]):
            self.assertIsNone(analyze_hfi(points, 30, 2, False, 0)["candidate"])
        pts = raw_points(cycles=1)
        pts[20:22] = pts[18:20]
        self.assertIsNone(analyze_hfi(pts, 30, 2, False, 0)["candidate"])

    def test_bad_l_or_small_delta_current_rejected_not_reused(self):
        for graph, value in ((0, .005), (0, 2), (1, 0), (1, 3000)):
            pts = raw_points()
            pts[graph]["value"] = value
            r = analyze_hfi(pts, 30, 2, False, 0)
            self.assertIsNone(r["candidate"])
            self.assertTrue(r["rejected_curves"])

    def test_noise_and_disagreeing_axes_rejected(self):
        self.assertIsNone(analyze_hfi(raw_points(noise=5), 30, 2, False, 0)["candidate"])
        pts = raw_points(43, cycles=1) + raw_points(63, generation=2, cycles=1)
        self.assertEqual(analyze_hfi(pts, 30, 2, False, 0)["status"], "inconsistent_axes")

    def test_no_saliency_rejected(self):
        pts = raw_points()
        for p in pts:
            if p["graph"] == 1:
                p["value"] = 20
        self.assertIsNone(analyze_hfi(pts, 30, 2, False, 0)["candidate"])

    def test_observer_erpm_not_a_motion_guard(self):
        row = dict(position_deg=30, current_motor_a=.1, current_in_a=0, id_a=.1, iq_a=0,
                   duty=.01, erpm=-2000, fault_code=0, v_in=25, temp_mos_c=27, temp_motor_c=-50, t=0)
        guard_sample(row, 30)
        with self.assertRaises(ValueError):
            guard_sample({**row, "position_deg": 31}, 30)

    def test_quiet_restore_uses_encoder_and_current_not_observer(self):
        rows = [{**r, "id_a": 0, "iq_a": 0, "erpm": 2000} for r in quiet_samples()]
        verify_encoder_quiet(rows)
        rows[-1]["position_deg"] += 1
        with self.assertRaises(FixtureInterlock):
            verify_encoder_quiet(rows)

    def test_configuration_timeout_restored_on_success_and_failure(self):
        c = Mock()
        c.serial = SimpleNamespace(timeout=.15)
        c.get_raw_config.return_value = b"expected"
        def ack(_):
            self.assertEqual(c.serial.timeout, 2)
        c.read_response.side_effect = ack
        self.assertEqual(write_motor_verified(c, b"expected"), b"expected")
        self.assertEqual(c.serial.timeout, .15)
        c.read_response.side_effect = OSError("USB")
        with self.assertRaises(OSError):
            write_motor_verified(c, b"expected")
        self.assertEqual(c.serial.timeout, .15)

    def test_hfi_permission_requires_limits_plot_and_single_dispatch(self):
        with locked_hfi_permit(motor(), .01) as p:
            with self.assertRaises(FixtureInterlock):
                check_payload(p.pulse)
            check_payload(b"\x0d" + p.limited)
            p.verify_limits(p.limited)
            with self.assertRaises(FixtureInterlock):
                check_payload(p.pulse)
            check_payload(b"\x14foc_plot_hfi_en 2")
            check_payload(p.pulse)
            for packet in (p.pulse, b"\x14measure_ind 0.9", b"\x14rotor_lock_openloop .5 .04 0"):
                with self.assertRaises(FixtureInterlock):
                    check_payload(packet)
            check_payload(b"\x14foc_plot_hfi_en 0")
        with self.assertRaises(FixtureInterlock):
            with locked_hfi_permit(motor(), .03):
                pass

    def dft_points(self, angles):
        out = []
        for i, angle in enumerate(angles):
            for graph, value in enumerate((math.radians(angle % 360), 0, 10, 1, 40)):
                out.append(dict(t=i*.004+graph*.00001, index=i, graph=graph,
                                generation=1, value=value))
        return out

    def test_dft_mean_uses_phase_graph_zero_not_mislabelled_bin2(self):
        r = analyze_dft(self.dft_points([43, 223]*50), 307.8, 2, False, 267.5)
        self.assertEqual(r["status"], "single_pose_candidate")
        self.assertAlmostEqual(r["candidate"]["minimum_inductance_axis_deg"], 43)
        self.assertAlmostEqual(r["candidate"]["offset_candidates_deg"][0], (615.6-43)%180)

    def test_dft_signed_radian_angles_are_not_discarded(self):
        pts = self.dft_points([80]*100)
        for p in pts:
            if p["graph"] == 0:
                p["value"] -= math.pi
        r = analyze_dft(pts, 307.8, 2, False, 267.5)
        self.assertEqual(r["status"], "single_pose_candidate")
        self.assertAlmostEqual(r["candidate"]["minimum_inductance_axis_deg"], 80)

    def test_dft_drifting_and_random_angles_rejected(self):
        for angles in ([i*19 for i in range(100)], [i*.25 for i in range(100)]):
            r = analyze_dft(self.dft_points(angles), 30, 2, False, 0)
            self.assertIsNone(r["candidate"])

    def test_dft_short_and_incomplete_frames_rejected(self):
        self.assertIsNone(analyze_dft(self.dft_points([43]*20), 30, 2, False, 0)["candidate"])
        pts = [p for p in self.dft_points([43]*100) if p["graph"] != 4]
        self.assertIsNone(analyze_dft(pts, 30, 2, False, 0)["candidate"])

    def test_dft_permission_freezes_pll_and_only_allows_selected_plot_mode(self):
        from vesc_workbench.wire_config import decode_config
        with locked_hfi_permit(motor(), .05, 1) as p:
            v = decode_config(p.limited, "motor")
            self.assertEqual(v["foc_pll_kp"], 0)
            self.assertEqual(v["foc_pll_ki"], 0)
            check_payload(b"\x0d"+p.limited)
            p.verify_limits(p.limited)
            with self.assertRaises(FixtureInterlock):
                check_payload(b"\x14foc_plot_hfi_en 2")
            check_payload(b"\x14foc_plot_hfi_en 1")
            check_payload(p.pulse)

    def summary_runs(self):
        runs = []
        for i, axis in enumerate((84.5, 85, 85.2)):
            runs.append(dict(dispatch_t=i, baseline_sha256="same", ok=True, plot_mode=1,
                             excitation_sent=True, zero_current_verified=True, baseline_restored=True,
                             app_unchanged=True, no_faults=True, duty=.1,
                             analysis=analyze_dft(self.dft_points([axis]*100), 307.6, 2, False, 357.5)))
        return runs

    def test_summary_preserves_ambiguity_and_does_not_apply(self):
        result = summarize_dft_runs(self.summary_runs(), 357.5)
        self.assertAlmostEqual(result["preferred_branch_deg"], 350.3, places=3)
        self.assertFalse(result["multi_pose_validated"])
        self.assertFalse(result["applied"])
        self.assertEqual(result["encoder_ratio"], 2)

    def test_summary_rejects_duplicate_or_failed_runs(self):
        runs = self.summary_runs()
        with self.assertRaises(ValueError):
            summarize_dft_runs([runs[0]]*3, 357.5)
        runs[1]["baseline_restored"] = False
        with self.assertRaises(ValueError):
            summarize_dft_runs(runs, 357.5)
