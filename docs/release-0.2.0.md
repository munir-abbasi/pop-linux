# Perish or Publish 0.2.0 — desktop release candidate

Adds an optional Python/PySide6 research workspace while retaining the existing
CLI and `pop-linux.execution/v1` contract. The desktop calls the same engine,
metrics, identity service, SQLite repository and exporters as the CLI.

Features in the desktop implementation: provider-aware search forms, a sortable
publication table with local filtering, publication details and provenance,
dataset-scoped metric cards, CSV/JSON/BibTeX/RIS exports with explicit selection
scope, saved snapshots, request reruns, citation/metric comparison, JSON dataset
merging, masked provider settings, light/dark appearance and remembered layout.
Searches use a cancellable Qt worker; progress is indeterminate.

## Intended packages (availability requires successful native build evidence)

| Platform | Architecture | Package |
| --- | --- | --- |
| Windows | x64 | Portable ZIP; extract the entire folder, launch PerishOrPublish.exe |
| macOS | Intel x86_64 | ZIP containing PerishOrPublish.app |
| macOS | Apple Silicon arm64 | Separate ZIP containing PerishOrPublish.app |
| Linux | x86_64 | AppImage, portable tar.gz, .deb and .rpm |

Linux builds use Ubuntu 22.04 and need glibc >=2.35 plus desktop graphics
libraries. Fedora compatibility must be demonstrated by its package smoke test.
Native-runner startup checks are necessary; a successful build is insufficient.
Do not describe the above as supported platforms until those checks pass.

## Installation and verification

Use the package matching your architecture. Check its SHA-256 hash against
`SHA256SUMS` before launching. Keep the complete extracted directory: the
executable depends on its bundled shared libraries. Python and pip are not
needed for native packages. For an AppImage, grant executable permission using
your file manager and open it; extraction mode is available where FUSE is absent.
Install .deb/.rpm through your distribution's package manager so dependencies
are resolved. macOS ZIPs contain a complete application bundle.

Every claimed native release must include its startup JSON, rendered screenshot,
source commit, workflow URL and installed dependency inventory. Those files
are build evidence, not evidence of live provider availability.

## Limitations and distribution status

- The Linux source GUI passes its offline startup probe and all 240 regression/
  Qt tests using system PySide6/Qt 6.11.2. Light/dark/empty screenshots are
  captured. Default-display Qt initialization fails in this restricted environment
  (also for a minimal Qt-only process); interactive desktop startup is unverified.
  A Python source wheel is built; no frozen native package is built or started.
  PyInstaller cannot be installed because package network access is unavailable.
  The draft release owner must replace this status with actual native CI results.
- No public GitHub Release or native artifact has been produced locally.
- Native packages are unsigned unless independently signed; no notarization is
  implemented. Windows/macOS may show operating-system security warnings.
- Chromium is not bundled. Scholar is user-initiated, can require a browser,
  is subject to access restrictions, and is not a machine-mode operation.
  Packaged Scholar browser launch/session storage remains untested on all OSes.
  Optional browser installation must use the Playwright version in the build's
  dependency inventory; installing a different version may not supply the
  browser revision the package needs.
- Keys/cookies use the existing files and are not encrypted at rest. API keys
  are masked in settings and redacted in provider diagnostics. No OS keychain
  migration is implemented.
- Linux data stays at ~/.config/pop_linux. New Windows/macOS installs use
  native directories. No existing Linux files are moved or overwritten.
- History retains the v2 schema and existing migration backups. Legacy snapshots
  cannot be rerun because original request/filter data was never stored.
  Snapshot tables omit some metadata such as abstracts; recorded provenance can
  provide the abstract where available.
- Desktop snapshots are explicitly saved with Save snapshot. Opening history
  can invoke the existing recoverable schema migration. Research data location
  changes are deliberately unavailable; export folders are configurable.
- Cancellation stops async provider tasks. Operating-system DNS resolution and
  browser cleanup can delay thread shutdown; those live cancellation paths need
  platform testing. No thread is forcibly terminated.
- Search datasets can be limited or partial. Metrics are not a complete author
  assessment. PubMed has no citation counts; merged counts use maximum observed
  provider values. Existing bibliometric formulas remain unchanged.
- Direct build dependencies are pinned; transitive dependencies and the Linux
  AppImage runtime are recorded with versions/digests at build time. Builds are
  not asserted to be bit-for-bit reproducible or a fully hash-locked supply chain.

The project's PolyForm Noncommercial License 1.0.0 is preserved. Qt/PySide6 and
other dependencies have separate redistribution obligations; see bundled
THIRD_PARTY_NOTICES. The owner must complete that review and provide required
corresponding source/offers before publishing the draft. No official affiliation
with Harzing's Publish or Perish is implied.
