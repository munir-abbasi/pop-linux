# Craft Anything Recovery and File Provenance Manifest

## Executive Summary

Craft Anything 0.3.0 was engaged to create a desktop interface for `pop-linux`. During this process, Craft Anything misclassified the repository as `Rust + macroquad`, invoked Ghidra binary analysis, and repeatedly attempted to steer the project toward an unrelated 2D mini-game ("Signal Collector").

Despite the tool's classification failures, the underlying AI engineer created a genuine, high-quality Python/PySide6 desktop research workspace under `pop_linux/gui/`, native packaging automation under `packaging/`, integration tests under `tests/`, and documentation under `docs/`. However, it also generated substantial scaffolding, game code, and internal verification state to satisfy Craft Anything's automated checks.

Before remediation, a complete filesystem backup was created outside the repository at:
`/home/meer/Projects/pop-linux-backup-20261105-2136`

This manifest documents the classification, disposition, and rationale for every file in the repository.

---

## 1. Retained and Maintained Files (Genuine Application)

### Essential Application & Engine (`pop_linux/`)
- `pop_linux/__init__.py`: Package metadata, version bumped to `0.2.0`.
- `pop_linux/cli.py`: Preserved original Typer/Rich CLI interface, options, and commands.
- `pop_linux/config.py`: Configuration and credential management. Enhanced with `application_directory()` supporting native paths on Windows (`%APPDATA%/pop_linux`) and macOS (`~/Library/Application Support/pop_linux`), while preserving Linux `~/.config/pop_linux` compatibility.
- `pop_linux/execution.py`: Execution engine providing `execute_request_async` and `execute_request` facades, provider dispatch, paper deduplication, and `ExecutionEnvelope` assembly.
- `pop_linux/execution_models.py`: Pydantic wire models for requests, envelopes, and execution messages.
- `pop_linux/models.py`: Core domain models (`Paper`, `Author`, `Metrics`, `QueryResult`).
- `pop_linux/providers/`: Provider implementations for OpenAlex, Semantic Scholar, CrossRef, PubMed, and Google Scholar.
- `pop_linux/providers/capabilities.py`: Provider capability registry, enhanced with `profile_filter_modes`.
- `pop_linux/providers/google_scholar.py`: Enhanced with `_fetch_query` and profile dispatch in `_fetch_native`.
- `pop_linux/utils/`: Identity matching, deduplication, metrics calculations, history persistence (SQLite v2), and exporters (BibTeX, CSV, JSON, RIS).

### Desktop GUI (`pop_linux/gui/`)
- `pop_linux/gui/__init__.py`: GUI package initialization.
- `pop_linux/gui/__main__.py`: Desktop entry point supporting `--screenshot`, `--self-test`, and `--isolated` modes.
- `pop_linux/gui/dialogs.py`: Settings dialog with password masking, about dialog, and snapshot comparison dialog.
- `pop_linux/gui/service.py`: Bridge between GUI presentation and execution engine, request construction, URL validation, and export helpers.
- `pop_linux/gui/smoke.py`: Automated offline self-test runner verifying search, table, storage, metrics, and screenshot capture.
- `pop_linux/gui/style.py`: Fusion styling, light/dark appearance palettes, and layout helpers.
- `pop_linux/gui/table.py`: Publication table model and proxy supporting sorting, local filtering, and selection.
- `pop_linux/gui/window.py`: Main research workspace window, search panel, publication details, bibliometric summary cards, and history management.
- `pop_linux/gui/resources/pop-linux.svg`: High-resolution vector application icon.

### Automated Tests (`tests/`)
- `tests/test_capabilities.py`: Provider capability registry tests.
- `tests/test_cli.py`, `tests/test_cli_safety.py`: CLI command and safety tests.
- `tests/test_config.py`: Configuration loading, saving, and backup tests.
- `tests/test_deduplicator.py`: DOI and fuzzy title deduplication tests.
- `tests/test_desktop_engine.py`: Engine async execution, cancellation, and path resolution tests.
- `tests/test_execution.py`, `tests/test_execution_characterization.py`, `tests/test_execution_models.py`: Execution engine and envelope tests.
- `tests/test_exporter.py`: Export formatting tests.
- `tests/test_fetch_contract.py`: Provider fetch contract tests.
- `tests/test_google_scholar.py`: Google Scholar provider tests.
- `tests/test_gui.py`: Offscreen PySide6 GUI integration tests exercising research workflows, table sorting/filtering, worker cancellation, and window closure.
- `tests/test_history.py`, `tests/test_history_v2.py`: SQLite persistence, schema migration, and snapshot diff tests.
- `tests/test_identity.py`: Canonical paper identity tests.
- `tests/test_machine_profile.py`: Machine-readable execution tests.
- `tests/test_metrics.py`, `tests/test_metrics_context.py`: Harzing bibliometric algorithm tests.
- `tests/test_models.py`: Pydantic domain model tests.
- `tests/test_pagination_filters.py`: Provider pagination and filtering tests.
- `tests/test_provenance.py`: Source observation and provenance tests.
- `tests/test_providers.py`: Provider registry tests.
- `tests/test_rerun_diff.py`: Snapshot rerun and trajectory comparison tests.

