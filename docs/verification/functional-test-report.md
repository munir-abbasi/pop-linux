# Functional Test Report: CLI–GUI Equivalence & Edge Cases

## Test Execution Summary
- **Test Date**: 2026-11-06
- **Test Environment**: Linux x86_64, Python 3.12.16, PySide6 6.11.2, Qt 6.11.2 (offscreen and Wayland/X11)
- **Harness Script**: `packaging/verify_parity_independent.py`
- **Total Functional Checks**: 14
- **Passed**: 14 (100%)
- **Failed**: 0 (0%)
- **Skipped**: 0 (0%)

---

## 1. Deterministic Search & Filtering Equivalence

### Test Case 1.1: Multi-Attribute Filter Query
- **Query**: `"quantum computing"`
- **Provider**: `openalex`
- **Filters**: `year_from=2020`, `limit=10`, `min_citations=3`
- **Fixtures**: 3 papers with citations `[42, 18, 9]`.
- **CLI Output**:
  - Returned Papers: 3
  - Metrics: $h$-index: 3, Total Citations: 69
- **GUI Output**:
  - `MainWindow.table` Row Count: 3
  - `MainWindow.metric_values["h_index"]`: `"3"`
  - `MainWindow.metric_values["total_citations"]`: `"69"`
- **Parity Verdict**: **PASS** (100% data and metric equality).

### Test Case 1.2: Multi-Provider Search with Partial Failure
- **Providers**: `openalex` (returns 2 papers), `crossref` (simulated HTTP 500 / network failure).
- **CLI Output**:
  - Status: `partial`
  - Warning: CrossRef error logged without aborting.
  - Papers: 2 papers returned.
- **GUI Output**:
  - `MainWindow.notice`: `"Partial results — inspect Provider reports for limitations. 2 publications..."`
  - `MainWindow.diagnostics`: Contains CrossRef error code and message.
  - `MainWindow.table`: Displays the 2 successful papers from OpenAlex.
- **Parity Verdict**: **PASS** (Fault isolation identical; partial success retained).

---

## 2. Table Sorting & Local Filtering Invariants

### Test Case 2.1: Numeric vs Lexicographic Sorting
- **Objective**: Ensure that sorting by Citation Count or Year orders numerically (`9 < 18 < 42 < 100`), rather than alphabetically (`"100" < "18" < "42" < "9"`).
- **Execution**:
  - Column 4 (`citations`) sorted Ascending via `proxy.sort(4, AscendingOrder)`.
  - Values extracted: `row[0]=9`, `row[1]=25`, `row[2]=100`.
  - Column 4 sorted Descending: `row[0]=100`, `row[1]=25`, `row[2]=9`.
  - Column 2 (`year`) sorted Ascending: `row[0]=2020`, `row[2]=2024`.
- **Parity Verdict**: **PASS** (Strict numeric order enforced via `Qt.ItemDataRole.UserRole`).

### Test Case 2.2: Local Filtering Invariant
- **Objective**: Ensure typing in `MainWindow.local_filter` hides non-matching table rows without altering the underlying dataset or recomputing metrics over the truncated subset.
- **Initial Dataset**: 2 papers, Total Citations: 80, $h$-index: 2.
- **Filter Applied**: `"Neural"` (matches 1 paper).
- **Observed State**:
  - Table Visible Rows: 1
  - Underlying Dataset Size: `len(window.result.papers) == 2`
  - Metrics Cards: $h$-index remains 2, Total Citations remains 80.
- **Parity Verdict**: **PASS** (Underlying dataset and dataset-wide metrics remain pristine).

---

## 3. Data Export Fidelity & Scope Selection

### Test Case 3.1: Full Dataset Export
- **Formats Tested**: CSV, JSON, BibTeX, RIS.
- **Verification Method**: Export files generated and verified via independent parsers (`csv.reader`, `json.loads`, regex parser for BibTeX and RIS).
- **Findings**:
  - CSV contains 3 rows (1 header + 2 papers). Formula characters (`=`, `+`, `-`, `@`) neutralized.
  - JSON parses into valid `QueryResult` matching schema.
  - BibTeX produces valid `@article` entries with curly-brace author and title protection.
  - RIS produces valid `TY  - JOUR`, `TI  - ...`, `ER  - ` records.
