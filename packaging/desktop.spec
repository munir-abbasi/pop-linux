# Native build only: execute through packaging/build_desktop.py.
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).parent
playwright_data, playwright_binaries, playwright_hidden = collect_all("playwright")
data = [(str(root / "LICENSE"), "."), (str(root / "packaging/THIRD_PARTY_NOTICES.md"), "."),
        (str(root / "build/desktop-notices"), "third-party-notices")]
data += copy_metadata("pop-linux") + playwright_data
data.append((str(root / "pop_linux/gui/resources/pop-linux.svg"), "pop_linux/gui/resources"))
hiddenimports = playwright_hidden + ["backports", "backports.tarfile"]
analysis = Analysis(
    [str(root / "packaging/desktop_entry.py")], pathex=[str(root)],
    binaries=playwright_binaries, datas=data, hiddenimports=hiddenimports,
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2"], noarchive=False,
)
pyz = PYZ(analysis.pure)
icon = root / "build" / ("pop-linux.icns" if sys.platform == "darwin" else "pop-linux.ico")
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name="PerishOrPublish",
          console=False, debug=False, strip=False, upx=False,
          icon=str(icon) if icon.exists() else None,
          codesign_identity=os.environ.get("MACOS_CODESIGN_IDENTITY") or None,
          entitlements_file=None)
collection = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="PerishOrPublish")
if sys.platform == "darwin":
    application = BUNDLE(collection, name="PerishOrPublish.app", icon=str(icon),
                         bundle_identifier="com.syntaxhouse.pop-linux",
                         info_plist={"NSHighResolutionCapable": True,
                                     "NSHumanReadableCopyright": "Copyright 2026 Munir Abbasi; PolyForm Noncommercial 1.0.0"})
