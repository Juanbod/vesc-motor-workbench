import unittest
from unittest.mock import patch
from test_locked_probe import app, quiet_samples
from vesc_workbench.fixture import (
    FixtureInterlock, locked_isolation_permit, check_payload)
from vesc_workbench.wire_config import patch_config, decode_config


class IsolationTests(unittest.TestCase):
    def rows(self):
        return [dict(r, id_a=0, iq_a=0) for r in quiet_samples()]

    @patch('vesc_workbench.fixture.require_locked')
    def test_exact_single_ram_write(self, _):
        original = patch_config(app(), 'app', dict(app_to_use=5, timeout_msec=1000))
        with locked_isolation_permit(original, self.rows()) as p:
            self.assertEqual(decode_config(p.isolated, 'app')['app_to_use'], 0)
            self.assertFalse(p.accept(b'\x10' + p.isolated))
            self.assertFalse(p.accept(b'\x95' + original))
            self.assertFalse(p.accept(b'\x06\x00\x00\x03\xe8'))
            check_payload(b'\x95' + p.isolated)
            self.assertFalse(p.accept(b'\x95' + p.isolated))
            with self.assertRaises(FixtureInterlock):
                with locked_isolation_permit(original, self.rows()):
                    pass

    @patch('vesc_workbench.fixture.require_locked')
    def test_not_quiet_rejected(self, _):
        rows = self.rows()
        rows[-1]['current_motor_a'] = 1
        with self.assertRaises(FixtureInterlock):
            with locked_isolation_permit(app(), rows):
                pass
