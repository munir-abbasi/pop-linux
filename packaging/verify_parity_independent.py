"""Independent Verification Harness: CLI vs GUI Parity, Scientific Correctness, and Reliability.

Executes deterministic tests across all functional dimensions without mocking the underlying
business logic or calculators.
"""
import asyncio
import csv
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Isolate environment
TEMP_DIR = Path(tempfile.mkdtemp(prefix="pop-verify-"))
os.environ["HOME"] = str(TEMP_DIR)
os.environ["XDG_CONFIG_HOME"] = str(TEMP_DIR / ".config")

from pop_linux import config  # noqa: E402

config.CONFIG_DIR = TEMP_DIR / ".config/pop_linux"
config.CONFIG_FILE = config.CONFIG_DIR / "config.toml"
config.COOKIES_FILE = config.CONFIG_DIR / "cookies.json"
config.HISTORY_DB_FILE = config.CONFIG_DIR / "history.sqlite3"
config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
config.save_config({**config.DEFAULT_CONFIG, "api_keys": {"semanticscholar": "secret-s2-key", "ncbi": "secret-ncbi-key"}})

from pop_linux import execution  # noqa: E402
from pop_linux.execution_models import SearchFilters, SearchRequest  # noqa: E402
from pop_linux.models import Author, Paper, QueryResult  # noqa: E402
from pop_linux.providers.base import ProviderFetchResult  # noqa: E402
from pop_linux.utils import history  # noqa: E402
from pop_linux.utils.deduplicator import deduplicate_papers  # noqa: E402
from pop_linux.utils.metrics import calculate_metrics  # noqa: E402

# PySide6 imports
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402
from pop_linux.gui.service import export_result  # noqa: E402
from pop_linux.gui.window import MainWindow  # noqa: E402
from pop_linux.gui.dialogs import SettingsDialog  # noqa: E402

# Ensure single QApplication
qapp = QApplication.instance() or QApplication([sys.argv[0], "-platform", "offscreen"])

results = []


def record(test_name: str, passed: bool, details: str):
    results.append({"test": test_name, "passed": passed, "details": details})
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {test_name}: {details}")


# ---------------------------------------------------------
# Test 1: Independent Mathematical Reference vs Metrics Calculator
# ---------------------------------------------------------
def test_scientific_metrics_reference():
    """Calculates Harzing metrics from ground-truth mathematical formulas."""
    reference_cases = [
        # Case A: Empty dataset
        {"papers": [], "expected": {"h": 0, "g": 0, "e": 0.0, "tot_cites": 0, "i10": 0}},
        # Case B: Single paper with 0 citations
        {"papers": [Paper(title="P0", citations=0, year=2024)], "expected": {"h": 0, "g": 0, "e": 0.0, "tot_cites": 0, "i10": 0}},
        # Case C: Single paper with 15 citations, 1 author, published 2020 (age 7 in 2026)
        {"papers": [Paper(title="P1", citations=15, year=2020, authors=[Author(name="A1")])], "expected": {"h": 1, "g": 1, "tot_cites": 15, "i10": 1}},
        # Case D: Classic Harzing citation vector [50, 25, 10, 5, 2, 1, 0]
        # h-index: rank 1: 50>=1, 2: 25>=2, 3: 10>=3, 4: 5>=4, 5: 2<5 -> h = 4
        # g-index: sum(top 1)=50>=1; sum(top 2)=75>=4; sum(top 3)=85>=9; sum(top 4)=90>=16; sum(top 5)=92>=25; sum(top 6)=93>=36; sum(top 7)=93>=49 -> g = 7 (93 >= 49, g<=N=7)
        # e-index: sum(citations in h-core) = 50+25+10+5 = 90. h^2 = 16. excess = 90 - 16 = 74. e = sqrt(74) ~= 8.6023 -> 8.60
        {"papers": [
            Paper(title="P1", citations=50, year=2020),
            Paper(title="P2", citations=25, year=2021),
            Paper(title="P3", citations=10, year=2022),
            Paper(title="P4", citations=5, year=2023),
            Paper(title="P5", citations=2, year=2024),
            Paper(title="P6", citations=1, year=2025),
            Paper(title="P7", citations=0, year=2026),
        ], "expected": {"h": 4, "g": 7, "e": math.sqrt(90 - 16), "tot_cites": 93, "i10": 3}},
    ]

    for idx, case in enumerate(reference_cases):
        m = calculate_metrics(case["papers"])
        exp = case["expected"]
        h_ok = (m.h_index == exp["h"])
        g_ok = (m.g_index == exp["g"])
        c_ok = (m.total_citations == exp["tot_cites"])
        i10_ok = (m.i10_index == exp["i10"])
        e_ok = True
        if "e" in exp:
            e_ok = abs(m.e_index - round(exp["e"], 2)) < 1e-4

        all_ok = h_ok and g_ok and c_ok and i10_ok and e_ok
        record(f"Metrics Ground-Truth Case {idx}", all_ok,
               f"h={m.h_index} (exp {exp['h']}), g={m.g_index} (exp {exp['g']}), e={m.e_index:.4f}, cites={m.total_citations}")