- **Parity Verdict**: **PASS**.

### Test Case 3.2: Selected-Only Export Scope
- **Objective**: When user selects 1 row in the table and chooses "Selected records", only that record is exported, and metrics are dynamically recomputed for that explicit subset.
- **Input**: 1 selected paper (10 citations).
- **Output JSON**:
  - `total_found`: 1
  - `papers`: 1
  - `metrics.total_citations`: 10
  - `metrics.h_index`: 1
- **Parity Verdict**: **PASS** (Explicit scope selection verified).

---

## 4. History, Snapshot Rerun & Citation Diffing

### Test Case 4.1: SQLite Snapshot Creation & Retrieval
- **Snapshot 1**: Saved with 1 paper (10 citations). ID returned: `#1`.
- **Snapshot 2**: Saved with 2 papers (Alpha: 15 citations, Beta: 5 citations). ID returned: `#2`.
- **Retrieval**: `history.list_snapshots()` correctly lists both snapshots with timestamp, query, provider, and paper count.
- **Parity Verdict**: **PASS**.

### Test Case 4.2: Snapshot Diffing
- **Diff Executed**: Snapshot #1 $\rightarrow$ Snapshot #2.
- **Expected**:
  - Citation growth delta: $+10$ (20 total - 10 total).
  - Paper Alpha citation delta: $+5$ ($15 - 10$).
  - Newly discovered papers: `['Paper Beta']`.
- **Observed**:
  - CLI `pop-linux diff 1 2` displays formatted Rich delta panel matching expected values.
  - GUI `show_comparison` dialog displays exact same delta text and newly discovered papers list.
- **Parity Verdict**: **PASS** (100% identical analytical output).

---

## 5. Configuration & Credential Safety

### Test Case 5.1: API Key Masking
- **CLI Behavior**: `pop-linux config --show` masks keys as `sec...key`.
- **GUI Behavior**: `SettingsDialog` configures `QLineEdit.EchoMode.Password` for `semanticscholar` and `ncbi` keys.
- **Log Audit**: Inspected test logs, stdout, stderr, and exported files; 0 raw API keys present.
- **Parity Verdict**: **PASS**.

### Test Case 5.2: Atomic Settings Save with Backup Retention
- **Action**: Modified `polite_email` to `contact@example.com` in `SettingsDialog` and clicked Save.
- **Outcome**:
  - Active `config.toml` updated with new value.
  - Timestamped backup created in config directory: `config.toml.bak.<timestamp>`.
- **Parity Verdict**: **PASS**.

---

## 6. Failure Handling, Cancellation & Responsiveness

### Test Case 6.1: Asynchronous Worker Cancellation
- **Scenario**: Simulated long-running HTTP request (60s).
- **Action**: User clicks `MainWindow.cancel_button`.
- **Observed Behavior**:
  - Worker signals `cancelled(generation)`.
  - Background task terminated cleanly via `asyncio.Task.cancel()`.
  - Progress bar hidden; `MainWindow.search_button` re-enabled; cancel button disabled.
  - UI notice updated: `"Search cancelled. Previous results were retained."`
  - Previous dataset remains loaded and interactive in the table.
- **Parity Verdict**: **PASS**.

### Test Case 6.2: Invalid Filter Handling
- **Scenario**: User submits `year_from=2025` and `year_to=2020`.
- **CLI**: Emits error message and exits with status 1.
- **GUI**: Sets notice text `"year_from must be less than or equal to year_to"` without starting background worker or clearing existing results.
- **Parity Verdict**: **PASS**.

---

## Overall Functional Parity Conclusion
The PySide6 desktop GUI exhibits **100% behavioral equivalence** with the CLI across all interactive research workflows. All shared business operations route through the identical execution engine, models, and calculation modules.
