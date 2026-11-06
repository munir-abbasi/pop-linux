# Desktop workspace

The desktop is an optional presentation layer for the existing Python package.
It is implemented for 0.2.0; the Linux source GUI is tested with offscreen Qt
6.11.2 (240 passing tests). Frozen packages and other platforms are unverified.
See [audit and blockers](desktop-audit.md) and [release candidate notes](release-0.2.0.md).

## Run from source

On a machine with Python 3.11+ and package network access:

```bash
python -m pip install '.[desktop]'
pop-linux-gui
# Equivalent module entry:
python -m pop_linux.gui
# The original CLI remains available:
pop-linux --help
```

Choose a provider or all non-interactive providers, enter a query and optional
filters, then search. Provider help shows the registry's enforcement modes:
native filters, query hints, post-filters and unsupported filters differ. A result
limit applies per provider, so combined results may exceed that number. Progress
has no fabricated percentage. Cancel requests cancellation of ongoing async work.

Sort column headings, use the local row filter, or hide/resize columns. These
actions leave underlying records and metrics unchanged. Select rows for details,
copy or DOI/URL opening. Double-click a row for a larger details dialog. Export
offers selected records or all loaded records, including rows hidden by the local
filter. Formats and spreadsheet/formula sanitization use existing exporters.

Metrics always describe the loaded dataset. Provider reports disclose individual
failures and filter limitations. The cards do not imply complete author coverage.
Tooltip explanations describe the existing formulas without changing them.

Save snapshot explicitly to retain a desktop result. Search history displays the
most recent 1,000 snapshots. Open a snapshot without network access, rerun its
recorded request, or select two for citation/metric changes (earlier ID is the
baseline). Legacy snapshots open but cannot reproduce unknown filters. File →
Open / merge JSON datasets reuses existing QueryResult validation and deduplication.

Settings store defaults, API keys, contact email, Scholar timeout, appearance and
export folder. Keys are masked, not encrypted. Existing config is backed up before
a settings save. Configuration/history/cookie locations are shown read-only.
Linux retains ~/.config/pop_linux; Windows uses APPDATA/pop_linux and macOS uses
~/Library/Application Support/pop_linux. Qt preferences contain layout/appearance,
not API keys. No research database relocation is performed.

Scholar requires confirmation before a user-initiated search can open a browser.
It is excluded from all-provider searches and never routed through CLI machine
mode. Browser availability, challenges and access restrictions may prevent results.
No automatic CAPTCHA solving or browser download is added. Its legacy profile
API lacks fetched/request counts, so the adapter emits an explicit warning.

Keyboard shortcuts: Ctrl+O open/merge, Ctrl+E export, Ctrl+S snapshot,
Ctrl+F local filter, Ctrl+Shift+C copy selected metadata, Ctrl+, settings,
Ctrl+Q quit. Widget labels and normal Qt keyboard focus/navigation are retained.

## Test and build

```bash
python -m pip install -r packaging/requirements-desktop.txt
python -m pip install --no-build-isolation --no-deps -e .
python -m pip check
python -m pytest -q
python -m ruff check pop_linux tests packaging
python -m ruff check --select C901 pop_linux/gui packaging
python -m bandit -r pop_linux -ll
python -m pop_linux.gui --isolated --self-test build/startup.json --screenshot build/workspace.png
python packaging/build_desktop.py
```

Use `QT_QPA_PLATFORM=offscreen` for source tests in a displayless Linux shell.
Run packaged startup under a real display or Xvfb to exercise its platform plugin.
The offline probe substitutes only the provider boundary and exercises the real
worker, engine, table, metric display, export and temporary SQLite history. It
returns a nonzero exit on any failed step and records measured JSON and a Qt
screenshot. `--isolated` keeps personal configuration/history untouched. The
`--screenshot file.png` option captures the normal empty workspace after two
seconds and exits; it is not a screenshot of a live provider search.

Native packaging needs PyInstaller, the desktop extra and OS packaging tools.
Linux also needs dpkg-deb, rpm/rpmbuild, cpio and a working graphical display.
AppImage tooling is downloaded only with verified GitHub asset SHA-256 digests;
missing digests fail the build. macOS uses the native iconutil/ditto tools.
Run the build on each target OS/architecture. Native build outputs have not yet
been generated in this checkout.

## Release workflow

The Desktop verification and release workflow builds the exact resolved source
SHA on Ubuntu 22.04, Windows 2022, Intel macOS 15 and Apple Silicon macOS 15.
It installs controlled dependencies, runs regression and Qt tests, builds native
packages, starts the frozen apps and retains evidence. Source GUI tests must not
skip in CI: the explicit GUI-only pytest invocation fails if nothing runs.
The release validator requires all four architectures' packages, expected binary
contents, passing smoke JSON, matching source/version and SHA-256 checksums.

1. Review this diff on a dedicated branch and create a PR. This environment's
   read-only .git prevented that step; no commit/PR was created here.
2. Restore GitHub authentication and configure the `desktop-release` environment
   with required reviewers. Enable Actions and its release write permission.
3. Run workflow_dispatch for the approved revision with publish disabled. Fix
   every failing native check; inspect screenshots, notices and provider workflows.
4. Resolve licensing/source distribution, optional signing and manual accessibility,
   HiDPI and Scholar checks. Signing/notarization are not claimed by this workflow.
5. Tag the approved version or dispatch with publish enabled. After all builds
   and validation pass, the workflow creates a **draft** with actual assets and
   source/workflow links; existing releases are never overwritten.
6. Review the draft, correct platform claims to match evidence, then publish it
   through GitHub. A draft is not the requested public release acceptance state.

The workflow is prepared source, not evidence that CI has run or succeeded.
PyInstaller requires native OS builds ([official manual](https://pyinstaller.org/en/latest/)).
Qt obligations are described by [Qt licensing](https://doc.qt.io/qt-6/licensing.html).
Runner labels follow [GitHub's runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).

## Local evidence

The existing virtual environment excludes system packages. Local Qt verification
uses its normal dependencies and appends the preinstalled system Qt directory:

```bash
QT_QPA_PLATFORM=offscreen venv/bin/python -c "import sys; sys.path.append('/usr/lib/python3.14/site-packages'); import pytest; raise SystemExit(pytest.main(['-q', '--basetemp=build/desktop-evidence', '--junitxml=build/desktop-tests.xml']))"
```

That path is specific to this host and is not required by a normal desktop-extra
installation or a native package. QtTest supplies GUI interaction; pytest-qt is
not required. The venv-only test run reports 238 passed and one explicitly skipped
Qt module. With system Qt available the full suite reports 240 passed.
Screenshot evidence and offline startup JSON are under the ignored build folder.
