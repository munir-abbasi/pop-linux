"""Native Linux packages from the tested PyInstaller directory bundle."""
import hashlib
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def run(arguments, **kwargs):
    subprocess.run([str(argument) for argument in arguments], cwd=ROOT, check=True, **kwargs)


def github_asset(repository: str, tag: str, name: str, destination: Path) -> dict:
    """Download a release asset and require GitHub's SHA-256 digest.

    Record immutable asset ID and digest for review/reproduction. A missing
    digest fails closed, rather than executing an unchecked downloaded tool.
    """
    url = f"https://api.github.com/repos/{repository}/releases/tags/{tag}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "pop-linux-desktop-build"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = httpx.get(url, headers=headers, timeout=60, follow_redirects=True)
    response.raise_for_status()
    release = response.json()
    asset = next((item for item in release["assets"] if item["name"] == name), None)
    if not asset or not (asset.get("digest") or "").startswith("sha256:"):
        raise RuntimeError(f"No SHA-256-verified asset available: {repository}/{tag}/{name}")
    expected = asset["digest"].split(":", 1)[1]
    with httpx.stream("GET", asset["browser_download_url"], headers={"User-Agent": headers["User-Agent"]},
                      timeout=120, follow_redirects=True) as response, destination.open("wb") as output:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            output.write(chunk)
    with destination.open("rb") as downloaded:
        actual = hashlib.file_digest(downloaded, "sha256").hexdigest()
    if actual != expected:
        raise RuntimeError("Downloaded AppImage component checksum mismatch")
    destination.chmod(0o755)
    return {"repository": repository, "tag": tag, "asset_id": asset["id"], "sha256": expected, "url": asset["browser_download_url"]}


def stage_payload(bundle: Path, destination: Path):
    shutil.copytree(bundle, destination / "usr/lib/pop-linux", dirs_exist_ok=True)
    applications = destination / "usr/share/applications"
    applications.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "packaging/pop-linux.desktop", applications)
    icons = destination / "usr/share/icons/hicolor/scalable/apps"
    icons.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "pop_linux/gui/resources/pop-linux.svg", icons)
    binary = destination / "usr/bin/pop-linux-gui"
    binary.parent.mkdir(parents=True, exist_ok=True)
    if not binary.is_symlink():
        binary.symlink_to("../lib/pop-linux/PerishOrPublish")


def build_deb(bundle: Path, output: Path, version: str):
    stage = ROOT / "build/deb-root"
    stage_payload(bundle, stage)
    control = stage / "DEBIAN/control"
    control.parent.mkdir(parents=True, exist_ok=True)
    control.write_text(f"""Package: pop-linux-desktop
Version: {version}
Architecture: amd64
Maintainer: Munir Abbasi <info@syntaxhouse.com>
Section: science
Priority: optional
Depends: libc6 (>= 2.35), libglib2.0-0, libgl1, libegl1, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-keysyms1, libxcb-shape0, libxcb-xinerama0, libxcb-randr0, libxcb-render-util0, libxcb-image0, libdbus-1-3, libfontconfig1
Description: Scholarly search and bibliometric research desktop
 Python and Qt application with an independent command-line interface.
""", encoding="utf-8")
    path = output / f"pop-linux-{version}-linux-x86_64.deb"
    run(["dpkg-deb", "--build", "--root-owner-group", stage, path])
    run(["dpkg-deb", "--contents", path])
    return path


