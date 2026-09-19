from unittest import TestCase
from unittest.mock import patch

from vesc_workbench.native_counter_snapshot import prepared_expression, checked_repl_ack
from vesc_workbench.native_probe_client import NativeProbeClient


class PreparedSnapshotTests(TestCase):
    def test_bounded_readonly_lambda_and_private_cleanup(self):
        expression = prepared_expression('wbcs123456789abc')
        self.assertLess(len(expression), 512)
        self.assertIn(b'(lambda (n)', expression)
        self.assertIn(b'(bufset-u32 b 4 n)', expression)
        for forbidden in (b'set-current', b'set-duty', b'set-rpm', b'spawn', b'loop', b'flash'):
            self.assertNotIn(forbidden, expression)
        self.assertEqual(prepared_expression('wbcs123456789abc', remove=True),
                         b"(progn (undefine 'wbcs123456789abc) 6819)")
        for name in ('user-function', 'wbcs123456789abc) (set-current 8)', ''):
            with self.assertRaises(ValueError):
                prepared_expression(name)

    def test_ack_is_exact_and_bounded(self):
        class Client:
            def send_payload(self, payload):
                self.payload = payload
            def read_response(self, command):
                return bytes((135,))+self.line
        client = Client()
        client.line = b'> 6818'
        checked_repl_ack(client, b'(+ 1 2)', 6818)
        self.assertEqual(client.payload, b'\x8a(+ 1 2)\0')
        for line in (b'> nil', b'error'):
            client.line = line
            with self.assertRaises(ValueError):
                checked_repl_ack(client, b'(+ 1 2)', 6818)

    def test_serial_closed_even_when_ram_cleanup_fails(self):
        client = NativeProbeClient.__new__(NativeProbeClient)
        client.snapshot_setup_attempted = True
        client.snapshot_name = 'wbcs123456789abc'
        client.native_snapshot_runtime = dict(removed=False)
        with patch('vesc_workbench.native_probe_client.checked_repl_ack', side_effect=ValueError('cleanup')), \
             patch('vesc_workbench.locked_probe.ProbeClient.close') as close:
            with self.assertRaises(ValueError):
                client.close()
            close.assert_called_once()
        self.assertFalse(client.native_snapshot_runtime['removed'])

    def test_delayed_snapshot_result_is_not_a_cleanup_ack(self):
        from unittest.mock import Mock
        client = Mock()
        client.read_response.side_effect = [b'\x87> t', b'\x87> 6819']
        checked_repl_ack(client, b"(undefine 'wbcs123456789abc)", 6819)
        self.assertEqual(client.read_response.call_count, 2)
        client.read_response.side_effect = None
        client.read_response.return_value = b'\x87> t'
        with self.assertRaises(ValueError):
            checked_repl_ack(client, b"(undefine 'wbcs123456789abc)", 6819)
