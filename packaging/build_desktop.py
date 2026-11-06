"""Build on the target OS, smoke-test frozen startup, then archive real outputs."""
import hashlib
import importlib.metadata as metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "packaging") not in sys.path:
    sys.path.insert(0, str(ROOT / "packaging"))
ARTIFACTS = ROOT / "dist" / "release"
PYSIDE_DISTRIBUTIONS = ("PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6")
PYSIDE_LICENSE_HASHES = {
    "LGPL-3.0-only.txt": "da7eabb7bafdf7d3ae5e9f223aa5bdc1eece45ac569dc21b3b037520b4464768",
    "GPL-3.0-only.txt": "8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903",
    "GPL-2.0-only.txt": "8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643",
}


def run(arguments, **kwargs):
    subprocess.run([str(argument) for argument in arguments], cwd=ROOT, check=True, **kwargs)


def collect_notices():
    target = ROOT / "build" / "desktop-notices"
    target.mkdir(parents=True, exist_ok=True)
    packages = {}
    for distribution in metadata.distributions():
        name = distribution.metadata["Name"]
        packages[name] = distribution.version
        for relative in distribution.files or []:
            if not any(word in str(relative).lower() for word in ("license", "copying", "notice", "copyright")):
                continue
            source = Path(distribution.locate_file(relative))
            if source.is_file() and source.suffix.lower() in {"", ".txt", ".md", ".rst", ".html"}:
                destination = target / name / str(relative).replace("../", "_")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    qt_versions = {}
    for name in PYSIDE_DISTRIBUTIONS:
        distribution = metadata.distribution(name)
        license_expression = distribution.metadata.get("License", "")
        if "LGPL-3.0-only" not in license_expression:
            raise RuntimeError(f"Unexpected {name} licensing metadata: {license_expression}")
        qt_versions[name] = distribution.version
    if len(set(qt_versions.values())) != 1:
        raise RuntimeError(f"Qt for Python component versions differ: {qt_versions}")
    source = ROOT / "packaging" / "licenses" / "pyside6"
    for name, expected in PYSIDE_LICENSE_HASHES.items():
        path = source / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Missing or changed Qt for Python license text: {name}")
    shutil.copytree(source, target / "qt-for-python", dirs_exist_ok=True)
    (target / "qt-for-python" / "distribution-metadata.json").write_text(
        json.dumps({"components": qt_versions, "licensing": "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
                    "license_text_source": "Fedora python3-pyside6-6.11.2-1.fc44.x86_64"}, indent=2),
        encoding="utf-8",
    )
    (target / "installed-versions.json").write_text(json.dumps(packages, indent=2), encoding="utf-8")


def create_icons():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(QColor("#142c3c"))
    painter = QPainter(image)
    painter.fillRect(52, 65, 66, 124, QColor("#e1eff0"))
    painter.fillRect(130, 65, 74, 124, QColor("#23a8af"))
    painter.end()
    target = ROOT / "build"
    target.mkdir(exist_ok=True)
    if sys.platform == "win32" and not image.save(str(target / "pop-linux.ico"), "ICO"):
        raise RuntimeError("Windows icon export failed")
    if sys.platform == "darwin":
        iconset = target / "pop-linux.iconset"
        iconset.mkdir(exist_ok=True)
        for size in (16, 32, 128, 256, 512):
            for factor, suffix in ((1, ""), (2, "@2x")):
                scaled = image.scaled(size * factor, size * factor, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                if not scaled.save(str(iconset / f"icon_{size}x{size}{suffix}.png")):
                    raise RuntimeError("macOS icon export failed")
        run(["iconutil", "--convert", "icns", "--output", target / "pop-linux.icns", iconset])
    app.quit()


def smoke(executable: Path, label: str, environment=None):
    output = ARTIFACTS / f"{label}-smoke.json"
    screenshot = ARTIFACTS / f"{label}-workspace.png"
    run([executable, "--isolated", "--self-test", output, "--screenshot", screenshot], timeout=90, env=environment)
    data = json.loads(output.read_text(encoding="utf-8"))
    if not data.get("steps") or not all(step.get("passed") is True for step in data["steps"]):
        raise RuntimeError(f"Frozen startup verification failed: {label}")
    if not screenshot.is_file() or screenshot.stat().st_size < 1000:
        raise RuntimeError("Frozen startup screenshot missing or empty")


def checksum_outputs(label):
    files = sorted(path for path in ARTIFACTS.iterdir() if path.is_file() and not path.name.endswith("SHA256SUMS"))
    if not files:
        raise RuntimeError("No release assets produced")
    checksums = []
    for path in files:
        with path.open("rb") as artifact:
            checksums.append(f"{hashlib.file_digest(artifact, 'sha256').hexdigest()}  {path.name}")
    (ARTIFACTS / f"{label}-SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")


def main():
    from pop_linux import __version__

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    collect_notices()
    create_icons()
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "packaging/desktop.spec"])
    system = platform.system().lower()
    architecture = platform.machine().lower()
    label = f"pop-linux-{__version__}-{system}-{architecture}"
    if sys.platform == "darwin":
        bundle = ROOT / "dist/PerishOrPublish.app"
        executable = bundle / "Contents/MacOS/PerishOrPublish"
        smoke(executable, label)
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", bundle, ARTIFACTS / (label + ".zip")])
    else:
        bundle = ROOT / "dist/PerishOrPublish"
        executable = bundle / ("PerishOrPublish.exe" if sys.platform == "win32" else "PerishOrPublish")
        smoke(executable, label)
        if sys.platform == "win32":
            shutil.make_archive(str(ARTIFACTS / label), "zip", bundle.parent, bundle.name)
        else:
            shutil.make_archive(str(ARTIFACTS / label), "gztar", bundle.parent, bundle.name)
            from linux_packages import build_linux_packages
            build_linux_packages(bundle, ARTIFACTS, __version__, smoke)
    provenance = {
        "version": __version__, "platform": platform.platform(), "architecture": architecture,
        "python": sys.version, "source_commit": os.environ.get("SOURCE_SHA", "unrecorded-local-build"),
        "workflow": os.environ.get("WORKFLOW_URL", "local"),
        "signing": "identity configured; verify signature separately" if os.environ.get("MACOS_CODESIGN_IDENTITY") else "unsigned / not notarized",
        "installed_packages": {distribution.metadata["Name"]: distribution.version for distribution in metadata.distributions()},
    }
    (ARTIFACTS / f"{label}-provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    checksum_outputs(label)


if __name__ == "__main__":
    main()