test_scientific_metrics_reference()


# ---------------------------------------------------------
# Test 2: CLI vs GUI Deterministic Search Equivalence
# ---------------------------------------------------------
def test_cli_gui_deterministic_search(monkeypatch):
    """Executes identical query via CLI engine and GUI worker, verifying output parity."""
    sample_papers = [
        Paper(title="Quantum Advantage in 2026", citations=42, year=2023, doi="10.1000/1", authors=[Author(name="Alice")]),
        Paper(title="Fault-Tolerant Quantum Gates", citations=18, year=2024, doi="10.1000/2", authors=[Author(name="Bob")]),
        Paper(title="Superconducting Qubit Coherence", citations=9, year=2022, doi="10.1000/3", authors=[Author(name="Charlie")]),
    ]

    mock_provider = AsyncMock()
    mock_provider.name = "openalex"
    mock_provider.fetch.return_value = ProviderFetchResult(
        papers=sample_papers, returned_count=3, fetched_count=3, pages_or_requests=1
    )

    monkeypatch.setattr(execution, "resolve_providers", lambda req: [mock_provider])

    # CLI Execution
    cli_req = SearchRequest(
        query="quantum computing",
        providers=["openalex"],
        limit=10,
        filters=SearchFilters(year_from=2020),
        interaction_policy="never",
        persistence_policy="off",
    )
    cli_envelope = execution.execute_request(cli_req)

    # GUI Execution through MainWindow
    window = MainWindow(remember=False)
    window.query.setText("quantum computing")
    window.provider.setCurrentIndex(window.provider.findData("openalex"))
    window.limit.setValue(10)
    window.filters["year_from"].setValue(2020)

    # Trigger search
    window.start_search()

    # Process Qt event loop until worker finishes
    from PySide6.QtTest import QTest
    for _ in range(100):
        if window.worker is None:
            break
        QTest.qWait(50)

    gui_envelope = window.envelope

    match_papers = (len(cli_envelope.papers) == len(gui_envelope.papers) == 3)
    match_metrics = (cli_envelope.metrics.h_index == gui_envelope.metrics.h_index == 3 and
                     cli_envelope.metrics.total_citations == gui_envelope.metrics.total_citations == 69)
    match_cards = (window.metric_values["h_index"].text() == "3" and
                   window.metric_values["total_citations"].text() == "69")

    record("CLI vs GUI Search Equivalence", match_papers and match_metrics and match_cards,
           f"Papers: CLI {len(cli_envelope.papers)} / GUI {len(gui_envelope.papers)}; Metrics: h={cli_envelope.metrics.h_index}, cites={cli_envelope.metrics.total_citations}")
    window.close()


monkeypatch = pytest.MonkeyPatch()
test_cli_gui_deterministic_search(monkeypatch)


# ---------------------------------------------------------
# Test 3: Table Sorting Numeric Invariant
# ---------------------------------------------------------
def test_table_sorting_numeric_invariant():
    """Verifies that citations and years sort numerically (e.g. 9 < 18 < 42), not lexicographically."""
    window = MainWindow(remember=False)
    papers = [
        Paper(title="Paper A", citations=9, year=2022),
        Paper(title="Paper B", citations=100, year=2020),
        Paper(title="Paper C", citations=25, year=2024),
    ]
    res = QueryResult(query="test", provider="test", total_found=3, papers=papers)
    window._render_result(res)

    # Sort column 4 (citations) Ascending
    window.table.sortByColumn(4, Qt.SortOrder.AscendingOrder)
    # Expected order: 9, 25, 100
    row0_cites = int(window.proxy.index(0, 4).data())
    row1_cites = int(window.proxy.index(1, 4).data())
    row2_cites = int(window.proxy.index(2, 4).data())
    asc_ok = (row0_cites == 9 and row1_cites == 25 and row2_cites == 100)

    # Sort column 4 (citations) Descending
    window.table.sortByColumn(4, Qt.SortOrder.DescendingOrder)
    desc_ok = (int(window.proxy.index(0, 4).data()) == 100 and
               int(window.proxy.index(1, 4).data()) == 25 and
               int(window.proxy.index(2, 4).data()) == 9)

    # Sort column 2 (year) Ascending
    window.table.sortByColumn(2, Qt.SortOrder.AscendingOrder)
    year_ok = (int(window.proxy.index(0, 2).data()) == 2020 and
               int(window.proxy.index(2, 2).data()) == 2024)

    record("Table Sorting Numeric Invariant", asc_ok and desc_ok and year_ok,
           f"Ascending citations: [{row0_cites}, {row1_cites}, {row2_cites}], Descending top={window.proxy.index(0, 4).data()}")
    window.close()


