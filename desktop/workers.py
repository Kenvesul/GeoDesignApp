from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    """Signals emitted by AnalysisWorker."""

    finished = Signal(object)
    failed = Signal(str)


class AnalysisWorker(QRunnable):
    """Run a callable off the UI thread and emit either a result or an error."""

    def __init__(self, fn, payload):
        super().__init__()
        self.fn = fn
        self.payload = payload
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn(self.payload)
        except Exception as exc:  # pragma: no cover - defensive Qt boundary
            self.signals.failed.emit(str(exc))
            return
        self.signals.finished.emit(result)