def build_rpm(bundle: Path, output: Path, version: str):
    stage = ROOT / "build/rpm-payload"
    stage_payload(bundle, stage)
    top = ROOT / "build/rpmbuild"
    top.mkdir(parents=True, exist_ok=True)
    spec = top / "pop-linux.spec"
    # %install copies a staged payload; it never runs an installation on the host.
    spec.write_text(f"""Name: pop-linux-desktop
Version: {version}
Release: 1
Summary: Scholarly search and bibliometric research desktop
License: LicenseRef-PolyForm-Noncommercial-1.0.0
BuildArch: x86_64
AutoReqProv: no
Requires: glibc >= 2.35, glib2, mesa-libGL, mesa-libEGL, libxkbcommon, libxkbcommon-x11, libxcb, xcb-util-cursor, xcb-util-image, xcb-util-keysyms, xcb-util-wm, xcb-util-renderutil, fontconfig, dbus-libs
%description
Python and Qt scientific research workspace.
%install
mkdir -p "%{{buildroot}}"
cp -a "{stage}/usr" "%{{buildroot}}/"
%files
/usr/lib/pop-linux
/usr/bin/pop-linux-gui
/usr/share/applications/pop-linux.desktop
/usr/share/icons/hicolor/scalable/apps/pop-linux.svg
""", encoding="utf-8")
    run(["rpmbuild", "--define", f"_topdir {top}", "--define", "__os_install_post %{nil}", "-bb", spec])
    built = list((top / "RPMS").rglob("*.rpm"))
    if len(built) != 1:
        raise RuntimeError("Expected exactly one RPM")
    target = output / f"pop-linux-{version}-linux-x86_64.rpm"
    shutil.copy2(built[0], target)
    run(["rpm", "-qlp", target])
    return target


def build_linux_packages(bundle: Path, output: Path, version: str, smoke):
    if platform.machine().lower() not in {"x86_64", "amd64"}:
        raise RuntimeError("Linux packaging currently requires an x86_64 native runner")
    tools = ROOT / "build/appimage-tools"
    tools.mkdir(parents=True, exist_ok=True)
    tool = tools / "appimagetool.AppImage"
    runtime = tools / "runtime-x86_64"
    provenance = [github_asset("AppImage/appimagetool", "1.9.1", "appimagetool-x86_64.AppImage", tool),
                  github_asset("AppImage/type2-runtime", "continuous", "runtime-x86_64", runtime)]
    (output / "appimage-toolchain.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    appdir = ROOT / "build/PerishOrPublish.AppDir"
    stage_payload(bundle, appdir)
    shutil.copy2(ROOT / "packaging/pop-linux.desktop", appdir)
    shutil.copy2(ROOT / "pop_linux/gui/resources/pop-linux.svg", appdir)
    (appdir / "AppRun").write_text('#!/bin/sh\nHERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\nexec "$HERE/usr/lib/pop-linux/PerishOrPublish" "$@"\n', encoding="utf-8")
    (appdir / "AppRun").chmod(0o755)
    image = output / f"pop-linux-{version}-linux-x86_64.AppImage"
    environment = {**os.environ, "APPIMAGE_EXTRACT_AND_RUN": "1", "ARCH": "x86_64"}
    run([tool, "--runtime-file", runtime, appdir, image], timeout=180, env=environment)
    smoke(image, "appimage", environment)
    deb = build_deb(bundle, output, version)
    rpm = build_rpm(bundle, output, version)
    for path in (deb, rpm):
        if not path.is_file() or path.stat().st_size < 1000:
            raise RuntimeError(f"Missing Linux package: {path.name}")
    deb_check = ROOT / "build/deb-startup"
    deb_check.mkdir(parents=True, exist_ok=True)
    run(["dpkg-deb", "--extract", deb, deb_check])
    smoke(deb_check / "usr/lib/pop-linux/PerishOrPublish", "deb")
    rpm_check = ROOT / "build/rpm-startup"
    rpm_check.mkdir(parents=True, exist_ok=True)
    with subprocess.Popen(["rpm2cpio", str(rpm)], stdout=subprocess.PIPE) as extraction:
        subprocess.run(["cpio", "-idm", "--quiet"], cwd=rpm_check, stdin=extraction.stdout, check=True)
        extraction.stdout.close()
        if extraction.wait() != 0:
            raise RuntimeError("RPM extraction failed")
    smoke(rpm_check / "usr/lib/pop-linux/PerishOrPublish", "rpm")
