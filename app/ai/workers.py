"""Background threads so the UI never freezes."""
from typing import Callable, Iterator

from PySide6.QtCore import QThread, Signal

from app.ai.ollama_client import OllamaError

_alive: set = set()  # keeps running workers from being garbage collected


class TaskContext:
    def __init__(self, worker: "TaskWorker"):
        self._w = worker

    def report(self, value) -> None:
        self._w.progress.emit(value)

    @property
    def cancelled(self) -> bool:
        return self._w.isInterruptionRequested()


class TaskWorker(QThread):
    """Runs fn(ctx) off the UI thread and emits its return value."""
    result = Signal(object)
    failed = Signal(str)
    progress = Signal(object)

    def __init__(self, fn: Callable[[TaskContext], object], parent=None):
        super().__init__()  # no parent: a running thread must outlive the widget that started it
        self._fn = fn
        _alive.add(self)
        self.finished.connect(lambda: _alive.discard(self))

    def run(self) -> None:
        try:
            self.result.emit(self._fn(TaskContext(self)))
        except OllamaError as e:
            self.failed.emit(str(e))
        except Exception as e:  # surface anything else instead of dying silently
            self.failed.emit(f"{type(e).__name__}: {e}")

    def cancel(self) -> None:
        self.requestInterruption()


class StreamWorker(QThread):
    """Consumes a text generator, emitting each piece as it arrives."""
    chunk = Signal(str)
    done = Signal(str)       # full text (also emitted after Stop, with what arrived so far)
    failed = Signal(str)

    def __init__(self, make_stream: Callable[[], Iterator[str]], parent=None):
        super().__init__()
        self._make = make_stream
        _alive.add(self)
        self.finished.connect(lambda: _alive.discard(self))

    def run(self) -> None:
        parts: list[str] = []
        gen = None
        try:
            gen = self._make()
            for piece in gen:
                if self.isInterruptionRequested():
                    break
                parts.append(piece)
                self.chunk.emit(piece)
        except OllamaError as e:
            self.failed.emit(str(e))
            return
        except Exception as e:
            self.failed.emit(f"{type(e).__name__}: {e}")
            return
        finally:
            if gen is not None and hasattr(gen, "close"):
                gen.close()
        self.done.emit("".join(parts))

    def cancel(self) -> None:
        self.requestInterruption()


def finish_all_workers(timeout_ms: int = 5000) -> None:
    """Ask running workers to stop and wait for them (call before the app exits)."""
    for w in list(_alive):
        w.requestInterruption()
    for w in list(_alive):
        w.wait(timeout_ms)
