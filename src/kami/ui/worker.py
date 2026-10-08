"""Run blocking calls (LLM requests) off the UI thread."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from kami.llm import LLMError

log = logging.getLogger(__name__)


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(str)   # emitted on the worker thread, delivered on the UI thread
    cancelled = Signal()


class _Task(QRunnable):
    def __init__(self, fn, args, kwargs) -> None:
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _Signals()

    def run(self) -> None:
        name = getattr(self.fn, "__qualname__", repr(self.fn))
        log.info("task %s started", name)
        try:
            result = self.fn(*self.args, **self.kwargs)
        except LLMError as exc:
            if exc.kind == "cancelled":
                log.info("task %s cancelled", name)
                self.signals.cancelled.emit()
            else:
                log.warning("task %s failed: %s", name, type(exc).__name__)
                self.signals.failed.emit(str(exc))
        except Exception as exc:  # surface every error to the UI
            # The traceback goes to the log file, never to the panel.
            log.warning("task %s failed: %s", name, type(exc).__name__, exc_info=True)
            self.signals.failed.emit(str(exc))
        else:
            self.signals.done.emit(result)


_active: set[_Task] = set()


def run_in_background(fn, *args, on_done=None, on_error=None, on_progress=None,
                      **kwargs) -> None:
    """Run fn(*args, **kwargs) on a pool thread. With on_progress, fn also gets
    on_delta=<emit>, so pieces of a streamed reply reach the UI thread as they arrive."""
    task = _Task(fn, args, kwargs)
    if on_progress:
        task.kwargs["on_delta"] = task.signals.progress.emit
        task.signals.progress.connect(on_progress)
    task.setAutoDelete(False)
    _active.add(task)

    def finish(callback, *value):
        _active.discard(task)
        if callback:
            callback(*value)

    task.signals.done.connect(lambda v: finish(on_done, v))
    task.signals.failed.connect(lambda e: finish(on_error, e))
    task.signals.cancelled.connect(lambda: finish(None))   # the panel already moved on
    QThreadPool.globalInstance().start(task)
