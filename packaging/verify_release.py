"""Fail closed on missing native packages, checksum mismatch or failed smoke data."""
import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path


def validate_archive(path: Path, executable: str, qt_plugin: str):
    if path.name.endswith(".zip"):
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            bad = archive.testzip()
            if bad:
                raise RuntimeError(f"Corrupt archive member: {bad}")
    else:
        with tarfile.open(path) as archive:
            names = archive.getnames()
    required = [executable, qt_plugin, "pydantic_core", "_sqlite3", "THIRD_PARTY_NOTICES.md"]
    for required_part in required:
        if not any(required_part in name for name in names):
            raise RuntimeError(f"{path.name} lacks {required_part}")


def verify(directory: Path, version: str, source: str):
    systems = {"linux-x86_64": ("tar.gz", "PerishOrPublish/PerishOrPublish", "libqxcb"),
               "windows-amd64": ("zip", "PerishOrPublish/PerishOrPublish.exe", "qwindows"),
               "darwin-x86_64": ("zip", "Contents/MacOS/PerishOrPublish", "libqcocoa"),
               "darwin-arm64": ("zip", "Contents/MacOS/PerishOrPublish", "libqcocoa")}
    for system, (extension, executable, qt_plugin) in systems.items():
        prefix = f"pop-linux-{version}-{system}"
        archive = directory / f"{prefix}.{extension}"
        validate_archive(archive, executable, qt_plugin)
        smoke = json.loads((directory / f"{prefix}-smoke.json").read_text(encoding="utf-8"))
        if not smoke.get("steps") or not all(step.get("passed") is True for step in smoke["steps"]):
            raise RuntimeError(f"Smoke test failed: {system}")
        evidence = json.loads((directory / f"{prefix}-provenance.json").read_text(encoding="utf-8"))
        if evidence["source_commit"] != source or evidence["version"] != version:
            raise RuntimeError(f"Wrong source revision/version: {system}")
    for suffix in ("AppImage", "deb", "rpm"):
        path = directory / f"pop-linux-{version}-linux-x86_64.{suffix}"
        if not path.is_file() or path.stat().st_size < 1000:
            raise RuntimeError(f"Required native asset missing: {path.name}")
    verify_checksums(directory)
    write_checksums(directory)


def verify_checksums(directory: Path):
    manifests = list(directory.glob("*-SHA256SUMS"))
    if len(manifests) != 4:
        raise RuntimeError("Expected checksums from all four native runners")
    for manifest in manifests:
        for line in manifest.read_text(encoding="utf-8").splitlines():
            expected, name = line.split("  ", 1)
            path = directory / name
            if path.parent != directory or not path.is_file():
                raise RuntimeError("Checksum manifest references an invalid file")
            with path.open("rb") as artifact:
                actual = hashlib.file_digest(artifact, "sha256").hexdigest()
            if actual != expected:
                raise RuntimeError(f"Artifact checksum mismatch: {name}")


def write_checksums(directory: Path):
    checksums = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            with path.open("rb") as artifact:
                checksums.append(f"{hashlib.file_digest(artifact, 'sha256').hexdigest()}  {path.name}")
    (directory / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")


if __name__ == "__main__":
    verify(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
