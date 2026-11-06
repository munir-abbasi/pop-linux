# Cross-Platform Packaging & Release Verification Matrix

## Release Overview
- **Version**: 0.2.0 (Tag `v0.2.0`)
- **Source Commit**: `a7df324adebdcfeb9239de25e4701bb630cfee4b`
- **Build Workflow**: GitHub Actions Run [42232102092](https://github.com/munir-abbasi/pop-linux/actions/runs/42232102092)
- **Release URL**: [https://github.com/munir-abbasi/pop-linux/releases/tag/v0.2.0](https://github.com/munir-abbasi/pop-linux/releases/tag/v0.2.0)
- **Release Verification Tool**: `packaging/verify_release.py` (Passed with zero defects)

---

## 1. Platform Coverage Matrix

| Target Operating System | Architecture | Package Format | Distribution File | Build Runner | Smoke Test Status | Verification Evidence |
|---|---|---|---|---|---|---|
| **Linux (Generic / FUSE)** | `x86_64` | AppImage | `pop-linux-0.2.0-linux-x86_64.AppImage` | `ubuntu-22.04` | **PASSED** (5/5 steps) | `APPIMAGE_EXTRACT_AND_RUN=1` verified offline; screenshot captured |
| **Linux (Debian / Ubuntu)** | `x86_64` | `.deb` | `pop-linux-0.2.0-linux-x86_64.deb` | `ubuntu-22.04` | **PASSED** (5/5 steps) | Package structure verified via `dpkg-deb`; XDG desktop file & icon |
| **Linux (Fedora / RHEL)** | `x86_64` | `.rpm` | `pop-linux-0.2.0-linux-x86_64.rpm` | `ubuntu-22.04` | **PASSED** (5/5 steps) | Package built via `rpmbuild`; directories and dependencies verified |
| **Linux Portable** | `x86_64` | `.tar.gz` | `pop-linux-0.2.0-linux-x86_64.tar.gz` | `ubuntu-22.04` | **PASSED** (5/5 steps) | Archive extracted and executed standalone |
| **Microsoft Windows** | `amd64` (x64) | Portable `.zip` | `pop-linux-0.2.0-windows-amd64.zip` | `windows-2022` | **PASSED** (5/5 steps) | `PerishOrPublish.exe` started headless; Qt plugins (`qwindows.dll`) |
| **macOS Apple Silicon** | `arm64` (M1–M4) | `.zip` (`.app`) | `pop-linux-0.2.0-darwin-arm64.zip` | `macos-15` | **PASSED** (5/5 steps) | Native Mach-O 64-bit arm64 binary; `libqcocoa.dylib` bundled |
| **macOS Intel** | `x86_64` | `.zip` (`.app`) | `pop-linux-0.2.0-darwin-x86_64.zip` | `macos-15-intel` | **PASSED** (5/5 steps) | Native Mach-O 64-bit x86_64 binary; `libqcocoa.dylib` bundled |

---

## 2. Release Asset Cryptographic Manifest

All packages and checksums are verified against the published release assets:

```text
5ba8bf1fe577fbea691002ca65aa5ff98436b71f98d9ad73d09a2ad4337b5206  pop-linux-0.2.0-linux-x86_64.AppImage
ed1b8fe54bda7dd64bb0f074a3f295b95ae0a82b09cba1573c9f22573f05dbfb  pop-linux-0.2.0-linux-x86_64.deb
78f4d3909ae2f303752944116c968f44ffea0cf200c8bdf922e379ff96a4b13d  pop-linux-0.2.0-linux-x86_64.rpm
dca9924c236b2d53accfeeedc612803b977bfb301c2ee1a3c617eb0d368d447a  pop-linux-0.2.0-linux-x86_64.tar.gz
44b20a80fa3dcff5e2dfcdd340156d11e5a52cf8a48ef8b89e672727a2327702  pop-linux-0.2.0-windows-amd64.zip
af2b0ada8335fe1411d3287db1c2b5ec6329759e6618d363717281f6c770c3ec  pop-linux-0.2.0-darwin-x86_64.zip
ecbc4d8a26c938f2e4df82ce1317ba0df77e92383c31aa967daee8e0fa0cff1a  pop-linux-0.2.0-darwin-arm64.zip
```

---

## 3. Package Structure & Runtime Bundling Verification

Each distribution archive was unpacked and verified for required runtime components:
1. **Python Interpreter**: Embedded CPython 3.11/3.12 shared library.
2. **Qt Dynamic Libraries**: Bundled Qt 6 shared libraries (`QtCore`, `QtGui`, `QtWidgets`).
3. **Platform Plugins**:
   - Linux: `platforms/libqxcb.so`, `platforms/libqwayland-generic.so`
   - Windows: `platforms/qwindows.dll`
   - macOS: `PlugIns/platforms/libqcocoa.dylib`
4. **SQLite Extension**: Native `_sqlite3` C-extension included for local history databases.
5. **Pydantic Core**: Native `pydantic_core` extension included.
6. **Licenses**: Embedded `THIRD_PARTY_NOTICES.md` and complete GNU LGPL 3.0 texts.

---

## 4. Release Verification Execution
The automated verification gate `packaging/verify_release.py` executed during the GitHub Actions workflow and confirmed:
- All 4 platform native archives unpack cleanly without corrupted members.
- Executables and required Qt plugins are present in every archive.
- Offline smoke-test JSON results show all steps passed (`search`, `table`, `storage`, `metrics`, `screenshot`).
- Source commit digest matches `a7df324adebdcfeb9239de25e4701bb630cfee4b`.
- Every artifact matches its SHA-256 digest in `SHA256SUMS`.
