import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from vesc_workbench.fixture import FixtureInterlock, check_payload
from vesc_workbench.uart import VescUartClient, encode_packet


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fixture.json"
        self.patcher = patch("vesc_workbench.fixture.FIXTURE_PATH", self.path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def state(self, rotor, confirmed=True):
        self.path.write_text(json.dumps({"schema": "vesc-fixture-v1", "rotor": rotor,
                                         "confirmed_by_user": confirmed}), encoding="utf-8")

    def test_missing_or_corrupt_state_fails_closed(self):
        for content in (None, "garbage", "null", "[]", "{}"):
            if content is not None:
                self.path.write_text(content, encoding="utf-8")
            with self.assertRaises(FixtureInterlock):
                check_payload(b"\x06\x00\x00\x03\xe8")

    def test_stop_and_read_only_work_without_state(self):
        for packet in (b"\x06\x00\x00\x00\x00", b"\x00", b"\x04", b"\x0e", b"\x11", b"\x14encoder"):
            check_payload(packet)

    def test_locked_blocks_drive_flash_terminal_and_mode_change(self):
        self.state("locked")
        for packet in (b"\x06\x00\x00\x03\xe8", b"\x08\x00\x00\x00\x00",
                       b"\x05\x00\x00\x00\x00", b"\x07\x00\x00\x00\x00",
                       b"\x0b\x03", b"\x0ddata", b"\x10data", b"\x95data",
                       b"\x14foc_openloop 1 60", b"\x14encoder; foc_openloop 1 60", b"\x1e"):
            with self.subTest(packet=packet), self.assertRaises(FixtureInterlock):
                check_payload(packet)

    def test_only_explicit_free_confirmation_allows_regular_runner(self):
        for rotor, confirmed in (("unknown", True), ("free", False), ("free", 1)):
            self.state(rotor, confirmed)
            with self.assertRaises(FixtureInterlock):
                check_payload(b"\x08\x00\x00\x01\x00")
        self.state("free")
        check_payload(b"\x08\x00\x00\x01\x00")

    def test_uart_blocks_before_serial_write_but_allows_stop(self):
        self.state("locked")
        client = VescUartClient.__new__(VescUartClient)
        client.serial = io.BytesIO()
        with self.assertRaises(FixtureInterlock):
            client.set_current(1)
        with self.assertRaises(FixtureInterlock):
            client.set_rpm(0)
        self.assertEqual(client.serial.getvalue(), b"")
        client.set_current(0)
        self.assertEqual(client.serial.getvalue(), encode_packet(b"\x06\x00\x00\x00\x00"))

    def test_state_rechecked_for_each_command(self):
        self.state("free")
        check_payload(b"\x08\x00\x00\x01\x00")
        self.state("locked")
        with self.assertRaises(FixtureInterlock):
            check_payload(b"\x08\x00\x00\x01\x00")
