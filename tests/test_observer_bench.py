from collections import deque
import io
import math
import struct
from unittest import TestCase
from unittest.mock import Mock, patch

from vesc_workbench.bench import BenchPlan, BenchStop, SimulatedBench, guard
from vesc_workbench.observer_bench import ObserverBench, summarize_observer_error
from vesc_workbench.uart import VescUartClient, VescPacketError, encode_packet, parse_pid_position_payload


class ObserverBenchTests(TestCase):
    def test_scaled_pid_position_rejected_before_prepare(self):
        b = ObserverBench.__new__(ObserverBench)
        b.values = {'foc_encoder_ratio': 2, 'p_pid_ang_div': 2}
        with patch('vesc_workbench.bench.HardwareBench.prepare') as prepare:
            with self.assertRaises(BenchStop):
                b.prepare(BenchPlan())
            prepare.assert_not_called()

    def test_recovery_uses_raw_stream_before_base_standstill_check(self):
        b = ObserverBench.__new__(ObserverBench)
        b.observer_enabled, b.modified, b.isolated = True, True, True
        b.values = {'foc_encoder_ratio': 2, 'foc_encoder_inverted': 0}
        b.client = Mock()
        clock = [0.0]
        def verify_raw():
            self.assertFalse(b.observer_enabled)
            b.client.stream_encoder.assert_called_once_with(True)
            self.assertTrue(all(call.args == (0,) for call in b.client.set_current.call_args_list))
            return {'motor_restored': True}
        with patch('vesc_workbench.observer_bench.monotonic', side_effect=lambda: clock[0]), \
             patch('vesc_workbench.observer_bench.sleep', side_effect=lambda dt: clock.__setitem__(0, clock[0]+dt)), \
             patch('vesc_workbench.bench.HardwareBench.close', side_effect=verify_raw):
            self.assertTrue(b.close()['motor_restored'])

    def test_failed_raw_stream_switch_blocks_restore(self):
        b = ObserverBench.__new__(ObserverBench)
        b.observer_enabled, b.modified, b.isolated = True, True, True
        b.client = Mock()
        b.client.stream_encoder.side_effect = OSError('Disconnected')
        with patch('vesc_workbench.bench.HardwareBench.close') as restore:
            result = b.close()
            self.assertFalse(result['motor_restored'])
            restore.assert_not_called()
            b.client.close.assert_called_once()

    def test_position_extension_and_missing_extension(self):
        prefix = bytes((4,)) + bytes(53)
        self.assertIsNone(parse_pid_position_payload(prefix))
        self.assertEqual(parse_pid_position_payload(prefix + struct.pack('>i', 123456789)), 123.456789)
        with self.assertRaises(VescPacketError):
            parse_pid_position_payload(b'\x16' + bytes(60))

    def test_error_packet_never_changes_raw_encoder(self):
        c = VescUartClient.__new__(VescUartClient)
        c.serial = io.BytesIO(encode_packet(b'\x16' + struct.pack('>i', -17500000)))
        c.position_mode, c.rotor_angle, c.rotor_samples = 6, 123, deque()
        c.read_payload()
        self.assertEqual(c.observer_error, -175)
        self.assertEqual(c.rotor_angle, 123)
        self.assertFalse(c.rotor_samples)

    def test_unavailable_stale_and_invalid_error_stop(self):
        b = SimulatedBench()
        b.prepare(BenchPlan())
        v = {**b.sample(), 'observer_error_deg': 5, 'observer_error_age': 0}
        guard(v, BenchPlan())
        for changed in ({'observer_error_deg': math.nan},
                        {'observer_error_deg': 181}, {'observer_error_age': .11}):
            with self.assertRaises(BenchStop):
                guard({**v, **changed}, BenchPlan())

    def samples(self, errors):
        return [dict(t=i*.025, observer_error_deg=e, encoder_erpm=300)
                for i,e in enumerate(errors)]

    def test_small_constant_error_passes_screen_not_sensorless(self):
        r = summarize_observer_error(self.samples([5]*201))
        self.assertAlmostEqual(r['mean_error_deg'], 5)
        self.assertTrue(r['passes_angle_screen'])
        self.assertFalse(r['sensorless_validated'])

    def test_wraparound_mean_is_not_zero(self):
        r = summarize_observer_error(self.samples([179,-179]*101))
        self.assertGreater(abs(r['mean_error_deg']), 178)
        self.assertLess(r['p95_residual_deg'], 3)
        self.assertFalse(r['passes_angle_screen'])

    def test_rotating_error_fails_screen(self):
        r = summarize_observer_error(self.samples([i*19 % 360 - 180 for i in range(201)]))
        self.assertFalse(r['passes_angle_screen'])
        self.assertLess(r['resultant'], .2)
        self.assertIsNone(r['mean_error_deg'])

    def test_short_series_never_qualifies(self):
        r = summarize_observer_error(self.samples([0]*20))
        self.assertFalse(r['passes_angle_screen'])