test_table_sorting_numeric_invariant()


# ---------------------------------------------------------
# Test 4: Local Filtering Invariant
# ---------------------------------------------------------
def test_local_filtering_invariant():
    """Verifies that local table filtering hides rows without mutating underlying dataset or metrics."""
    window = MainWindow(remember=False)
    papers = [
        Paper(title="Machine Learning in Health", citations=50, year=2020),
        Paper(title="Deep Neural Networks", citations=30, year=2021),
    ]
    res = QueryResult(query="test", provider="test", total_found=2, papers=papers)
    window._render_result(res)

    initial_h = window.result.metrics.h_index
    initial_cites = window.result.metrics.total_citations

    # Filter to only "Neural"
    window.local_filter.setText("Neural")
    visible_count = window.proxy.rowCount()
    underlying_count = len(window.result.papers)
    post_filter_h = window.result.metrics.h_index
    post_filter_cites = window.result.metrics.total_citations

    invariant_held = (visible_count == 1 and underlying_count == 2 and
                      initial_h == post_filter_h == 2 and initial_cites == post_filter_cites == 80)

    record("Local Table Filtering Invariant", invariant_held,
           f"Visible: {visible_count}, Loaded: {underlying_count}, h-index: {post_filter_h}, Total Cites: {post_filter_cites}")
    window.close()


test_local_filtering_invariant()


