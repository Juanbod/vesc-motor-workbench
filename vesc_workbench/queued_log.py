"""Bounded disk writer; enqueue never waits for disk and failures stay visible."""
from pathlib import Path
from queue import Queue, Empty, Full
from threading import Event, Thread


class QueuedTextLog:
    def __init__(self, path, capacity=8192):
        if type(capacity) is not int or not 1 <= capacity <= 8192:
            raise ValueError('Invalid bounded log capacity')
        self.stream = Path(path).open('x', encoding='utf-8')
        self.queue = Queue(maxsize=capacity)
        self.done = Event()
        self.error = None
        self.closed = False
        self.thread = Thread(target=self._write_loop, daemon=True, name='trial-log')
        self.thread.start()

    def _write_loop(self):
        try:
            while not self.done.is_set() or not self.queue.empty():
                try:
                    text = self.queue.get(timeout=.01)
                except Empty:
                    continue
                self.stream.write(text)
                if self.queue.empty():
                    self.stream.flush()
            self.stream.flush()
        except Exception as exc:
            self.error = exc
        finally:
            try:
                self.stream.close()
            except Exception as exc:
                self.error = exc

    def check(self):
        if self.error is not None:
            raise OSError(f'Trial log writer failed: {self.error}') from self.error

    def write(self, text):
        self.check()
        if self.closed or len(text) > 8192:
            raise ValueError('Closed trial log or oversized record')
        try:
            self.queue.put_nowait(text)
        except Full as exc:
            raise OSError('Trial log queue is full') from exc

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.done.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise OSError('Trial log did not drain after zero-current recovery')
        self.check()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class MemoryTextLog:
    """Bounded ASCII records, drained only after the caller's zero-current recovery."""
    def __init__(self, path, capacity=64*1024*1024):
        if type(capacity) is not int or not 1 <= capacity <= 64*1024*1024:
            raise ValueError('Invalid memory log capacity')
        self.stream = Path(path).open('x', encoding='utf-8')
        self.capacity = capacity
        self.size = 0
        self.records = []
        self.error = None
        self.closed = False

    def check(self):
        if self.error is not None:
            raise OSError(f'Memory log failed: {self.error}') from self.error

    def write(self, text):
        self.check()
        if self.closed or not text or len(text) > 8192 or not text.isascii():
            raise ValueError('Closed memory log or invalid record')
        if self.size+len(text) > self.capacity or len(self.records) >= 131072:
            self.error = OSError('Memory log capacity exceeded')
            self.check()
        self.records.append(text)
        self.size += len(text)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.stream.writelines(self.records)
            self.stream.flush()
        except Exception as exc:
            self.error = exc
        finally:
            try:
                self.stream.close()
            except Exception as exc:
                self.error = exc
            self.records.clear()
        self.check()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def open_trial_log(path, queued=False, *, memory=False):
    if memory and queued:
        raise ValueError('Choose one buffered log backend')
    if memory:
        return MemoryTextLog(path)
    return QueuedTextLog(path) if queued else Path(path).open('x', encoding='utf-8')


def check_trial_log(stream):
    if isinstance(stream, (QueuedTextLog, MemoryTextLog)):
        stream.check()
    else:
        stream.flush()
