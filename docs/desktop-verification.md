# Desktop delivery and verification

```text
DOMAIN: General_Engineering
PROTOCOL_ACTIVE: TRUE
SECURITY_SCAN: Redacted
STEP_GATE: FAIL

SCOPE: Extend the existing scientific Python CLI into a desktop application,
       preserve its contracts/data, and prepare verified native releases.
CHANGES: Optional Qt workspace, compatible async engine facade, profile adapter,
         platform state paths, deterministic GUI integration, native build gates.
FILES: Exact paths are enumerated under Changed files below.
VALIDATION: Source quality and Linux offscreen runtime pass; native distribution
            and public-release acceptance remain blocked.
RISK: No verified native packages, default-display startup, Windows/macOS startup,
      interactive Scholar lifecycle, signing/notarization or public release.
```

This is a tested source candidate, **not a completed cross-platform release**.
The source baseline is `9b7898d`; changes remain uncommitted because `.git` is
read-only. No branch, commit, PR, CI run or release URL was created.

## Implemented components

- The original CLI is retained. GUI entry points are `pop-linux-gui` and
  `python -m pop_linux.gui`. Qt remains optional for CLI installations.
- The desktop uses the existing engine, normalized models, deduplication,
  bibliometrics, history and exporters. No HTTP backend or CLI subprocess is used.
- Search forms use the capability registry, including separate profile-filter
  semantics. Indeterminate background search supports cancellation, stale-result
  suppression, partial results, provider errors and orderly worker closure.
- Results support real numeric/text sorting, local filtering, column visibility,
  row selection, metadata copying, safe web links, details and provenance.
- All 12 existing metrics are displayed with dataset scope and explanations.
  Missing JSON metrics are computed rather than shown as fabricated zeroes.
- History supports explicit snapshots, reopening, recorded filters, reruns and
  comparisons; the existing SQLite migration/backup implementation is unchanged.
- Exports reuse CSV/JSON/BibTeX/RIS implementations with explicit record scope.
  Adding a filename extension cannot silently overwrite another existing export.
- Settings mask API keys, back up TOML before saving, and retain unknown config
  values. Appearance, window geometry and panel/column state use Qt preferences.
- Linux state paths are unchanged; new Windows/macOS installations use native
  directories. The project license is unchanged. The icon is newly authored.

## Verified evidence

| Check | Observed result | Artifact |
| --- | --- | --- |
| Original suite | 236 passed in 1.45s | Baseline command output; audit |
| Final full suite with system Qt | **240 passed in 3.89s**, no failures/errors/skips | `build/desktop-tests.xml` |
| CLI-only venv run | 238 passed, one Qt module explicitly skipped | Command output |
| GUI integration flows | Included in full suite: search/partial results/table/details/export/history/settings/import and invalid/error/empty/cancel/close behavior | `build/desktop-evidence/test_research_flow_uses_engine0/research-workspace.png` and lifecycle JSON in the second flow's artifact directory |
| CLI/desktop equivalence | Real Typer machine command and async engine produce equal papers/metrics with deterministic provider fixture | `tests/test_desktop_engine.py` |
| Offline source startup | Five measured steps passed | `build/desktop-startup.json`, `build/desktop-workspace.png` |
| Extracted Python wheel startup | Five measured steps passed, using the extracted wheel rather than source checkout | `build/wheel-startup.json`, `build/wheel-workspace.png` |
| Light/dark/empty rendering | PNGs produced and inspected; normal empty screenshot option exits successfully | `build/desktop-dark.png`, `build/desktop-empty.png` |
| Ruff | Pass on application, tests and packaging | Command output |
| Complexity | Pass at default threshold 10 for all changed Python surfaces, including Scholar profile/query dispatch | Command output; same gate in workflow |
| Compile | Python modules and PyInstaller spec compile | Command output |
| Security | No medium/high Bandit findings in application or packaging | `bandit -r pop_linux packaging -ll` exits 0 |
| Existing application Bandit findings | Two unchanged low-severity B110 findings at cookie_bridge.py:63 and :92 | `build/desktop-bandit.json` |
| CLI help | Exit 0 | `build/desktop-cli-help.txt` |
| Workflow | YAML parses; four native runner entries present | Static check only; no CI success claim |
| Diff whitespace | Pass | `git diff --check` |

