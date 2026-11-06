"""Restrained research workspace; native widgets retain keyboard/scale behavior."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette


def apply_appearance(app, appearance: str):
    dark = appearance == "dark" or (appearance == "system" and app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
    background, surface, text, muted, border = (
        ("#151d26", "#1e2935", "#e6edf3", "#a3b4c5", "#334252") if dark else
        ("#f3f5f7", "#ffffff", "#182b3a", "#627588", "#dce4eb")
    )
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, background), (QPalette.ColorRole.Base, surface),
                        (QPalette.ColorRole.WindowText, text), (QPalette.ColorRole.Text, text),
                        (QPalette.ColorRole.ButtonText, text), (QPalette.ColorRole.Button, surface),
                        (QPalette.ColorRole.Highlight, "#167d89"), (QPalette.ColorRole.HighlightedText, "#ffffff"),
                        (QPalette.ColorRole.AlternateBase, background), (QPalette.ColorRole.ToolTipBase, surface),
                        (QPalette.ColorRole.ToolTipText, text)):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(f"""
        QMainWindow, QDialog {{ background: {background}; color: {text}; }}
        QWidget {{ font-family: 'Segoe UI', 'Noto Sans', 'Helvetica Neue', sans-serif; font-size: 13px; }}
        QLabel {{ color: {text}; background: transparent; }}
        QLabel#muted {{ color: {muted}; }}
        QLabel#heading {{ font-size: 26px; font-weight: 650; }}
        QLabel#brand {{ font-size: 21px; font-weight: 700; color: #29b3bb; }}
        QLabel#metricValue {{ font-size: 28px; font-weight: 650; }}
        QFrame#card, QFrame#searchPanel {{ background: {surface}; border: 1px solid {border}; border-radius: 9px; }}
        QFrame#sidebar {{ background: #142c3c; border: none; }}
        QFrame#sidebar QLabel {{ color: #b9ccd9; }}
        QFrame#sidebar QPushButton {{ background: transparent; color: #dce8ef; border: none; padding: 12px; text-align: left; }}
        QFrame#sidebar QPushButton:checked {{ background: #254758; color: white; border-radius: 6px; }}
        QPushButton {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: 6px; padding: 8px 13px; }}
        QPushButton:hover {{ border-color: #2197a0; }}
        QPushButton#primary {{ background: #117b85; color: white; border: none; font-weight: 650; padding: 11px; }}
        QPushButton:disabled {{ color: {muted}; }}
        QLineEdit, QSpinBox, QComboBox {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: 5px; padding: 7px; min-height: 18px; }}
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: #168993; }}
        QTableView, QPlainTextEdit, QListWidget {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: 5px; selection-background-color: #d9eef0; selection-color: #142c3c; }}
        QHeaderView::section {{ background: {background}; color: {muted}; border: none; border-bottom: 1px solid {border}; padding: 10px 8px; font-weight: 600; }}
        QTableView::item {{ padding: 7px; border-bottom: 1px solid {border}; }}
        QTabWidget::pane {{ border: none; }}
        QTabBar::tab {{ padding: 10px 16px; color: {muted}; border-bottom: 2px solid transparent; }}
        QTabBar::tab:selected {{ color: #168993; border-bottom: 2px solid #168993; }}
        QProgressBar {{ border: none; background: {border}; height: 3px; }}
        QProgressBar::chunk {{ background: #17929c; }}
        QStatusBar {{ color: {muted}; background: {surface}; }}
        QSplitter::handle {{ background: {background}; width: 8px; height: 8px; }}
    """)
