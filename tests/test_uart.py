from unittest import TestCase
from struct import pack_into

from vesc_workbench.uart import (
    crc16,
    encode_packet,
    extract_packet,
    parse_fw_version_payload,
    set_current_payload,
    parse_values_payload,
    parse_pid_position_payload,
    VescPacketError,
)


class UartPacketTests(TestCase):
    def test_values_preserve_signed_sector_counters_and_position(self):
        payload = bytearray(58)
        payload[0] = 4
        pack_into('>i', payload, 45, -2147483648)
        pack_into('>i', payload, 49, 2147483647)
        payload[53] = 3
        pack_into('>i', payload, 54, 123456789)
        parsed = parse_values_payload(bytes(payload))
        self.assertEqual(parsed.tachometer, -2147483648)
        self.assertEqual(parsed.tachometer_abs, 2147483647)
        self.assertEqual(parsed.fault_code, 3)
        self.assertAlmostEqual(parse_pid_position_payload(bytes(payload)), 123.456789)

    def test_values_reject_every_truncated_base_packet(self):
        for size in range(1, 54):
            with self.subTest(size=size), self.assertRaises(VescPacketError):
                parse_values_payload(bytes([4]) + bytes(size - 1))

    def test_crc16_xmodem_reference_vector(self) -> None:
        self.assertEqual(crc16(b"123456789"), 0x31C3)

    def test_packet_round_trip(self) -> None:
        payload = set_current_payload(1.5)
        self.assertEqual(extract_packet(encode_packet(payload)), payload)

    def test_parse_fw_version(self) -> None:
        version = parse_fw_version_payload(bytes((0, 7, 0)) + b"mkseesc\x00")
        self.assertEqual(version.major, 7)
        self.assertEqual(version.minor, 0)
        self.assertEqual(version.hardware, "mkseesc")
