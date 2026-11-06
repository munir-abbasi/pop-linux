# Perish or Publish 0.2.0 — Native Desktop Release

We are excited to announce **pop-linux 0.2.0**, introducing an official **PySide6 Desktop Research Workspace** alongside the existing Python CLI and machine execution engine.

`pop-linux` provides researchers and academics with an open, high-performance environment for multi-source literature search, deduplication, and Harzing bibliometric analysis—without requiring Windows or emulation wrappers (Wine/Proton/VMs).

---

## What's New in v0.2.0

- **PySide6 Desktop Workspace**: A modern desktop interface with light and dark themes, responsive search forms, and persistent layout settings.
- **Multi-Provider Search**: Query OpenAlex, Semantic Scholar, CrossRef, PubMed, and Google Scholar with provider-aware filters (author, journal, ISSN, year bounds, min citations).
- **Harzing Bibliometrics Dashboard**: Real-time calculation of citation metrics ($h$-index, $g$-index, $e$-index, $hI_{\text{annual}}$, $hL_{\text{norm}}$, $\text{AWCR}$, $\text{AW-index}$, $i10$, and citations per year/author).
- **Interactive Results Table**: Client-side filtering and multi-column sorting without re-fetching from APIs.
- **Publication Details & Provenance**: Inspect full metadata, abstracts, DOI links, and per-provider provenance.
- **Multi-Format Exporting**: Export complete datasets or selected rows to BibTeX (`.bib`), CSV (`.csv`), JSON (`.json`), or RIS (`.ris`).
- **SQLite History & Diffing**: Search snapshots are saved automatically to local SQLite with built-in growth diffing and query rerun capabilities.
- **Multi-Provider Deduplication**: Strict DOI matching with normalized fuzzy title fallback ($\ge 0.92$).
- **Machine Execution Contract**: Full backward compatibility with the CLI and versioned JSON envelope (`pop-linux.execution/v1`) for AI agent workflows.

---

## Download Native Packages

Standalone native packages bundle all required Python and Qt runtime libraries. **No Python installation is required.**

| Platform | Architecture | Package Format | Quick Instructions |
|---|---|---|---|
| **Linux** | `x86_64` | `pop-linux-0.2.0-linux-x86_64.AppImage` | `chmod +x *.AppImage && ./pop-linux-0.2.0-linux-x86_64.AppImage` |
| **Linux (Debian / Ubuntu)** | `x86_64` | `pop-linux-0.2.0-linux-x86_64.deb` | `sudo apt install ./pop-linux-0.2.0-linux-x86_64.deb` |
| **Linux (Fedora / RHEL)** | `x86_64` | `pop-linux-0.2.0-linux-x86_64.rpm` | `sudo dnf install ./pop-linux-0.2.0-linux-x86_64.rpm` |
| **Linux Portable** | `x86_64` | `pop-linux-0.2.0-linux-x86_64.tar.gz` | Extract and run `PerishOrPublish/PerishOrPublish` |
| **Windows** | `x64` | `pop-linux-0.2.0-windows-amd64.zip` | Extract archive and launch `PerishOrPublish.exe` |
| **macOS (Apple Silicon)** | `arm64` | `pop-linux-0.2.0-darwin-arm64.zip` | Extract archive and launch `PerishOrPublish.app` (M1/M2/M3/M4) |
| **macOS (Intel)** | `x86_64` | `pop-linux-0.2.0-darwin-x86_64.zip` | Extract archive and launch `PerishOrPublish.app` (Intel x86_64) |

*Package SHA-256 digests are available in `SHA256SUMS`.*

---

## Python Package Installation

If you prefer installing via Python pip:

```bash
# Install CLI:
pip install pop-linux

# Install with PySide6 desktop interface:
pip install 'pop-linux[desktop]'

# Launch GUI:
pop-linux-gui
```

---

## License & Third-Party Notices

This project is licensed under the **PolyForm Noncommercial License 1.0.0**.
Third-party dependencies and Qt/PySide6 licenses (LGPL-3.0) are bundled in `packaging/THIRD_PARTY_NOTICES.md`.

- **Source Commit**: `a7df324`
- **Build Workflow**: [GitHub Actions #42232102092](https://github.com/munir-abbasi/pop-linux/actions/runs/42232102092)
