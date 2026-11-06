"""Entry point, screenshot capture and deterministic packaged-startup probe."""
import argparse
import sys
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Perish or Publish desktop research workspace")
    parser.add_argument("--screenshot", type=Path, help="Capture the normal workspace to PNG and exit")
    parser.add_argument("--self-test", type=Path, help="Exercise an offline research workflow and save JSON evidence")
    parser.add_argument("--isolated", action="store_true", help="Use temporary state without reading or changing personal data")
    args = parser.parse_args()
    try:
        from PySide6.QtCore import QCoreApplication, QSettings, QTimer
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        print("Desktop dependencies are unavailable. Install pop-linux[desktop] to launch the GUI.", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="pop-desktop-") as temporary:
        QCoreApplication.setOrganizationName("pop-linux")
        QCoreApplication.setApplicationName("Perish or Publish")
        if args.isolated or args.self_test:
            _isolate(Path(temporary))
            QSettings.setDefaultFormat(QSettings.Format.IniFormat)
            QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, temporary)
        app = QApplication([sys.argv[0]])
        app.setStyle("Fusion")
        from pop_linux.gui.style import apply_appearance
        from pop_linux.gui.window import MainWindow

        apply_appearance(app, QSettings().value("appearance", "system"))
        try:
            window = MainWindow(remember=not (args.isolated or args.self_test))
        except OSError:
            QMessageBox.critical(None, "Application data unavailable", "The application cannot open its configuration directory. Check filesystem access and available space.")
            return 2
        window.show()
        if args.self_test:
            from pop_linux.gui.smoke import run_smoke
            QTimer.singleShot(150, lambda: run_smoke(window, args.self_test, args.screenshot))
        elif args.screenshot:
            def capture():
                try:
                    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                    saved = window.grab().save(str(args.screenshot), "PNG")
                except OSError:
                    saved = False
                app.exit(0 if saved else 1)
            QTimer.singleShot(2000, capture)
        return app.exec()


def _isolate(directory: Path):
    from pop_linux import config
    # Set paths before importing history or cookie_bridge (they import constants).
    config.CONFIG_DIR = directory
    config.CONFIG_FILE = directory / "config.toml"
    config.COOKIES_FILE = directory / "cookies.json"
    config.HISTORY_DB_FILE = directory / "history.sqlite3"
    config.DEFAULT_CONFIG = {**config.DEFAULT_CONFIG, "cookies_file": str(config.COOKIES_FILE)}


if __name__ == "__main__":
    sys.exit(main())
