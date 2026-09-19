import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from vesc_workbench.queued_log import MemoryTextLog, open_trial_log, check_trial_log


class MemoryLogTests(TestCase):
    def test_no_disk_writes_before_close_and_order_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'samples.jsonl'
            with open_trial_log(path, memory=True) as log:
                for i in range(1000):
                    log.write(f'{i}\n')
                    check_trial_log(log)
                self.assertEqual(path.read_bytes(), b'')
            self.assertEqual(path.read_text().splitlines(), [str(i) for i in range(1000)])
            self.assertEqual(log.records, [])
            log.close()
            with self.assertRaises(ValueError):
                log.write('late')

    def test_overflow_latches_failure_but_retained_records_are_drained(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'samples.jsonl'
            log = MemoryTextLog(path, capacity=4)
            log.write('one\n')
            with self.assertRaisesRegex(OSError, 'capacity'):
                log.write('two\n')
            with self.assertRaises(OSError):
                log.close()
            self.assertEqual(path.read_text(), 'one\n')
            with self.assertRaises(OSError):
                log.check()
            log.close()

    def test_drain_failure_is_visible_and_stream_is_closed(self):
        stream = Mock()
        stream.writelines.side_effect = OSError('Disk failed')
        with patch('vesc_workbench.queued_log.Path.open', return_value=stream):
            log = MemoryTextLog('unused')
            log.write('one\n')
            stream.writelines.assert_not_called()
            with self.assertRaisesRegex(OSError, 'Disk failed'):
                log.close()
            stream.close.assert_called_once()
            with self.assertRaises(OSError):
                log.check()

    def test_backend_capacity_and_records_are_bounded(self):
        with self.assertRaises(ValueError):
            open_trial_log('unused', True, memory=True)
        for capacity in (0, -1, True, 64*1024*1024+1):
            with self.assertRaises(ValueError):
                MemoryTextLog('unused', capacity)
        with patch('vesc_workbench.queued_log.Path.open', return_value=Mock()):
            with MemoryTextLog('unused') as log:
                for text in ('', 'x'*8193, '\u0400'):
                    with self.assertRaises(ValueError):
                        log.write(text)
