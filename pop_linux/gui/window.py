"""Desktop research workspace backed by the existing Python engine."""
import json
from pathlib import Path

from PySide6.QtCore import QSettings, QSortFilterProxyModel, Qt
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QSplitter, QStackedWidget, QTableView,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from pop_linux import __version__, config
from pop_linux.execution import redact_secrets
from pop_linux.execution_models import ExecutionEnvelope
from pop_linux.gui.dialogs import SettingsDialog, show_comparison, spin
from pop_linux.gui.service import export_result, make_request, result_from_envelope, safe_external_url
from pop_linux.gui.style import apply_appearance
from pop_linux.gui.table import COLUMNS, PublicationModel
from pop_linux.gui.worker import SearchWorker
from pop_linux.models import QueryResult
from pop_linux.providers.capabilities import CAPABILITIES
from pop_linux.utils import history
from pop_linux.utils.deduplicator import deduplicate_papers
from pop_linux.utils.identity import identity_token
from pop_linux.utils.metrics import calculate_metrics


METRICS = (
    ("total_papers", "Publications", "Number of publications in this loaded dataset."),
    ("total_citations", "Total citations", "Sum of citation counts for the loaded papers. Merged records use the maximum observed count."),
    ("h_index", "h-index", "Largest h for which h papers each have at least h citations."),
    ("g_index", "g-index", "Largest g for which the top g papers have at least g² total citations."),
    ("avg_citations_per_paper", "Citations / paper", "Total citations divided by the number of papers in this dataset."),
    ("i10_index", "i10-index", "Number of loaded papers with at least 10 citations."),
    ("e_index", "e-index", "Square root of excess citations above h² in the h-core."),
    ("hI_annual", "hI annual", "Existing engine: author-normalized h-core citations divided by inclusive publication-year span."),
    ("hL_norm", "hL norm", "h-index after dividing each paper's citations by its author count."),
    ("awcr", "AWCR", "Sum of citations divided by each paper's inclusive age in years."),
    ("aw_index", "AW-index", "Square root of the age-weighted citation rate."),
    ("citations_per_author", "Citations / author", "Sum of each paper's citations divided by its author count."),
)


def label(text: str, name: str = "") -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(name)
    return widget


def button(text: str, callback, primary=False) -> QPushButton:
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    if primary:
        widget.setObjectName("primary")
    return widget