### Packaging & Distribution (`packaging/`)
- `packaging/build_desktop.py`: Standalone cross-platform build script using PyInstaller, icon generation, license collection, and frozen executable smoke verification.
- `packaging/desktop.spec`: PyInstaller specification bundling `pop_linux` with PySide6, Playwright assets, and application metadata.
- `packaging/desktop_entry.py`: Frozen application entry point.
- `packaging/linux_packages.py`: Linux packaging generator producing AppImage (via verified `appimagetool`), Debian `.deb` (via `dpkg-deb`), and Red Hat `.rpm` (via `rpmbuild`).
- `packaging/pop-linux.desktop`: XDG desktop entry specification.
- `packaging/requirements-desktop.txt`: Pinned build and test dependency manifest.
- `packaging/verify_release.py`: Independent release asset validator verifying platform packages, signatures, and frozen startup logs.
- `packaging/THIRD_PARTY_NOTICES.md`: Third-party license documentation.
- `packaging/licenses/pyside6/`: Exact Qt for Python license notices (LGPL-3.0, GPL-2.0, GPL-3.0).

### CI/CD Workflow (`.github/`)
- `.github/workflows/desktop.yml`: Multi-platform matrix build (Linux, Windows, macOS) verifying linting, security, tests, packaging, and draft release publication.

### Documentation (`docs/`)
- `docs/desktop.md`: Desktop user guide.
- `docs/desktop-audit.md`: Architectural inventory and baseline audit.
- `docs/desktop-verification.md`: Initial verification notes.
- `docs/release-0.2.0.md`: Release candidate notes and distribution guide.
- `docs/desktop-final-verification.md`: Comprehensive final verification report.
- `docs/craft-recovery-manifest.md`: This document.

---

## 2. Modified Files

- `README.md`: Stripped Craft Anything game notices; updated with desktop documentation, installation guide, and preserved CLI instructions.
- `pyproject.toml`: Modernized packaging metadata, added `pop-linux-gui` script entry point, and declared `desktop`, `desktop-test`, and `desktop-build` dependency groups.
- `pop_linux/__init__.py`: Version updated to `0.2.0`.
- `pop_linux/config.py`: Added platform-aware application directory logic.
- `pop_linux/execution.py`: Added async execution facade and multi-provider coordination.
- `pop_linux/providers/capabilities.py`: Added profile filter modes.
- `pop_linux/providers/google_scholar.py`: Added query/profile split.

---

## 3. Excluded and Quarantined Craft Anything Contamination

The following files and directories were generated solely to satisfy Craft Anything's game checker or record its internal state. They have no relationship to the scholarly research application and are excluded from the clean codebase (while preserved in the external backup):

| Path | Category | Evidence & Rationale | Action |
|---|---|---|---|
| `app/game.py` | Game code | Implemented a 2D mini-game ("Signal Collector") with HUD and player movement. Unrelated to academic research. | Excluded / Removed |
| `app/build.py` | Game wrapper | Hijacked `pop-linux-gui` to launch `game.py` unless passed `--research`. | Excluded / Removed |
| `app/MECHANICS.md` | Game docs | Documented game rules, player speed, and signal scoring. | Excluded / Removed |
| `app/CREDITS.md` | Game docs | Attributed game drawing routines. | Excluded / Removed |
| `app/package.json` | Game wrapper | Invoked `npm run build` for game bundling. | Excluded / Removed |
| `app/test_build.py` | Game tests | Tested game movement, HUD scoring, and signal collection. | Excluded / Removed |
| `app/CONFIGURATION_AUDIT.md` | Craft state | Internal audit of Craft build mechanics. | Excluded / Removed |
| `app/README.md` | Game docs | Private game build notice. | Excluded / Removed |
| `app/dist/` | Game build | Compiled game artifacts. | Excluded / Removed |
| `craft.json` | Craft state | Tool configuration and initial prompt. | Excluded / Removed |
| `mechanics.json` | Craft state | Game mechanics specification. | Excluded / Removed |
| `package.json` | Craft state | Top-level npm script delegating to `app/`. | Excluded / Removed |
| `feed.json` | Craft state | Event feed for Craft Anything monitor. | Excluded / Removed |
| `usage.json` | Craft state | Token usage and work time statistics. | Excluded / Removed |
| `checks/` | Craft state | Screenshots and JSON test reports from rounds 0–12 of game checks. | Excluded / Removed |
| `capture/` | Craft state | Browser / window capture notes from Craft Anything. | Excluded / Removed |
| `investigation.cany/` | Craft state | Evidence ledger and findings from Craft Anything run. | Excluded / Removed |
| `pinned/` | Craft state | Log of test play session (`play.log`). | Excluded / Removed |
| `build-activity.log` | Craft state | Complete execution log of Craft Anything. | Excluded / Removed |
| `CREDITS.md` | Game docs | Root duplicate of game attribution. | Excluded / Removed |
| `Build/` | Temporary build | Extracted zipapp and runtime built by `app/build.py`. | Excluded / Removed |
| `build_wheels/` | Temporary build | Temporary wheel directory. | Excluded / Removed |

---

## 4. Preservation of User Data

- Linux configuration file (`~/.config/pop_linux/config.toml`) and search history database (`~/.config/pop_linux/history.sqlite3`) remain strictly in place and were never touched or modified during testing.
- All automated tests were redirected to temporary directories (`tmp_path`) using pytest fixtures and monkeypatching.
- The external backup `/home/meer/Projects/pop-linux-backup-20261105-2136` contains an exact, untouched mirror of all original files, including all Craft Anything state, prior to any cleanup.
