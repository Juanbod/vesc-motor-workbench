import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from vesc_workbench.queued_log import QueuedTextLog


class QueuedLogTests(unittest.TestCase):
    def test_drains_in_order_before_close_returns(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'rows.jsonl'
            with QueuedTextLog(path) as log:
                for i in range(1000):
                    log.write(f'{i}\n')
            self.assertFalse(log.thread.is_alive())
            self.assertEqual(path.read_text().splitlines(), [str(i) for i in range(1000)])
            with self.assertRaises(ValueError):
                log.write('late')

    def test_blocked_disk_does_not_block_enqueue_and_overflow_is_visible(self):
        entered, release = Event(), Event()
        class SlowStream:
            def write(self, text):
                entered.set()
                release.wait(3)
            def flush(self):
                pass
            def close(self):
                pass
        with patch('vesc_workbench.queued_log.Path.open', return_value=SlowStream()):
            log = QueuedTextLog('unused', capacity=1)
        try:
            log.write('first')
            self.assertTrue(entered.wait(1))
            log.write('second')
            with self.assertRaisesRegex(OSError, 'queue is full'):
                log.write('third')
        finally:
            release.set()
            log.close()

    def test_disk_failure_is_not_silently_accepted(self):
        class FailedStream:
            def write(self, text):
                raise OSError('disk unavailable')
            def close(self):
                pass
        with patch('vesc_workbench.queued_log.Path.open', return_value=FailedStream()):
            log = QueuedTextLog('unused')
        log.write('first')
        with self.assertRaisesRegex(OSError, 'disk unavailable'):
            log.close()
        with self.assertRaises(OSError):
            log.check()
        for capacity in (0, -1, 8193, True):
            with self.assertRaises(ValueError):
                QueuedTextLog('unused', capacity)
