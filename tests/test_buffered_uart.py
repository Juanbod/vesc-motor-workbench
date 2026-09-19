from unittest import TestCase

from vesc_workbench.uart import AvailableSerialReader, VescUartClient, VescPacketError
from vesc_workbench.uart import encode_packet, extract_packet, read_frame


class SerialBytes:
    def __init__(self, data, visible=None):
        self.data = bytearray(data)
        self.calls = []
        self.visible = visible

    @property
    def in_waiting(self):
        return len(self.data) if self.visible is None else self.visible

    def read(self, size):
        self.calls.append(size)
        result = bytes(self.data[:size])
        del self.data[:size]
        return result


class BufferedUartTests(TestCase):
    def test_short_and_long_frames_keep_crc_and_payload(self):
        for payload in (b'\x04abc', b'\x0e'+b'x'*1200):
            stream = SerialBytes(encode_packet(payload))
            reader = AvailableSerialReader(stream)
            self.assertEqual(extract_packet(read_frame(reader)), payload)
            self.assertEqual(len(stream.calls), 1)

    def test_multiple_frames_keep_boundaries_without_discarding_bytes(self):
        a, b = b'\x15hello', b'\x04world'
        stream = SerialBytes(encode_packet(a)+encode_packet(b))
        reader = AvailableSerialReader(stream)
        self.assertEqual(extract_packet(read_frame(reader)), a)
        self.assertEqual(extract_packet(read_frame(reader)), b)
        self.assertEqual(len(stream.calls), 1)

    def test_no_available_bytes_uses_normal_bounded_reads(self):
        stream = SerialBytes(encode_packet(b'\x04data'), visible=0)
        self.assertEqual(extract_packet(read_frame(AvailableSerialReader(stream))), b'\x04data')
        self.assertEqual(len(stream.calls), 3)

    def test_truncated_packet_is_not_retried_forever(self):
        stream = SerialBytes(encode_packet(b'\x04data')[:-2])
        with self.assertRaises(VescPacketError):
            read_frame(AvailableSerialReader(stream))
        self.assertLessEqual(len(stream.calls), 2)

    def test_crc_failure_remains_a_failure(self):
        data = bytearray(encode_packet(b'\x04data'))
        data[-2] ^= 1
        with self.assertRaises(VescPacketError):
            extract_packet(read_frame(AvailableSerialReader(SerialBytes(data))))

    def test_unsolicited_packet_does_not_replace_requested_response(self):
        client = VescUartClient.__new__(VescUartClient)
        client.serial = SerialBytes(encode_packet(b'\x15hello')+encode_packet(b'\x04reply'))
        client._reader = AvailableSerialReader(client.serial)
        client.response_timeout_s = .1
        self.assertEqual(client.read_response(4), b'\x04reply')

    def test_empty_read_does_not_consume_and_negative_size_refused(self):
        stream = SerialBytes(b'abc')
        reader = AvailableSerialReader(stream)
        self.assertEqual(reader.read(0), b'')
        self.assertEqual(stream.calls, [])
        with self.assertRaises(ValueError):
            reader.read(-1)
