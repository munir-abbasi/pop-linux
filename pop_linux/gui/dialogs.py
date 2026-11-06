"""Native settings and snapshot comparison dialogs."""
import copy
import json
import shutil
from datetime import datetime, timezone

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from pop_linux import config
from pop_linux.providers.capabilities import CAPABILITIES


def spin(minimum: int, maximum: int, value: int) -> QSpinBox:
    widget = QSpinBox()
    widget.setRange(minimum, maximum)
    widget.setValue(value)
    return widget


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Application settings")
        self.resize(580, 650)
        self.cfg = config.load_config()
        layout = QVBoxLayout(self)
        intro = QLabel("Search defaults and provider access")
        intro.setObjectName("heading")
        layout.addWidget(intro)
        form = QFormLayout()
        layout.addLayout(form)
        self.provider = QComboBox()
        for key, caps in CAPABILITIES.items():
            self.provider.addItem(caps.display_name, key)
        self.provider.addItem("All non-interactive providers", "all")
        self.provider.setCurrentIndex(max(0, self.provider.findData(self.cfg.get("default_provider"))))
        form.addRow("Default &provider", self.provider)
        self.limit = spin(1, 10000, self.cfg.get("default_limit", 50))
        form.addRow("Default &result limit", self.limit)
        self.email = QLineEdit(self.cfg.get("polite_email", ""))
        form.addRow("Contact &email", self.email)
        self.timeout = spin(1, 300, self.cfg.get("google_scholar_timeout", 30))
        self.timeout.setSuffix(" seconds")
        form.addRow("Scholar &timeout", self.timeout)
        self.user_agent = QLineEdit(self.cfg.get("user_agent", ""))
        self.user_agent.setReadOnly(True)
        self.user_agent.setToolTip("Legacy Scholar uses its built-in user agent; changing this field is not supported.")
        form.addRow("Browser user agent", self.user_agent)
        self.keys: dict[str, QLineEdit] = {}
        for key, label in (("semanticscholar", "Semantic Scholar API key"), ("ncbi", "NCBI API key")):
            field = QLineEdit(self.cfg.get("api_keys", {}).get(key, ""))
            field.setEchoMode(QLineEdit.EchoMode.Password)
            field.setAccessibleName(label)
            form.addRow(label, field)
            self.keys[key] = field
        self.appearance = QComboBox()
        self.appearance.addItems(["system", "light", "dark"])
        self.appearance.setCurrentText(QSettings().value("appearance", "system"))
        form.addRow("&Appearance", self.appearance)
        self.export_dir = QLineEdit(QSettings().value("export_dir", ""))
        form.addRow("Default export &folder", self.export_dir)
        choose = QPushButton("Choose export folder…")
        choose.clicked.connect(self.choose_export_folder)
        form.addRow("", choose)
        for label, path in (("Configuration", config.CONFIG_FILE), ("Research history", config.HISTORY_DB_FILE),
                            ("Scholar cookies", config.COOKIES_FILE)):
            field = QLineEdit(str(path))
            field.setReadOnly(True)
            field.setAccessibleName(label + " location")
            form.addRow(label, field)
        note = QLabel("Keys are masked here and stored using the existing configuration file; they are not encrypted. "
                      "Research data stays in the locations above. Chromium is optional and installed separately. "
                      "No CAPTCHA automation is provided.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_export_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Default export folder", self.export_dir.text())
        if directory:
            self.export_dir.setText(directory)

    def save(self):
        updated = copy.deepcopy(self.cfg)
        updated.update(default_provider=self.provider.currentData(), default_limit=self.limit.value(),
                       polite_email=self.email.text().strip(), google_scholar_timeout=self.timeout.value())
        updated.setdefault("api_keys", {}).update({key: field.text() for key, field in self.keys.items()})
        try:
            if config.CONFIG_FILE.exists():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
                shutil.copy2(config.CONFIG_FILE, config.CONFIG_FILE.with_suffix(".toml.bak." + stamp))
            config.save_config(updated)
        except (OSError, TypeError, ValueError):
            self.error.setText("Settings could not be saved. Check access to the configuration directory; your backup was retained.")
            return
        preferences = QSettings()
        preferences.setValue("appearance", self.appearance.currentText())
        preferences.setValue("export_dir", self.export_dir.text().strip())
        self.accept()


def show_comparison(parent, difference: dict):
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"Snapshot #{difference['snapshot1_id']} → #{difference['snapshot2_id']}")
    dialog.resize(760, 600)
    layout = QVBoxLayout(dialog)
    heading = QLabel("Citation and bibliometric changes")
    heading.setObjectName("heading")
    layout.addWidget(heading)
    note = QLabel("Changes compare the two retrieved datasets. Provider coverage and query limits may differ.")
    note.setWordWrap(True)
    layout.addWidget(note)
    lines = ["METRIC CHANGES"]
    lines.extend(f"{key.replace('_delta', '').replace('_', ' ')}: {value:+g}" for key, value in difference["metrics_diff"].items())
    lines.append("\nCITATION CHANGES")
    lines.extend(f"{row['title']}\n  {row['old_citations']} → {row['new_citations']} ({row['delta']:+d})"
                 for row in difference["citation_deltas"])
    lines.append("\nNEW PUBLICATIONS")
    lines.extend(difference["new_papers"] or ["None found"])
    lines.append("\nAMBIGUOUS MATCHES (not treated as confirmed changes)")
    lines.extend(json.dumps(row, ensure_ascii=False) for row in difference["ambiguous_matches"])
    text = QPlainTextEdit()
    text.setReadOnly(True)
    text.setPlainText("\n".join(lines))
    layout.addWidget(text)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()