The tests use temporary configuration, Qt preferences and SQLite files. Network
providers are replaced at their fetch boundary; the engine and storage run for
real. No live-provider success is inferred from these checks. New defects were
reproduced before fixing missing import metrics, malformed publication URLs and
extension-induced export overwrites. Scholar profile dispatch/filter behavior
also has a failing-before-fix regression scenario.

## Artifact produced

`build/desktop-wheels-clean/pop_linux-0.2.0-py3-none-any.whl`

SHA-256:

```text
03f3a88dc15426eac32c99acafba6424687d742d79784dfd4da0f5588d391739
```

This is a **Python wheel requiring Python/dependencies**, not an independently
installable native application. Its 36 archive members were checked: package
source bytes match the checkout, the icon and both entry points are present,
the project license is preserved, and no build/test/capture/venv trees are
included. Full manifest evidence is in `build/wheel-verification.json` and the
build log is `build/desktop-wheel-build.log`. An initial wheel contaminated by
pre-existing build outputs was rejected and quarantined under `.review_backup`;
the accepted wheel uses a separate build directory. A later stale candidate was
also rejected by the source-byte check and rebuilt before final startup testing.

## Blocked or not tested

- Default-display startup fails locally with exit 134, also for a minimal
  QApplication without project code. Offscreen Qt works. Interactive desktop,
  system font/HiDPI, accessibility and actual window-manager integration remain
  verification work on a usable display.
- No Windows/macOS/Linux frozen executable, AppImage, .deb or .rpm is produced.
  PyInstaller is absent; pip DNS resolution fails. Craft Anything's installation
  tool returns “requires approval, but approval policy is never.” System Qt
  provided a safe local source-test path, but does not provide a packaging tool.
- Native workflows, archives, installation, provider network access and Scholar
  Chromium launch/session cleanup have not run on native platforms. DNS/browser
  shutdown can outlast coroutine cancellation and needs live testing.
- Git ref writes are denied and `gh auth status` reports invalid authentication.
  No GitHub repository writes, tags, PR or release are claimed. The workflow
  creates drafts only after all native gates pass; publishing remains an owner
  action after platform/licensing review.
- No signing/notarization is performed. API keys/cookies retain plaintext file
  storage under existing permissions; OS keychain migration is not implemented.
- The native dependency graph is directly pinned but not fully hash locked.
  AppImage runtime/tool digests and resolved package versions are recorded by
  the prepared build; that build has not run here.
- Craft Anything `rebuild_check` reports “No project to build found in the project
  folder yet” for this Python project. No game/framework replacement or records
  edits were made to force its checker to pass.

```text
UNSPECIFIED: Cannot verify bug-free completion in this environment
```

## Changed files

```text
README.md
pyproject.toml
pop_linux/__init__.py
pop_linux/config.py
pop_linux/execution.py
pop_linux/providers/capabilities.py
pop_linux/providers/google_scholar.py
pop_linux/gui/__init__.py
pop_linux/gui/__main__.py
pop_linux/gui/dialogs.py
pop_linux/gui/service.py
pop_linux/gui/smoke.py
pop_linux/gui/style.py
pop_linux/gui/table.py
pop_linux/gui/window.py
pop_linux/gui/worker.py
pop_linux/gui/resources/pop-linux.svg
tests/test_desktop_engine.py
tests/test_gui.py
packaging/desktop_entry.py
packaging/desktop.spec
packaging/build_desktop.py
packaging/linux_packages.py
packaging/verify_release.py
packaging/requirements-desktop.txt
packaging/pop-linux.desktop
packaging/THIRD_PARTY_NOTICES.md
.github/workflows/desktop.yml
docs/desktop-audit.md
docs/desktop.md
docs/release-0.2.0.md
docs/desktop-verification.md
AGENTS.md (ignored local routing/invariants)
design_specification.md (ignored local architecture)
implementation_plan.md (ignored local remaining acceptance work)
```

Generated build evidence and reversible backups stay in ignored build/backup
directories. Existing Craft Anything records, capture/reference files and
unrelated working-tree entries were not edited directly.

## Launch and next actions

Follow [the desktop guide](desktop.md) for source installation, launch, tests and
native builds. [Release notes](release-0.2.0.md) enumerate intended formats and
limitations. Restore native build/network/GitHub access, review a dedicated
branch/PR, run the prepared workflow at the approved revision, inspect every
platform's startup evidence, complete redistribution/signing decisions, and
publish only the resulting verified assets. Those actions are still required
to satisfy the original release acceptance criteria.