class MainWindow(QMainWindow):
    def __init__(self, *, remember=True):
        super().__init__()
        self.remember = remember
        self.worker = None
        self.generation = 0
        self.closing = False
        self.result: QueryResult | None = None
        self.envelope: ExecutionEnvelope | None = None
        self.parent_snapshot_id = None
        self.cfg = config.load_config()
        self.setWindowTitle("Perish or Publish · Research workspace")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / "resources/pop-linux.svg")))
        self.resize(1480, 940)
        self.setMinimumSize(1040, 700)
        self._build_workspace()
        self._build_menu()
        if remember:
            self._restore_preferences()
        self.statusBar().showMessage("Ready · Your research data stays on this computer")

    def _build_workspace(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(195)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(17, 28, 17, 20)
        nav.addWidget(label("P / P", "brand"))
        nav.addWidget(label("PERISH OR PUBLISH"))
        nav.addSpacing(36)
        self.search_nav = button("Research workspace", lambda: self.show_page(0))
        self.history_nav = button("Search history", lambda: self.show_page(1))
        for item in (self.search_nav, self.history_nav):
            item.setCheckable(True)
            nav.addWidget(item)
        self.search_nav.setChecked(True)
        nav.addStretch()
        nav.addWidget(label("RESEARCH, WITH CONTEXT"))
        footnote = label("Multiple sources.\nOne considered view.", "muted")
        footnote.setWordWrap(True)
        nav.addWidget(footnote)
        nav.addSpacing(20)
        nav.addWidget(button("Settings", self.show_settings))
        nav.addWidget(button("About this application", self.show_about))
        root.addWidget(sidebar)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(26, 24, 26, 16)
        layout.setSpacing(14)
        layout.addWidget(label("Research workspace", "heading"))
        layout.addWidget(label("Discover literature. Understand its impact. Keep the evidence.", "muted"))
        self.notice = label("Start a search to build your literature dataset.")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.pages = QStackedWidget()
        self.search_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.search_splitter.addWidget(self._search_panel())
        self.search_splitter.addWidget(self._results_panel())
        self.search_splitter.setStretchFactor(1, 1)
        self.search_splitter.setSizes([290, 950])
        self.pages.addWidget(self.search_splitter)
        self.pages.addWidget(self._history_panel())
        layout.addWidget(self.pages, 1)
        root.addWidget(body, 1)

    def _search_panel(self):
        panel = QFrame()
        panel.setObjectName("searchPanel")
        panel.setMinimumWidth(250)
        panel.setMaximumWidth(420)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(16, 18, 16, 18)
        outer.addWidget(label("NEW LITERATURE SEARCH", "muted"))
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        outer.addLayout(form)
        self.query = QLineEdit()
        self.query.setPlaceholderText("e.g. climate adaptation")
        self.query.returnPressed.connect(self.start_search)
        form.addRow("Research &query", self.query)
        self.provider = QComboBox()
        self.provider.addItem("All non-interactive providers", "all")
        for key, caps in CAPABILITIES.items():
            self.provider.addItem(caps.display_name, key)
        self.provider.setCurrentIndex(max(0, self.provider.findData(self.cfg.get("default_provider"))))
        form.addRow("Search &provider", self.provider)
        self.filters = {}
        for key, title, placeholder in (("author", "&Author", "Author name"), ("journal", "&Journal", "Journal or source"),
                                        ("issn", "&ISSN", "e.g. 0028-0836")):
            field = QLineEdit()
            field.setPlaceholderText(placeholder)
            form.addRow(title, field)
            self.filters[key] = field
        for key, title, maximum in (("year_from", "&From year", 9999), ("year_to", "&To year", 9999),
                                     ("min_citations", "Minimum &citations", 1000000000)):
            field = spin(0, maximum, 0)
            field.setSpecialValueText("No restriction")
            form.addRow(title, field)
            self.filters[key] = field
        self.limit = spin(1, 10000, self.cfg.get("default_limit", 50))
        form.addRow("Maximum &results per provider", self.limit)
        self.profile = QLineEdit()
        self.profile.setPlaceholderText("Optional Scholar profile ID")
        form.addRow("Scholar profile", self.profile)
        self.capability_help = label("", "muted")
        self.capability_help.setWordWrap(True)
        self.capability_help.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self.capability_help)
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.profile.textChanged.connect(self._provider_changed)
        self._provider_changed()
        outer.addStretch()
        self.search_button = button("Search literature", self.start_search, True)
        self.cancel_button = button("Cancel search", self.cancel_search)
        self.cancel_button.setEnabled(False)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumWidth(270)
        scroll.setMaximumWidth(430)
        scroll.setWidget(panel)
        panel.setObjectName("")
        wrapper = QFrame()
        wrapper.setObjectName("searchPanel")
        wrapper.setMinimumWidth(270)
        wrapper.setMaximumWidth(430)
        controls = QVBoxLayout(wrapper)
        controls.setContentsMargins(0, 0, 0, 12)
        controls.addWidget(scroll, 1)
        controls.addWidget(self.search_button)
        controls.addWidget(self.cancel_button)
        return wrapper

    def _results_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 0, 0, 0)
        self.scope = label("METRICS · No dataset loaded", "muted")
        self.scope.setWordWrap(True)
        layout.addWidget(self.scope)
        cards = QGridLayout()
        self.metric_values = {}
        for index, (key, title, explanation) in enumerate(METRICS[:6]):
            card, value = self._metric_card(title, explanation)
            cards.addWidget(card, index // 3, index % 3)
            self.metric_values[key] = value
        layout.addLayout(cards)
        tools = QHBoxLayout()
        self.local_filter = QLineEdit()
        self.local_filter.setPlaceholderText("Filter loaded rows…")
        self.local_filter.setAccessibleName("Local filter of loaded publications")
        self.local_filter.setToolTip("Filters this table only. The dataset, exports of all records, and metrics stay unchanged.")
        tools.addWidget(self.local_filter, 1)
        columns = QPushButton("Columns")
        self.columns_menu = QMenu(columns)
        columns.setMenu(self.columns_menu)
        tools.addWidget(columns)
        tools.addWidget(button("Save snapshot", self.save_current))
        tools.addWidget(button("Export…", self.export_dialog))
        layout.addLayout(tools)
        self.row_count = label("No publications yet · Table filtering and sorting are local.", "muted")
        layout.addWidget(self.row_count)
        self.tabs = QTabWidget()
        self.model = PublicationModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.local_filter.textChanged.connect(self._filter_rows)
        self.table = QTableView()
        self.table.setAccessibleName("Retrieved publications")
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(4, Qt.SortOrder.DescendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((300, 170, 65, 150, 85, 120, 180, 180)):
            self.table.setColumnWidth(column, width)
            action = QAction(COLUMNS[column][0], self)
            action.setCheckable(True)
            action.setChecked(column < 6)
            action.toggled.connect(lambda visible, col=column: self.table.setColumnHidden(col, not visible))
            self.columns_menu.addAction(action)
            self.table.setColumnHidden(column, column >= 6)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.table.doubleClicked.connect(self.inspect_publication)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setAccessibleName("Publication details and provenance")
        self.details.setPlaceholderText("Select a publication to inspect its abstract, metadata and sources.\nDouble-click a row for a larger view.")
        self.result_splitter = QSplitter(Qt.Orientation.Vertical)
        self.result_splitter.addWidget(self.table)
        self.result_splitter.addWidget(self.details)
        self.result_splitter.setSizes([360, 190])
        self.tabs.addTab(self.result_splitter, "Publications")
        metrics_page = QWidget()
        grid = QGridLayout(metrics_page)
        for index, (key, title, explanation) in enumerate(METRICS[6:]):
            card, value = self._metric_card(title, explanation)
            self.metric_values[key] = value
            grid.addWidget(card, index // 3, index % 3)
        self.tabs.addTab(metrics_page, "More metrics")
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setPlaceholderText("Provider reports, filter enforcement and warnings appear here after a search.")
        self.tabs.addTab(self.diagnostics, "Provider reports")
        layout.addWidget(self.tabs, 1)
        actions = QHBoxLayout()
        actions.addWidget(button("Copy selected metadata", self.copy_selected))
        actions.addWidget(button("Open DOI / publication", self.open_publication))
        actions.addStretch()
        layout.addLayout(actions)
        return panel

    def _metric_card(self, title, explanation):
        card = QFrame()
        card.setObjectName("card")
        card.setToolTip(explanation)
        card.setAccessibleName(title)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 11, 15, 12)
        layout.addWidget(label(title, "muted"))
        value = label("—", "metricValue")
        layout.addWidget(value)
        return card, value

    def _history_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(label("Saved search snapshots", "heading"))
        layout.addWidget(label("Open a snapshot, rerun its recorded request, or select two to compare.", "muted"))
        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(["Snapshot", "Search date (UTC)", "Query", "Providers", "Papers", "Status"])
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.itemDoubleClicked.connect(lambda _: self.open_history_selection())
        layout.addWidget(self.history_table, 1)
        self.history_details = QPlainTextEdit()
        self.history_details.setReadOnly(True)
        self.history_details.setMaximumHeight(200)
        self.history_details.setPlaceholderText("Select a snapshot to see its recorded query, providers and filters.")
        self.history_details.setAccessibleName("Saved search request and filters")
        self.history_table.selectionModel().selectionChanged.connect(self._history_selection_changed)
        layout.addWidget(self.history_details)
        controls = QHBoxLayout()
        for title, callback in (("Refresh", self.refresh_history), ("Open snapshot", self.open_history_selection),
                                ("Rerun search", self.rerun_history_selection), ("Compare two snapshots", self.compare_history_selection)):
            controls.addWidget(button(title, callback))
        layout.addLayout(controls)
        return panel

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("&File")
        for title, callback, shortcut in (("Open / merge JSON datasets…", self.open_datasets, "Ctrl+O"),
                                          ("Export dataset…", self.export_dialog, "Ctrl+E"),
                                          ("Save snapshot", self.save_current, "Ctrl+S"),
                                          ("Settings…", self.show_settings, "Ctrl+,"),
                                          ("Quit", self.close, "Ctrl+Q")):
            action = file_menu.addAction(title)
            action.triggered.connect(callback)
            action.setShortcut(QKeySequence(shortcut))
        edit = self.menuBar().addMenu("&Edit")
        copy = edit.addAction("Copy selected metadata")
        copy.setShortcut(QKeySequence("Ctrl+Shift+C"))
        copy.triggered.connect(self.copy_selected)
        focus = edit.addAction("Find in loaded results")
        focus.setShortcut(QKeySequence.StandardKey.Find)
        focus.triggered.connect(self.local_filter.setFocus)
        self.menuBar().addMenu("&Help").addAction("About…", self.show_about)

    def _provider_changed(self):
        key = self.provider.currentData()
        caps = list(CAPABILITIES.values()) if key == "all" else [CAPABILITIES[key]]
        if key == "all":
            caps = [cap for cap in caps if cap.included_in_all]
        modes = []
        for cap in caps:
            supported = cap.profile_filter_modes if self.profile.text().strip() else cap.filter_modes
            citation_note = "" if cap.citation_counts_available else " Citation counts are unavailable."
            modes.append(f"{cap.display_name}: {cap.description}{citation_note}\n" + ", ".join(
                f"{name.replace('_', ' ')} = {mode.replace('_', ' ')}" for name, mode in supported.items() if name != "year_to"))
        self.capability_help.setText("PROVIDER FILTER SUPPORT\n" + "\n\n".join(modes) +
                                    "\n\nQuery hints are not exact filters. Unknown publication years may remain in results.")
        self.profile.setEnabled(key != "all" and caps[0].profile_search)
        if not self.profile.isEnabled():
            self.profile.clear()

    def _read_filters(self):
        values = {}
        for key, field in self.filters.items():
            if isinstance(field, QLineEdit):
                value = field.text().strip()
            else:
                value = field.value()
            if value:
                values[key] = value
        return values

    def start_search(self):
        if self.worker is not None:
            return
        try:
            request = make_request(self.query.text(), self.provider.currentData(), self.limit.value(),
                                   self._read_filters(), self.profile.text())
        except ValueError as error:
            self.notice.setText(str(error))
            return
        self.parent_snapshot_id = None
        self._start_request(request)

    def _start_request(self, request):
        if self.worker is not None:
            self.notice.setText("Wait for the current search to finish or cancel it first.")
            return
        interactive = any(CAPABILITIES[key].interactive_risk for key in request.providers)
        if interactive:
            answer = QMessageBox.question(self, "Google Scholar browser access", "Google Scholar may restrict access and open a browser for you to complete a challenge manually. "
                                          "Chromium must be installed separately. This operation can save session cookies. Continue?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.generation += 1
        self.worker = SearchWorker(request, self.generation, self)
        self.worker.completed.connect(self._search_completed)
        self.worker.failed.connect(self._search_failed)
        self.worker.cancelled.connect(self._search_cancelled)
        self.worker.finished.connect(self._worker_finished)
        self.search_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.show()
        self.notice.setText("Searching providers… Existing results remain available. Progress is indeterminate.")
        self.worker.start()

    def cancel_search(self):
        if self.worker is not None:
            self.generation += 1
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.notice.setText("Cancelling network work…")

    def _search_completed(self, generation, envelope):
        if generation != self.generation or self.closing:
            return
        self.render_envelope(envelope)

    def _search_failed(self, generation, message):
        if generation == self.generation and not self.closing:
            self.notice.setText("Search failed: " + self._redact(message))

    def _search_cancelled(self, generation):
        if not self.closing:
            self.notice.setText("Search cancelled. Previous results were retained.")

    def _worker_finished(self):
        finished = self.worker
        self.worker = None
        if finished is not None:
            finished.deleteLater()
        self.search_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress.hide()
        if self.closing:
            self.close()

    def render_envelope(self, envelope):
        self.envelope = envelope
        self._render_result(result_from_envelope(envelope))
        context = envelope.metrics_context
        bounded = " · Result limit reached" if context and context.bounded_by_limit else ""
        self.scope.setText(f"METRICS · {len(envelope.papers)} retrieved publications · {envelope.status.upper()}{bounded}\n"
                           "This is a search dataset, not a complete author record. Merged citations use the maximum observed count. "
                           "Local table filters do not change these metrics.")
        reports = [f"{report.provider}: {report.status} · {report.counts.returned} returned · "
                   f"{report.pages_or_requests if report.pages_or_requests is not None else 'unknown'} requests\n"
                   f"Filter enforcement: {report.filter_modes or 'no filters requested'}" for report in envelope.provider_reports]
        reports.extend(f"{message.provider or 'Search'} · {message.code}: {message.message}" for message in envelope.warnings + envelope.errors)
        self.diagnostics.setPlainText(self._redact("\n\n".join(reports)))
        status = {"success": "Search completed", "partial": "Partial results — inspect Provider reports for limitations",
                  "empty": "No matching publications returned", "error": "All providers failed — inspect Provider reports"}[envelope.status]
        self.notice.setText(f"{status}. {len(envelope.papers)} publications · {envelope.elapsed_seconds:g} seconds.")

    def _render_result(self, result):
        metrics = result.metrics if result.metrics is not None else calculate_metrics(result.papers)
        self.result = result.model_copy(update={"metrics": metrics})
        self.local_filter.clear()
        self.model.set_papers(result.papers)
        for key, value in self.metric_values.items():
            value.setText(f"{getattr(metrics, key):,g}")
        self.details.clear()
        self._update_row_count()

    def _filter_rows(self, text):
        self.proxy.setFilterFixedString(text)
        self._update_row_count()

    def _update_row_count(self):
        self.row_count.setText(f"{self.proxy.rowCount():,} visible / {len(self.model.papers):,} loaded · "
                               f"{len(self.selected_papers())} selected · Table filter and sort are local")

    def selected_papers(self):
        return [self.model.papers[self.proxy.mapToSource(index).row()]
                for index in sorted(self.table.selectionModel().selectedRows(), key=lambda index: index.row())]

    def _selection_changed(self, *_):
        papers = self.selected_papers()
        self.details.setPlainText(self._publication_text(papers[0]) if papers else "Select a publication to inspect its details.")
        self._update_row_count()

    def _publication_text(self, paper):
        lines = [paper.title, "", paper.author_string]
        lines.extend(f"Affiliation: {author.affiliation}" for author in paper.authors if author.affiliation)
        lines.extend([f"Year: {paper.year or 'Not supplied'} · Journal: {paper.journal or 'Not supplied'}",
                      f"Citations: {paper.citations} · Provider: {paper.source_provider or 'Not supplied'}",
                      f"DOI: {paper.doi or 'Not supplied'}", f"URL: {paper.url or 'Not supplied'}"])
        observations = []
        if self.envelope:
            observations = [entry for entry in self.envelope.provenance if entry.canonical_id == identity_token(paper)]
        abstract = paper.abstract or next((obs.abstract for entry in observations for obs in entry.observations if obs.abstract), None)
        lines.extend(["", "ABSTRACT", abstract or "No abstract supplied by the provider."])
        if observations:
            lines.extend(["", "PROVIDER EVIDENCE", json.dumps([entry.model_dump() for entry in observations], ensure_ascii=False, indent=2)])
        return "\n".join(lines)

    def inspect_publication(self, *_):
        papers = self.selected_papers()
        if not papers:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Publication details")
        dialog.resize(780, 600)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(self._publication_text(papers[0]))
        layout.addWidget(text)
        layout.addWidget(button("Close", dialog.accept))
        dialog.exec()

    def copy_selected(self):
        papers = self.selected_papers()
        if papers:
            QApplication.clipboard().setText("\n\n".join(self._publication_text(paper) for paper in papers))
            self.notice.setText(f"Copied metadata for {len(papers)} selected publications.")

    def open_publication(self):
        papers = self.selected_papers()
        url = safe_external_url(papers[0]) if papers else None
        if url:
            QDesktopServices.openUrl(QUrl(url))
        else:
            self.notice.setText("Select a publication with an available DOI or web URL.")

    def export_dialog(self):
        if self.result is None or not self.result.papers:
            self.notice.setText("Load publications before exporting.")
            return
        selected = self.selected_papers()
        papers = self.result.papers
        scope = f"all {len(papers)} loaded records (including hidden rows)"
        if selected:
            choice = QMessageBox(self)
            choice.setWindowTitle("Choose export scope")
            choice.setText(f"Export {len(selected)} selected records, or all {len(papers)} loaded records?")
            only = choice.addButton("Selected records", QMessageBox.ButtonRole.AcceptRole)
            all_records = choice.addButton("All loaded records", QMessageBox.ButtonRole.ActionRole)
            choice.addButton(QMessageBox.StandardButton.Cancel)
            choice.exec()
            if choice.clickedButton() == only:
                papers, scope = selected, f"{len(selected)} selected records"
            elif choice.clickedButton() != all_records:
                return
        filters = "CSV (*.csv);;JSON (*.json);;BibTeX (*.bib);;RIS (*.ris)"
        directory = QSettings().value("export_dir", "")
        filename, chosen = QFileDialog.getSaveFileName(self, "Export " + scope, str(Path(directory) / "publications.csv"), filters)
        if not filename:
            return
        path = Path(filename)
        extension = chosen.split("*.")[-1].rstrip(")")
        if path.suffix.lower().lstrip(".") not in {"csv", "json", "bib", "ris"}:
            path = path.with_suffix("." + extension)
        if path != Path(filename) and path.exists():
            answer = QMessageBox.question(self, "Replace existing export?", f"Adding the format extension selects {path.name}, which already exists. Replace it?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.notice.setText("Export cancelled. The existing file was preserved.")
                return
        try:
            export_result(self.result, path, papers)
            self.notice.setText(f"Exported {scope} to {path.name}.")
        except (OSError, ValueError) as error:
            self.notice.setText("Export failed; retrieved results remain available. " + self._redact(str(error)))

    def save_current(self):
        if self.result is None:
            self.notice.setText("Load a dataset before saving a snapshot.")
            return
        try:
            snapshot = history.save_execution(self.envelope, parent_snapshot_id=self.parent_snapshot_id) if self.envelope else history.save_snapshot(self.result)
            self.parent_snapshot_id = snapshot
            self.notice.setText(f"Saved snapshot #{snapshot}. The full loaded dataset was saved.")
        except Exception as error:
            self.notice.setText("History write failed; results remain available. " + self._redact(str(error)))

    def show_page(self, index):
        self.pages.setCurrentIndex(index)
        self.search_nav.setChecked(index == 0)
        self.history_nav.setChecked(index == 1)
        if index == 1:
            self.refresh_history()

    def refresh_history(self):
        try:
            snapshots = history.list_snapshots(limit=1000)
            self.history_table.setRowCount(len(snapshots))
            for row, snapshot in enumerate(snapshots):
                for column, key in enumerate(("id", "timestamp", "query", "provider", "total_found", "status")):
                    self.history_table.setItem(row, column, QTableWidgetItem(str(snapshot[key] if snapshot[key] is not None else "Legacy")))
            self.notice.setText(f"{len(snapshots)} recent snapshots. Legacy snapshots have no recorded filters or rerunnable request.")
        except Exception as error:
            self.notice.setText("Could not load history: " + self._redact(str(error)))

    def _selected_snapshots(self):
        return [int(self.history_table.item(index.row(), 0).text()) for index in self.history_table.selectionModel().selectedRows()]

    def _history_selection_changed(self, *_):
        selected = self._selected_snapshots()
        if len(selected) != 1:
            self.history_details.setPlainText("Select one snapshot to inspect its recorded request, or two to compare.")
            return
        try:
            envelope = history.get_execution(selected[0])
            self.history_details.setPlainText(envelope.request.model_dump_json(indent=2) if envelope else
                                              "Legacy snapshot: request filters were not recorded. Publications and metrics can still be reopened.")
        except Exception as error:
            self.history_details.setPlainText("Could not read recorded request: " + self._redact(str(error)))

    def open_history_selection(self):
        selected = self._selected_snapshots()
        if len(selected) == 1:
            self.open_snapshot(selected[0])
        else:
            self.notice.setText("Select one saved snapshot to open.")

    def open_snapshot(self, snapshot):
        if self.worker is not None:
            self.cancel_search()
        try:
            envelope = history.get_execution(snapshot)
            result = history.get_snapshot(snapshot) if envelope is None else None
            if envelope:
                self.render_envelope(envelope)
                self._populate_request(envelope.request)
            elif result:
                self.envelope = None
                self._render_result(result)
                self.scope.setText("METRICS · Legacy saved dataset. Original filters and completeness were not recorded.")
                self.diagnostics.setPlainText("Legacy snapshot: provider execution reports and filters are unavailable.")
            else:
                raise ValueError("Snapshot no longer exists.")
            self.parent_snapshot_id = snapshot
            self.show_page(0)
            self.notice.setText(f"Opened snapshot #{snapshot}. Saved values are shown; no network request was made.")
        except Exception as error:
            self.notice.setText("Could not reopen snapshot: " + self._redact(str(error)))

    def _populate_request(self, request):
        self.query.setText(request.query)
        key = request.providers[0] if len(request.providers) == 1 else "all"
        self.provider.setCurrentIndex(max(0, self.provider.findData(key)))
        self.limit.setValue(request.limit)
        self.profile.setText(request.profile_id or "")
        for name, field in self.filters.items():
            value = getattr(request.filters, name)
            if isinstance(field, QLineEdit):
                field.setText(value or "")
            else:
                field.setValue(value or 0)

    def rerun_history_selection(self):
        selected = self._selected_snapshots()
        if len(selected) != 1:
            self.notice.setText("Select one recorded search to rerun.")
            return
        try:
            envelope = history.get_execution(selected[0])
            if envelope is None:
                raise ValueError("Legacy snapshot has no recorded request. Start a new search with explicit filters instead.")
            self.parent_snapshot_id = selected[0]
            self._populate_request(envelope.request)
            self.show_page(0)
            self._start_request(envelope.request.model_copy(update={"interaction_policy": "allow", "persistence_policy": "explicit"}))
        except Exception as error:
            self.notice.setText(self._redact(str(error)))

    def compare_history_selection(self):
        selected = sorted(self._selected_snapshots())
        if len(selected) != 2:
            self.notice.setText("Select two snapshots. The earlier snapshot is the comparison baseline.")
            return
        try:
            show_comparison(self, history.compute_snapshot_diff(*selected))
        except Exception as error:
            self.notice.setText("Comparison failed: " + self._redact(str(error)))

    def open_datasets(self):
        filenames, _ = QFileDialog.getOpenFileNames(self, "Open or merge saved JSON datasets", "", "QueryResult JSON (*.json)")
        if not filenames:
            return
        if self.worker is not None:
            self.cancel_search()
        try:
            datasets = [QueryResult.model_validate_json(Path(filename).read_text(encoding="utf-8")) for filename in filenames]
            papers = deduplicate_papers([paper for dataset in datasets for paper in dataset.papers])
            result = datasets[0] if len(datasets) == 1 else QueryResult(query="Merged Dataset", provider="merged", total_found=len(papers),
                                                                      papers=papers, metrics=calculate_metrics(papers))
            self.envelope = None
            self.parent_snapshot_id = None
            self._render_result(result)
            self.scope.setText("METRICS · Loaded JSON dataset. Search completeness is unknown. Merged citations use maximum observed counts.")
            self.diagnostics.setPlainText("Loaded QueryResult files do not include provider execution reports or full provenance.")
            self.show_page(0)
            self.notice.setText(f"Loaded {len(result.papers)} publications from {len(filenames)} files.")
        except (OSError, ValueError) as error:
            self.notice.setText("Dataset import failed: " + self._redact(str(error)))

    def _redact(self, message):
        text = redact_secrets(message)
        for value in self.cfg.get("api_keys", {}).values():
            if value:
                text = text.replace(str(value), "[REDACTED]")
        return text

    def show_settings(self):
        if self.worker is not None:
            self.notice.setText("Finish or cancel the active search before changing provider settings.")
            return
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.cfg = config.load_config()
            apply_appearance(QApplication.instance(), QSettings().value("appearance", "system"))
            self.notice.setText("Settings saved. Provider defaults apply to the next application launch.")

    def show_about(self):
        QMessageBox.about(self, "About Perish or Publish", f"Perish or Publish {__version__}\n\nScientific literature search and bibliometrics.\n"
                          "Copyright 2026 Munir Abbasi\nPolyForm Noncommercial License 1.0.0\n"
                          "https://github.com/munir-abbasi/pop-linux\n\n"
                          "Built with Python, PySide6/Qt, HTTPX, Pydantic, Typer, Rich, BeautifulSoup and Playwright.\n"
                          "Inspired by the Publish or Perish concept; no official affiliation.\n"
                          "Qt/PySide6 retain their separate licenses. See bundled third-party notices.")

    def _restore_preferences(self):
        preferences = QSettings()
        for key, restore in (("geometry", self.restoreGeometry), ("search_splitter", self.search_splitter.restoreState),
                             ("result_splitter", self.result_splitter.restoreState), ("columns", self.table.horizontalHeader().restoreState)):
            saved = preferences.value(key)
            if saved is not None:
                restore(saved)

    def closeEvent(self, event):
        if self.worker is not None:
            self.closing = True
            self.cancel_search()
            self.hide()
            event.ignore()
            return
        if self.remember:
            preferences = QSettings()
            for key, value in (("geometry", self.saveGeometry()), ("search_splitter", self.search_splitter.saveState()),
                               ("result_splitter", self.result_splitter.saveState()), ("columns", self.table.horizontalHeader().saveState())):
                preferences.setValue(key, value)
        event.accept()