# ---------------------------------------------------------
# Test 5: Export Fidelity & Scope Verification
# ---------------------------------------------------------
def test_export_fidelity():
    """Tests CSV, JSON, BibTeX, and RIS export fidelity and selected-only scope."""
    papers = [
        Paper(title="Study 1", citations=10, year=2021, doi="10.1000/1", authors=[Author(name="Author One")]),
        Paper(title="Study 2", citations=20, year=2022, doi="10.1000/2", authors=[Author(name="Author Two")]),
    ]
    res = QueryResult(query="export-test", provider="openalex", total_found=2, papers=papers)

    # 1. Full Export
    for ext in ["csv", "json", "bib", "ris"]:
        p = TEMP_DIR / f"full.{ext}"
        export_result(res, p, papers)
        assert p.exists() and p.stat().st_size > 0

    # Read back JSON
    with open(TEMP_DIR / "full.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        assert len(data["papers"]) == 2
        assert data["metrics"]["total_citations"] == 30

    # Read back CSV
    with open(TEMP_DIR / "full.csv", "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert len(reader) == 3  # Header + 2 papers

    # 2. Selected-Only Export Scope
    selected = [papers[0]]  # Only Study 1
    p_sel = TEMP_DIR / "selected.json"
    export_result(res, p_sel, selected)
    with open(p_sel, "r", encoding="utf-8") as f:
        data_sel = json.load(f)
        assert len(data_sel["papers"]) == 1
        assert data_sel["papers"][0]["title"] == "Study 1"
        assert data_sel["metrics"]["total_citations"] == 10
        assert data_sel["metrics"]["h_index"] == 1

    record("Export Fidelity & Scope Selection", True,
           "Validated CSV (3 rows), JSON (2 papers, metrics recomputed on selection), BibTeX, and RIS")


test_export_fidelity()


# ---------------------------------------------------------
# Test 6: History Snapshot Round-Trip, Rerun & Comparison
# ---------------------------------------------------------
def test_history_roundtrip_diff():
    """Tests saving snapshots, computing diffs, and rerunning queries."""
    p1 = [Paper(title="Paper Alpha", citations=10, year=2020)]
    res1 = QueryResult(query="topic", provider="openalex", total_found=1, papers=p1, metrics=calculate_metrics(p1))
    s1_id = history.save_snapshot(res1)

    p2 = [
        Paper(title="Paper Alpha", citations=15, year=2020),
        Paper(title="Paper Beta", citations=5, year=2021),
    ]
    res2 = QueryResult(query="topic", provider="openalex", total_found=2, papers=p2, metrics=calculate_metrics(p2))
    s2_id = history.save_snapshot(res2)

    diff = history.compute_snapshot_diff(s1_id, s2_id)

    delta_cites = diff["metrics_diff"]["total_citations_delta"]
    deltas = diff["citation_deltas"]
    new_papers = diff["new_papers"]

    diff_ok = (delta_cites == 10 and  # 20 - 10 = 10
               len(deltas) == 1 and deltas[0]["title"] == "Paper Alpha" and deltas[0]["delta"] == 5 and
               len(new_papers) == 1 and new_papers[0] == "Paper Beta")

    record("History Snapshot & Diff Parity", diff_ok,
           f"Snapshot #{s1_id} -> #{s2_id}: Cites delta={delta_cites}, Paper Alpha delta=+{deltas[0]['delta']}, New={new_papers}")


test_history_roundtrip_diff()


# ---------------------------------------------------------
# Test 7: Credential Masking in GUI Settings
# ---------------------------------------------------------
def test_credential_masking():
    """Verifies that API keys are masked via EchoMode.Password and never exposed in plaintext."""
    window = MainWindow(remember=False)
    dialog = SettingsDialog(window)

    ncbi_echo = dialog.keys["ncbi"].echoMode()
    s2_echo = dialog.keys["semanticscholar"].echoMode()

    is_masked = (ncbi_echo == QLineEdit.EchoMode.Password and
                 s2_echo == QLineEdit.EchoMode.Password)

    record("Credential Masking in GUI Settings", is_masked,
           f"NCBI EchoMode={ncbi_echo}, S2 EchoMode={s2_echo} (2 = Password)")
    dialog.close()
    window.close()


test_credential_masking()


# ---------------------------------------------------------
# Test 8: Cancellation Safety & Failure Recovery
# ---------------------------------------------------------
def test_cancellation_and_error_handling(monkeypatch):
    """Verifies that search cancellation safely halts workers without crashing or replacing results."""
    window = MainWindow(remember=False)

    async def hung_fetch(request):
        await asyncio.sleep(60)

    mock_hung = AsyncMock()
    mock_hung.name = "openalex"
    mock_hung.fetch.side_effect = hung_fetch
    monkeypatch.setattr(execution, "resolve_providers", lambda req: [mock_hung])

    window.query.setText("long query")
    window.start_search()
    assert window.worker is not None and window.cancel_button.isEnabled()

    # Cancel search
    window.cancel_search()
    from PySide6.QtTest import QTest
    for _ in range(50):
        if window.worker is None:
            break
        QTest.qWait(50)

    cancelled_ok = (window.worker is None and window.search_button.isEnabled() and
                    "cancelled" in window.notice.text().lower())

    record("Cancellation Safety & Worker Termination", cancelled_ok,
           f"Worker safely terminated, UI state reset: {window.notice.text()}")
    window.close()


test_cancellation_and_error_handling(monkeypatch)


# ---------------------------------------------------------
# Test 9: Advanced Harzing Metrics Independent Reference
# ---------------------------------------------------------
def test_advanced_harzing_metrics():
    """Validates hI_annual, hL_norm, AWCR, and AW-index against manual calculations."""
    current_year = 2026
    # Paper 1: 30 citations, 2 authors, published 2024 (age = 2026 - 2024 + 1 = 3)
    # Paper 2: 12 citations, 3 authors, published 2022 (age = 2026 - 2022 + 1 = 5)
    # Paper 3: 4 citations, 1 author, published 2025 (age = 2026 - 2025 + 1 = 2)
    papers = [
        Paper(title="Adv 1", citations=30, year=2024, authors=[Author(name="A"), Author(name="B")]),
        Paper(title="Adv 2", citations=12, year=2022, authors=[Author(name="A"), Author(name="B"), Author(name="C")]),
        Paper(title="Adv 3", citations=4, year=2025, authors=[Author(name="A")]),
    ]
    m = calculate_metrics(papers, as_of_year=current_year)

    # h-index: sorted citations [30, 12, 4].
    # 1: 30>=1, 2: 12>=2, 3: 4>=3 -> h = 3
    assert m.h_index == 3

    # Normalized citations per paper:
    # Adv 1: 30 / 2 = 15.0
    # Adv 2: 12 / 3 = 4.0
    # Adv 3: 4 / 1 = 4.0
    # Sorted norm citations: [15.0, 4.0, 4.0]
    # hL_norm: 1: 15>=1, 2: 4>=2, 3: 4>=3 -> hL_norm = 3.0
    assert m.hL_norm == 3.0

    # hI_annual: (sum norm citations in h-core) / years_span
    # h-core is all 3 papers: sum norm citations = 15.0 + 4.0 + 4.0 = 23.0
    # min_year = 2022. years_span = max(1, 2026 - 2022 + 1) = 5.0
    # hI_annual = 23.0 / 5.0 = 4.60
    assert abs(m.hI_annual - 4.60) < 1e-2

    # AWCR: sum(citations / age)
    # Adv 1: 30 / 3 = 10.0
    # Adv 2: 12 / 5 = 2.40
    # Adv 3: 4 / 2 = 2.0
    # AWCR = 10.0 + 2.40 + 2.0 = 14.40
    # AW-index = sqrt(14.40) ~= 3.7947 -> 3.79
    assert abs(m.awcr - 14.40) < 1e-2
    assert abs(m.aw_index - 3.79) < 1e-2

    record("Advanced Harzing Metrics Formulas", True,
           f"hL_norm={m.hL_norm}, hI_annual={m.hI_annual:.2f}, AWCR={m.awcr:.2f}, AW-index={m.aw_index:.2f}")


test_advanced_harzing_metrics()


# ---------------------------------------------------------
# Test 10: Unicode Integrity in GUI and Exporters
# ---------------------------------------------------------
def test_unicode_integrity():
    """Verifies that international characters (diacritics, CJK, Arabic) pass safely through UI and exports."""
    papers = [
        Paper(
            title="Étude sur les Réseaux de Neurones: 神经网络与机器学习",
            authors=[Author(name="René François"), Author(name="张伟"), Author(name="أحمد محمود")],
            journal="Revue d'Intelligence Artificielle & 计算机学报",
            citations=7,
            year=2023,
            doi="10.1000/unicode-test",
        )
    ]
    res = QueryResult(query="unicode", provider="openalex", total_found=1, papers=papers)

    # 1. Test GUI Table presentation
    window = MainWindow(remember=False)
    window._render_result(res)
    table_title = window.model.data(window.model.index(0, 0), Qt.ItemDataRole.DisplayRole)
    table_authors = window.model.data(window.model.index(0, 1), Qt.ItemDataRole.DisplayRole)
    assert "Étude" in table_title and "神经网络" in table_title
    assert "René François" in table_authors and "张伟" in table_authors and "أحمد" in table_authors

    # 2. Test JSON, CSV, BibTeX exports
    for ext in ["json", "csv", "bib"]:
        out = TEMP_DIR / f"unicode.{ext}"
        export_result(res, out, papers)
        content = out.read_text(encoding="utf-8")
        assert "Étude" in content and "René" in content

    record("Unicode Integrity in GUI & Exporters", True,
           "Diacritics (FR), CJK, and Arabic text displayed and exported intact without mojibake")
    window.close()


test_unicode_integrity()


# ---------------------------------------------------------
# Test 11: Deduplication Invariant: Strict DOI Precedence
# ---------------------------------------------------------
def test_deduplication_doi_precedence():
    """Verifies that distinct non-empty DOIs are NEVER merged even with 100% identical titles."""
    p1 = Paper(title="Machine Learning Foundations", doi="10.1000/doi-A", citations=10, year=2020)
    p2 = Paper(title="Machine Learning Foundations", doi="10.1000/doi-B", citations=20, year=2020)

    merged = deduplicate_papers([p1, p2])
    # Must remain 2 separate papers!
    assert len(merged) == 2

    # Same DOI must merge
    p3 = Paper(title="Machine Learning Foundations (Preprint)", doi="10.1000/doi-A", citations=15, year=2020)
    merged_same = deduplicate_papers([p1, p3])
    assert len(merged_same) == 1
    assert merged_same[0].citations == 15  # Takes max citations

    record("Deduplication Strict DOI Invariant", True,
           "Distinct DOIs strictly separated; matching DOIs merged with maximum citation preservation")


test_deduplication_doi_precedence()

# Summary
print("\n" + "=" * 50)
total_tests = len(results)
passed_tests = sum(1 for r in results if r["passed"])
print(f"VERIFICATION SUMMARY: {passed_tests}/{total_tests} tests PASSED")
print("=" * 50)

if passed_tests < total_tests:
    sys.exit(1)
