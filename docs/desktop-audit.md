# Desktop audit and implementation plan

Baseline: source revision `9b7898d`, branch `main`, version 0.1.0, Python >=3.11.
236 tests passed in 1.45s. Ruff passed. Bandit: two pre-existing low severity
`except: pass` findings in `utils/cookie_bridge.py`. No release workflows or tags.
Untracked Craft Anything records are unrelated and must be preserved.

## Architecture and functional inventory

Typer/Rich CLI -> SearchRequest -> execution engine -> async HTTPX providers ->
Paper/ExecutionEnvelope -> metrics, identity/dedup, SQLite v2 history, exporters.
Pydantic supplies validation and wire contracts. BeautifulSoup parses Scholar;
Playwright provides a user-operated browser challenge workflow. TOML config stores
credentials with best-effort POSIX permissions. License: PolyForm Noncommercial
1.0.0; this is not an OSI open-source license.

| CLI | Desktop presentation | Existing implementation reused |
| --- | --- | --- |
| search | Search form, result table, details | execution, capabilities, models |
| metrics | Dataset-scoped cards | utils/metrics.py |
| history / rerun | Snapshot workspace | utils/history.py |
| diff | Ordered comparison dialog | compute_snapshot_diff |
| merge | Open JSON datasets | deduplicate_papers, calculate_metrics |
| config | Password-masked settings | load_config, save_config |
| capabilities / providers | Provider help | CAPABILITIES |
| --export | Native save dialog, all/selected | export_data |

Confirmed by existing tests: CLI, validation, status aggregation, provider fetch
contracts, bounded pagination, secret redaction, export sanitization, identity,
metrics, history migrations/backups, reruns/diffs, provenance. Remote service
availability and interactive browser startup were not tested by the baseline.
Some comments in AGENTS/execution still describe earlier architecture; executable
code already uses fetch, paginated APIs, identity-based diff and history v2.
Capability registry pagination flags currently disagree with actual REST adapters;
do not promise pagination from these flags in UI help.

## Event loop and portability risks

The synchronous engine calls asyncio.run. A Qt worker needs an additive async
entry point; the existing synchronous API must remain unchanged. Async task
cancellation must propagate through HTTPX and gather. Never terminate QThreads.
Single active operation plus a generation token prevents stale responses.

Linux state stays at ~/.config/pop_linux. New Windows state uses APPDATA and
macOS uses Library/Application Support. No automatic Linux migration. Existing
SQLite migration/backup behavior is retained. Qt preferences hold presentation
settings only. Config credentials remain plaintext at rest under the existing
contract; masking is not encryption. Scholar's default browser user agent is
Linux-specific, and browser cache/launch behavior needs native-platform testing.
The existing browser bridge has no safe explicit browser-completion handshake;
desktop Scholar search must be an informed, user-initiated action, never machine
mode. Chromium is a separately installed optional runtime.

## Implementation and acceptance

1. Add optional PySide6 presentation package and GUI entry point; retain CLI.
2. Add compatible async engine facade, cancellable worker, sortable proxy table,
   details/provenance, existing metric cards and native exports.
3. Connect existing history, comparisons, merge and masked settings. Preserve
   schemas and formulas. Do not synthesize legacy request/filter metadata.
4. Add native-runner packaging gates, startup artifacts and draft release flow.

High-value scenarios: valid partial multi-provider result remains inspectable,
sortable/exportable/saveable; invalid filters, cancelled requests, stale signals,
failed storage and close-during-search cannot corrupt or replace results.
No new runtime backend, CLI subprocess, formula, identity policy or DB schema.

## Environment blockers

The project venv initially lacks Qt; the system installation provides PySide6/Qt
6.11.2. Using the venv's existing dependencies plus that system Qt, all 240 tests
pass, including two real Qt integration tests. A five-step offline desktop probe
passes and captures the rendered workspace; light/dark/empty screenshots are
generated. The source wheel builds and its manifest is checked for stale build
trees, test files and both entry points. This does not establish frozen startup.

Default-display Qt initialization exits 134 in this environment, including a
minimal QApplication with no application code; offscreen Qt works. Display-server
access remains a local limitation. Interactive/HiDPI behavior needs a real desktop.

PyInstaller is absent. pip fails DNS resolution; Craft Anything's installation
tool requires approval unavailable under this session's policy. Git branch
creation cannot write .git refs. gh authentication reports invalid credentials.
Windows/macOS runners are unavailable locally. Native artifacts, CI status, PR
and release publication therefore remain acceptance blockers. The baseline venv
also contains Rich 15 despite the declared <15 constraint; CI's pinned graph
still needs resolver/native verification. No constraints are weakened to hide it.
