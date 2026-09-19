from struct import pack
from unittest import TestCase

from vesc_workbench.native_encoder_burst import burst_expression, decode_burst, read_native_burst


class NativeBurstTests(TestCase):
    def payload(self, *, nonce=17, start=1000, gap=10, width=0, angle=lambda i: 40+i*36):
        return (bytes((36,))+pack('>II', 6816, nonce)+b''.join(
            pack('>IfI', (start+i*gap) & 0xffffffff, angle(i) % 360,
                 (start+i*gap+width) & 0xffffffff) for i in range(16)))

    def test_fixed_bounded_read_expression_has_no_actuator_calls(self):
        expression = burst_expression(17)
        self.assertLess(len(expression), 500)
        self.assertIn(b'looprange i 0 16', expression)
        for forbidden in (b'set-current', b'set-rpm', b'set-duty', b'conf-set', b'eeprom', b'spawn'):
            self.assertNotIn(forbidden, expression)
        for nonce in (0, -1, True, 0x1000000):
            with self.assertRaises(ValueError):
                burst_expression(nonce)

    def test_native_timing_and_angle_wrap_reconstruct_6000rpm(self):
        rows = decode_burst(self.payload(), 17)
        self.assertAlmostEqual(rows[-1]['travel_deg'], 540)
        self.assertAlmostEqual(rows[-1]['travel_deg']/rows[-1]['elapsed_s']/6, 6000)
        self.assertEqual(rows[0]['bracket_upper_s'], .0001)

    def test_system_tick_wrap_is_supported(self):
        rows = decode_burst(self.payload(start=0xfffffff0), 17)
        self.assertAlmostEqual(rows[-1]['elapsed_s'], .015)

    def test_invalid_nonce_nan_delay_and_overspeed_fail(self):
        for payload in (self.payload(nonce=18), self.payload()[:-1],
                        self.payload(gap=50), self.payload(width=101),
                        self.payload(angle=lambda i: float('nan')),
                        self.payload(angle=lambda i: i*70)):
            with self.assertRaises(ValueError):
                decode_burst(payload, 17)

    def test_failed_decode_preserves_raw_evidence(self):
        payload = self.payload(gap=50)
        class Client:
            def send_payload(self, _):
                pass
            def read_response(self, _):
                return payload
        result = read_native_burst(Client(), 17)
        self.assertFalse(result['capture_verified'])
        self.assertEqual(result['raw_payload_hex'], payload.hex())
        self.assertTrue(result['errors'])
