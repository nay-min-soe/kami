"""Run blocking calls (LLM requests) off the UI thread."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from kami.llm import LLMError

log = logging.getLogger(__name__)


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


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
        except Exception as exc:  # surface every error to the UI
            # LLMErrors are expected and already logged; anything else keeps its
            # traceback in the log file, never in the panel.
            log.warning("task %s failed: %s", name, type(exc).__name__,
                        exc_info=not isinstance(exc, LLMError))
            self.signals.failed.emit(str(exc))
        else:
            self.signals.done.emit(result)


_active: set[_Task] = set()


def run_in_background(fn, *args, on_done=None, on_error=None, **kwargs) -> None:
    task = _Task(fn, args, kwargs)
    task.setAutoDelete(False)
    _active.add(task)

    def finish(callback, value):
        _active.discard(task)
        if callback:
            callback(value)

    task.signals.done.connect(lambda v: finish(on_done, v))
    task.signals.failed.connect(lambda e: finish(on_error, e))
    QThreadPool.globalInstance().start(task)
