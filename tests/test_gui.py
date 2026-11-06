"""Qt integration: one complete research flow and one cancellation/failure flow.

Requires the desktop-test extra. CI installs it; CLI-only installs skip explicitly.
"""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("PySide6", reason="install .[desktop-test] to verify desktop runtime")
from PySide6.QtCore import QCoreApplication, QElapsedTimer, QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from pop_linux import config, execution  # noqa: E402
from pop_linux.gui.window import MainWindow  # noqa: E402
from pop_linux.gui.dialogs import SettingsDialog  # noqa: E402
from pop_linux.gui.service import export_result  # noqa: E402
from pop_linux.models import Author, Paper  # noqa: E402
from pop_linux.providers.base import ProviderFetchResult  # noqa: E402
from pop_linux.utils import history  # noqa: E402


def wait_until(predicate, timeout=5000):
    timer = QElapsedTimer()
    timer.start()
    while not predicate() and timer.elapsed() < timeout:
        QTest.qWait(10)
    assert predicate(), "Qt operation did not finish within the timeout"


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def desktop(qapp, monkeypatch, tmp_path):
    previous_format = QSettings.defaultFormat()
    previous_organization = QCoreApplication.organizationName()
    previous_application = QCoreApplication.applicationName()
    QCoreApplication.setOrganizationName("pop-linux-tests")
    QCoreApplication.setApplicationName("desktop-integration")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.toml")
    monkeypatch.setattr(history, "HISTORY_DB_FILE", tmp_path / "history.sqlite3")
    config.save_config({**config.DEFAULT_CONFIG, "api_keys": {"ncbi": "private-test-key"}})
    window = MainWindow(remember=False)
    window.show()
    yield window
    window.close()
    wait_until(lambda: window.worker is None)
    QApplication.processEvents()
    QSettings.setDefaultFormat(previous_format)
    QCoreApplication.setOrganizationName(previous_organization)
    QCoreApplication.setApplicationName(previous_application)


def test_research_flow_uses_engine_sort_filter_details_export_history(desktop, monkeypatch, tmp_path):
    provider = AsyncMock()
    provider.name = "openalex"
    provider.fetch.return_value = ProviderFetchResult(
        papers=[Paper(title="Alpha study", citations=5, year=2020, authors=[Author(name="A. Researcher")], abstract="Available abstract"),
                Paper(title="Beta study", citations=20, year=2024)],
        returned_count=2, fetched_count=2, pages_or_requests=1,
    )
    failed = AsyncMock()
    failed.name = "crossref"
    failed.fetch.side_effect = RuntimeError("token=private-test-key")
    monkeypatch.setattr(execution, "resolve_providers", lambda request: [provider, failed])
    desktop.query.setText("research")
    desktop.start_search()
    wait_until(lambda: desktop.worker is None)
    assert desktop.envelope.status == "partial"
    assert "private-test-key" not in desktop.diagnostics.toPlainText()
    assert desktop.result.metrics.h_index == 2
    assert desktop.metric_values["total_citations"].text() == "25"
    desktop.table.sortByColumn(4, Qt.SortOrder.AscendingOrder)
    assert desktop.proxy.index(0, 4).data() == "5"
    desktop.local_filter.setText("Alpha")
    assert desktop.proxy.rowCount() == 1 and len(desktop.result.papers) == 2
    desktop.table.selectRow(0)
    assert "Available abstract" in desktop.details.toPlainText()
    selected = desktop.selected_papers()
    assert len(selected) == 1 and selected[0].title == "Alpha study"
    output = tmp_path / "selected.json"
    export_result(desktop.result, output, selected)
    assert json.loads(output.read_text())["total_found"] == 1
    desktop.save_current()
    first = history.list_snapshots()[0]["id"]
    desktop.save_current()
    second = history.list_snapshots()[0]["id"]
    assert history.compute_snapshot_diff(first, second)["metrics_diff"]["total_citations_delta"] == 0
    desktop.open_snapshot(first)
    assert len(desktop.result.papers) == 2
    settings = SettingsDialog(desktop)
    assert settings.keys["ncbi"].echoMode() == QLineEdit.EchoMode.Password
    settings.email.setText("contact@example.com")
    settings.save()
    saved = config.load_config()
    assert saved["polite_email"] == "contact@example.com" and saved["api_keys"]["ncbi"] == "private-test-key"
    assert list(tmp_path.glob("config.toml.bak.*"))
    settings.close()
    imported = json.loads(output.read_text())
    imported["metrics"] = None
    output.write_text(json.dumps(imported))
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getOpenFileNames", lambda *args: ([str(output)], "JSON (*.json)"))
    desktop.open_datasets()
    assert desktop.metric_values["total_papers"].text() == "1" and desktop.metric_values["h_index"].text() == "1"
    protected = tmp_path / "existing.csv"
    protected.write_text("keep this existing export")
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog.getSaveFileName", lambda *args: (str(protected.with_suffix("")), "CSV (*.csv)"))
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    desktop.export_dialog()
    assert protected.read_text() == "keep this existing export"
    assert desktop.grab().save(str(tmp_path / "research-workspace.png"))


def test_invalid_input_and_cancelled_close_do_not_replace_results(desktop, monkeypatch, tmp_path):
    desktop.query.clear()
    desktop.start_search()
    assert desktop.worker is None and "Enter" in desktop.notice.text()
    provider = AsyncMock()
    provider.name = "openalex"

    async def wait(request):
        await asyncio.sleep(30)

    provider.fetch.side_effect = wait
    monkeypatch.setattr(execution, "resolve_providers", lambda request: [provider])
    desktop.query.setText("cancel")
    desktop.start_search()
    desktop.cancel_search()
    wait_until(lambda: desktop.worker is None)
    assert desktop.result is None
    provider.fetch.side_effect = RuntimeError("authorization=private-test-key")
    desktop.start_search()
    wait_until(lambda: desktop.worker is None)
    assert desktop.envelope.status == "error" and "All providers failed" in desktop.notice.text()
    assert "private-test-key" not in desktop.diagnostics.toPlainText()
    provider.fetch.side_effect = None
    provider.fetch.return_value = ProviderFetchResult(returned_count=0)
    desktop.start_search()
    wait_until(lambda: desktop.worker is None)
    assert desktop.envelope.status == "empty" and "No matching publications" in desktop.notice.text()
    provider.fetch.side_effect = wait
    desktop.start_search()
    desktop.close()
    wait_until(lambda: desktop.worker is None)
    assert not desktop.isVisible()
    (tmp_path / "lifecycle.json").write_text('{"cancelled":true,"closed_without_worker":true}')
