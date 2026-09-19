"""Optional process-local scheduling preference, never a real-time guarantee."""
from contextlib import contextmanager
import ctypes
import gc
import sys

TRIAL_THREAD_SWITCH_S = .001


def _windows_api():
    if sys.platform != 'win32':
        raise RuntimeError('Above-normal process scheduling requires Windows')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.GetPriorityClass.argtypes = [ctypes.c_void_p]
    kernel.GetPriorityClass.restype = ctypes.c_uint32
    kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.SetPriorityClass.restype = ctypes.c_int
    process = kernel.GetCurrentProcess()

    def get():
        value = kernel.GetPriorityClass(process)
        if not value:
            raise ctypes.WinError(ctypes.get_last_error())
        return value

    def set_priority(value):
        if not kernel.SetPriorityClass(process, value):
            raise ctypes.WinError(ctypes.get_last_error())

    return get, set_priority


@contextmanager
def above_normal_priority(enabled=False):
    if not enabled:
        yield dict(applied=False, hard_realtime=False)
        return
    get, set_priority = _windows_api()
    previous = get()
    if previous not in (0x20, 0x40, 0x4000, 0x8000):
        raise RuntimeError('Unexpected initial process priority; do not run this trial')
    previous_switch = sys.getswitchinterval()
    try:
        set_priority(0x8000)
        if get() != 0x8000:
            raise RuntimeError('Process priority readback mismatch')
        # Avoid the logging thread holding the GIL for the default 5 ms slice.
        sys.setswitchinterval(TRIAL_THREAD_SWITCH_S)
        if abs(sys.getswitchinterval()-TRIAL_THREAD_SWITCH_S) > 1e-9:
            raise RuntimeError('Thread switch interval readback mismatch')
        yield dict(applied=True, previous_priority_class=previous,
                   priority_class=0x8000, scope='current_process_only', hard_realtime=False,
                   thread_switch_interval_s=TRIAL_THREAD_SWITCH_S,
                   previous_thread_switch_interval_s=previous_switch)
    finally:
        try:
            sys.setswitchinterval(previous_switch)
        finally:
            set_priority(previous)
            if get() != previous:
                raise RuntimeError('Could not restore process scheduling priority')


@contextmanager
def defer_cyclic_gc(enabled=False):
    """Use only around bounded trials; reference-count reclamation remains active."""
    previous = gc.isenabled()
    if not enabled:
        yield dict(deferred=False)
        return
    gc.disable()
    try:
        yield dict(deferred=True, previous_enabled=previous,
                   scope='bounded_trial_process', reference_counting_unchanged=True)
    finally:
        if previous:
            gc.enable()
        else:
            gc.disable()
