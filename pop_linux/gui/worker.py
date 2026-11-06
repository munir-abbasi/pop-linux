"""A single cancellable asyncio operation owned by a Qt thread."""
import asyncio
import threading

from PySide6.QtCore import QThread, Signal

from pop_linux.execution import execute_request_async, redact_secrets
from pop_linux.execution_models import SearchRequest


class SearchWorker(QThread):
    completed = Signal(int, object)
    failed = Signal(int, str)
    cancelled = Signal(int)

    def __init__(self, request: SearchRequest, generation: int, parent=None):
        super().__init__(parent)
        self.request = request
        self.generation = generation
        self._lock = threading.Lock()
        self._cancel_requested = False
        self._loop = None
        self._task = None

    def cancel(self):
        with self._lock:
            self._cancel_requested = True
            if self._loop is not None and self._task is not None:
                self._loop.call_soon_threadsafe(self._task.cancel)

    async def _execute(self):
        with self._lock:
            self._loop = asyncio.get_running_loop()
            self._task = asyncio.current_task()
            cancel = self._cancel_requested
        try:
            if cancel:
                raise asyncio.CancelledError
            return await execute_request_async(self.request)
        finally:
            with self._lock:
                self._loop = self._task = None

    def run(self):
        try:
            envelope = asyncio.run(self._execute())
            with self._lock:
                cancelled = self._cancel_requested
            if cancelled:
                self.cancelled.emit(self.generation)
            else:
                self.completed.emit(self.generation, envelope)
        except asyncio.CancelledError:
            self.cancelled.emit(self.generation)
        except Exception as error:
            self.failed.emit(self.generation, redact_secrets(str(error)))
        finally:
            with self._lock:
                self._loop = self._task = None
