from unittest import TestCase
from struct import pack

from vesc_workbench.lisp_capability import read_lisp_capability, probe_empty_lisp_arithmetic, read_native_snapshot
from vesc_workbench.uart import VescPacketError


class LispCapabilityTests(TestCase):
    def client(self, replies):
        class Client:
            sent = []
            def send_payload(self, payload):
                self.sent.append(payload)
            def read_response(self, command):
                if command not in replies:
                    raise VescPacketError('No reply')
                return replies[command]
        return Client()

    def test_only_two_read_queries_no_start_erase_write_or_repl(self):
        client = self.client({130: bytes((130,))+pack('>ii', 1234, 0), 134: bytes((134,))+bytes(9)})
        result = read_lisp_capability(client)
        self.assertEqual(client.sent, [bytes((130,))+bytes(8), bytes((134,))])
        self.assertEqual(result['stored_code_bytes'], 1234)
        self.assertTrue(result['runtime_response'])
        self.assertFalse(result['runtime_started'])
        self.assertFalse(result['code_writes'])
        self.assertFalse(result['excitation_sent'])

    def test_missing_reply_is_not_claimed_as_definite_absence(self):
        result = read_lisp_capability(self.client({130: bytes((130,))+bytes(8)}))
        self.assertEqual(result['stored_code_bytes'], 0)
        self.assertFalse(result['runtime_response'])
        self.assertIn('inconclusive', result['interpretation'])

    def test_bad_storage_header_does_not_become_zero_length(self):
        for payload in (b'bad', bytes((130,))+pack('>ii', -1, 0), bytes((130,))+pack('>ii', 0, 3)):
            result = read_lisp_capability(self.client({130: payload}))
            self.assertIsNone(result['stored_code_bytes'])
            self.assertTrue(result['errors'])

    def test_arithmetic_probe_is_literal_and_never_writes_flash(self):
        client = self.client({135: bytes((135,))+b'> 3\n'})
        result = probe_empty_lisp_arithmetic(client, dict(stored_code_bytes=0, runtime_response=False))
        self.assertEqual(client.sent, [bytes((138,))+b'(+ 1 2)\0'])
        self.assertTrue(result['arithmetic_verified'])
        self.assertFalse(result['flash_writes'])
        for capability in ({}, dict(stored_code_bytes=1, runtime_response=False),
                           dict(stored_code_bytes=0, runtime_response=True)):
            with self.assertRaises(ValueError):
                probe_empty_lisp_arithmetic(client, capability)
        self.assertEqual(len(client.sent), 1)

    def test_snapshot_is_fixed_read_only_expression(self):
        client = self.client({135: bytes((135,))+b'> (100 40.5 100 0 0 0 24.4)'})
        result = read_native_snapshot(client)
        self.assertEqual(len(client.sent), 1)
        self.assertEqual(client.sent[0], bytes((138,))+result['expression'].encode()+b'\0')
        self.assertNotIn('set-', result['expression'])
        self.assertFalse(result['excitation_sent'])
