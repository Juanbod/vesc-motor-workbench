from dataclasses import dataclass
from unittest import TestCase
from unittest.mock import patch

from vesc_workbench.telemetry_capture import capture_values


@dataclass
class Values:
    current_motor_a: float = 0


class CaptureTests(TestCase):
    def test_formatting_delay_is_not_capture_latency_but_remains_visible(self):
        clock = [10.0]
        class Client:
            pid_position = 32
            def get_values(self):
                clock[0] += .002
                return Values()
        def slow_format(values):
            clock[0] += .1
            return {'current_motor_a': values.current_motor_a}
        with patch('vesc_workbench.telemetry_capture.asdict', side_effect=slow_format):
            row = capture_values(Client(), lambda: clock[0])
        self.assertAlmostEqual(row['latency_s'], .002)
        self.assertAlmostEqual(row['t'], 10.002)
        self.assertAlmostEqual(row['formatting_s'], .1)
        self.assertAlmostEqual(clock[0]-row['t'], .1)
        self.assertEqual(row['position_deg'], 32)

    def test_full_device_wait_cannot_be_removed(self):
        clock = [0]
        class Client:
            pid_position = 0
            def get_values(self):
                clock[0] += .25
                return Values()
        row = capture_values(Client(), lambda: clock[0])
        self.assertEqual(row['latency_s'], .25)
        self.assertEqual(row['t'], .25)

    def test_read_failure_propagates_without_a_sample(self):
        class Client:
            def get_values(self):
                raise OSError('Lost response')
        with self.assertRaisesRegex(OSError, 'Lost response'):
            capture_values(Client())

    def test_native_metadata_cannot_override_host_timestamp(self):
        class Client:
            pid_position = 0
            native_counter_record = {'t': 99}
            def get_values(self):
                return Values()
        with self.assertRaises(ValueError):
            capture_values(Client())
