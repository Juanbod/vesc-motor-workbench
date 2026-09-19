import unittest
import sys
from unittest.mock import patch

from vesc_workbench.host_scheduling import above_normal_priority, defer_cyclic_gc


class HostSchedulingTests(unittest.TestCase):
    def test_cyclic_collection_state_restored_after_trial_failure(self):
        for original in (False, True):
            state = [original]
            with patch('vesc_workbench.host_scheduling.gc.isenabled', side_effect=lambda: state[0]), \
                 patch('vesc_workbench.host_scheduling.gc.enable', side_effect=lambda: state.__setitem__(0, True)), \
                 patch('vesc_workbench.host_scheduling.gc.disable', side_effect=lambda: state.__setitem__(0, False)):
                with self.assertRaises(ValueError):
                    with defer_cyclic_gc(True) as evidence:
                        self.assertFalse(state[0])
                        self.assertTrue(evidence['reference_counting_unchanged'])
                        raise ValueError('Injected failure')
                self.assertEqual(state[0], original)

    def test_gc_deferral_is_opt_in(self):
        with patch('vesc_workbench.host_scheduling.gc.disable') as disable:
            with defer_cyclic_gc() as evidence:
                self.assertFalse(evidence['deferred'])
            disable.assert_not_called()

    def test_disabled_does_not_touch_os(self):
        with patch('vesc_workbench.host_scheduling._windows_api') as api, \
             patch('vesc_workbench.host_scheduling.sys.setswitchinterval') as switch:
            with above_normal_priority() as evidence:
                self.assertFalse(evidence['applied'])
            api.assert_not_called()
            switch.assert_not_called()

    def test_only_current_process_above_normal_and_restore_on_error(self):
        for fail in (False, True):
            state, writes = [0x20], []
            previous_switch = sys.getswitchinterval()
            def set_priority(value):
                state[0] = value
                writes.append(value)
            with patch('vesc_workbench.host_scheduling._windows_api',
                       return_value=(lambda: state[0], set_priority)):
                try:
                    with above_normal_priority(True) as evidence:
                        self.assertEqual(state[0], 0x8000)
                        self.assertFalse(evidence['hard_realtime'])
                        self.assertAlmostEqual(sys.getswitchinterval(), .001)
                        self.assertEqual(evidence['thread_switch_interval_s'], .001)
                        if fail:
                            raise ValueError('Injected trial failure')
                except ValueError:
                    self.assertTrue(fail)
            self.assertEqual(state[0], 0x20)
            self.assertEqual(writes, [0x8000, 0x20])
            self.assertEqual(sys.getswitchinterval(), previous_switch)

    def test_high_realtime_or_unknown_priority_refused(self):
        for initial in (0x80, 0x100, 0):
            with patch('vesc_workbench.host_scheduling._windows_api',
                       return_value=(lambda: initial, lambda _: self.fail('Unexpected priority write'))):
                with self.assertRaises(RuntimeError):
                    with above_normal_priority(True):
                        self.fail('Unexpected entry')

    def test_readback_failure_still_attempts_restore(self):
        writes = []
        with patch('vesc_workbench.host_scheduling._windows_api',
                   return_value=(lambda: 0x20, writes.append)):
            with self.assertRaisesRegex(RuntimeError, 'readback'):
                with above_normal_priority(True):
                    self.fail('Unexpected entry')
        self.assertEqual(writes, [0x8000, 0x20])
