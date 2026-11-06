"""Offline runtime probe for source and frozen apps; never contacts providers.

The provider boundary is replaced; real engine, worker, UI, exporters and
SQLite history remain in use. No canned completion or success artifacts.
"""
import json
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication


def run_smoke(window, output: Path, screenshot: Path | None):
    from pop_linux import execution
    from pop_linux.models import Author, Paper
    from pop_linux.providers.base import ProviderFetchResult

    class OfflineProvider:
        name = "openalex"

        async def fetch(self, request):
            return ProviderFetchResult(papers=[
                Paper(title="Offline startup verification", authors=[Author(name="Test researcher")], citations=12, year=2020),
                Paper(title="Second verification record", citations=3, year=2022),
            ], returned_count=2, fetched_count=2, pages_or_requests=1)

    original = execution.resolve_providers
    execution.resolve_providers = lambda request: [OfflineProvider()]
    window.query.setText("Offline startup verification")
    window.provider.setCurrentIndex(window.provider.findData("openalex"))
    window.start_search()
    attempts = 0
    timer = QTimer(window)

    def check():
        nonlocal attempts
        attempts += 1
        if window.worker is not None and attempts < 300:
            return
        timer.stop()
        execution.resolve_providers = original
        steps = []
        try:
            if window.worker is not None:
                window.cancel_search()
                raise RuntimeError("Offline worker did not finish within 30 seconds")
            if window.result is None:
                raise RuntimeError("Search produced no dataset")
            steps.append({"step": "search", "passed": len(window.result.papers) == 2, "detail": "Existing engine and background worker returned two offline fixture records"})
            window.table.sortByColumn(4, Qt.SortOrder.AscendingOrder)
            window.local_filter.setText("Second")
            window.table.selectRow(0)
            selected = window.selected_papers()
            steps.append({"step": "table", "passed": len(selected) == 1 and selected[0].citations == 3 and len(window.result.papers) == 2,
                          "detail": "Sort, local filter and selection preserve the underlying dataset"})
            from pop_linux.gui.service import export_result
            from pop_linux.utils import history
            output.parent.mkdir(parents=True, exist_ok=True)
            export_path = output.with_suffix(".export.json")
            export_result(window.result, export_path, selected)
            snapshot = history.save_execution(window.envelope)
            restored = history.get_execution(snapshot)
            steps.append({"step": "storage", "passed": restored is not None and len(restored.papers) == 2 and
                          json.loads(export_path.read_text(encoding="utf-8"))["total_found"] == 1,
                          "detail": "Real SQLite snapshot round-trip and selected-record JSON export"})
            steps.append({"step": "metrics", "passed": window.result.metrics.h_index == 2 and window.metric_values["total_citations"].text() == "15",
                          "detail": "Engine metrics displayed: h-index 2, total citations 15"})
            if screenshot:
                window.local_filter.clear()
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                steps.append({"step": "screenshot", "passed": window.grab().save(str(screenshot), "PNG"), "detail": "Rendered Qt workspace captured"})
        except Exception as error:
            steps.append({"step": "runtime", "passed": False, "detail": str(error)})
        exit_code = 0 if steps and all(step["passed"] for step in steps) else 1
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({"version": 1, "steps": steps}, indent=2), encoding="utf-8")
        except OSError:
            exit_code = 1
        if window.worker is not None:
            window.worker.finished.connect(lambda: QApplication.instance().exit(exit_code))
        else:
            QApplication.instance().exit(exit_code)

    timer.timeout.connect(check)
    timer.start(100)
