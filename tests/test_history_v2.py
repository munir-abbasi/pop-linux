"""History schema v2 tests (Packet 14): migration safety, repository API,
and data-safety guarantees from implementation_plan.md Phase 9.

Uses real temporary SQLite databases; never touches a user's real history.
"""

import json
import sqlite3

import pytest

from pop_linux.utils import history as hist
from pop_linux.execution_models import (
    AggregateCounts,
    ExecutionEnvelope,
    ExecutionMessage,
    MetricsContext,
    PersistenceReport,
    ProviderCounts,
    ProviderReport,
    SearchFilters,
    SearchRequest,
)
from pop_linux.models import Author, Metrics, Paper, QueryResult
from pop_linux.utils.history import (
    SCHEMA_VERSION,
    compute_snapshot_diff,
    get_db_connection,
    get_execution,
    get_snapshot,
    is_execution,
    list_snapshots,
    save_execution,
    save_snapshot,
)


def _request(**kw) -> SearchRequest:
    base = {
        "query": "history v2",
        "providers": ["openalex", "crossref"],
        "limit": 10,
        "filters": SearchFilters(year_from=2020, min_citations=2),
        "interaction_policy": "never",
        "persistence_policy": "explicit",
    }
    base.update(kw)
    return SearchRequest(**base)


def _envelope(status="success", providers=("openalex", "crossref"), parent=None) -> ExecutionEnvelope:
    papers = [
        Paper(title="V2 Paper One", citations=12, doi="10.1000/1", year=2021,
              authors=[Author(name="A")], source_provider="openalex", paper_id="W1"),
        Paper(title="V2 Paper Two", citations=7, doi="10.1000/2", year=2022,
              source_provider="crossref", paper_id="W2"),
    ]
    request = _request(providers=list(providers))
    reports = [
        ProviderReport(
            provider=name,
            status="success",
            elapsed_seconds=0.4,
            counts=ProviderCounts(matched=99, fetched=1, after_filter=1, returned=1),
            pages_or_requests=2,
            filter_modes={"issn": "native"},
        )
        for name in providers
    ]
    from pop_linux.execution_models import ProvenanceEntry, SourceObservation

    prov = [
        ProvenanceEntry(
            canonical_id="doi:10.1000/1",
            citation_selection_policy="max_observed",
            observations=[SourceObservation(provider="openalex", paper_id="W1", title="V2 Paper One", citations=12)],
            preferred_citation_source="openalex",
        ),
    ]
    return ExecutionEnvelope(
        app_version="0.1.0-test",
        status=status,  # type: ignore[arg-type]
        request=request,
        provider_reports=reports,
        counts=AggregateCounts(returned_raw=len(papers), merged=len(papers)),
        papers=papers,
        provenance=prov,
        metrics=Metrics(total_papers=2, total_citations=19, h_index=1),
        metrics_context=MetricsContext(paper_count=2, providers_contributing=list(providers), citation_selection_policy="max_observed"),
        persistence=PersistenceReport(history_policy="explicit", snapshot_written=True, snapshot_id=77),
        warnings=[ExecutionMessage(code="FILTER_APPROXIMATED", message="demo", provider="crossref")],
        errors=[],
        elapsed_seconds=0.9,
    )


# ---------------------------------------------------------------------------
# Fresh v2 creation
# ---------------------------------------------------------------------------


def test_fresh_database_is_created_at_v2(tmp_path, monkeypatch):
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    conn = get_db_connection()
    version = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()["value"]
    conn.close()
    assert int(version) == SCHEMA_VERSION == 2


# ---------------------------------------------------------------------------
# v1 fixture migration (real v1-shaped database)
# ---------------------------------------------------------------------------


def _make_v1_fixture(db_path) -> int:
    """Builds a genuine v1-shaped database: no schema_meta, no v2 columns."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("""
            CREATE TABLE snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                provider TEXT NOT NULL,
                total_found INTEGER NOT NULL,
                search_time_seconds REAL NOT NULL,
                timestamp TEXT NOT NULL,
                metrics_json TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE snapshot_papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                authors_json TEXT NOT NULL,
                year INTEGER,
                journal TEXT,
                citations INTEGER NOT NULL,
                doi TEXT,
                url TEXT,
                source_provider TEXT,
                paper_id TEXT,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
            )
        """)
        cur = conn.execute(
            "INSERT INTO snapshots (query, provider, total_found, search_time_seconds, timestamp, metrics_json) VALUES (?,?,?,?,?,?)",
            ("legacy asthma", "openalex", 1, 1.2, "2025-01-01T00:00:00+00:00", json.dumps({"h_index": 1, "total_citations": 5})),
        )
        snap_id = cur.lastrowid
        conn.execute(
            "INSERT INTO snapshot_papers (snapshot_id, title, authors_json, year, journal, citations, doi, url, source_provider, paper_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (snap_id, "Legacy Paper", "[]", 2020, "Old Journal", 5, "10.1000/legacy", None, "openalex", "L1"),
        )
    conn.commit()
    conn.close()
    return snap_id


def test_v1_fixture_migrates_and_legacy_data_remains_readable(tmp_path, monkeypatch):
    db = tmp_path / "h.sqlite3"
    legacy_id = _make_v1_fixture(db)
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", db)

    conn = get_db_connection()
    version = int(conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()["value"])
    conn.close()
    assert version == 2

    # Legacy row remains fully readable through the legacy API
    snap = get_snapshot(legacy_id)
    assert snap is not None
    assert snap.query == "legacy asthma"
    assert snap.papers[0].title == "Legacy Paper"
    assert snap.papers[0].doi == "10.1000/legacy"

    # New v2 rows coexist with migrated legacy rows
    env = _envelope()
    new_id = save_execution(env)
    assert new_id > legacy_id
    assert is_execution(legacy_id) is False
    assert is_execution(new_id) is True


def test_migration_creates_timestamped_backup_for_populated_v1(tmp_path, monkeypatch):
    db = tmp_path / "h.sqlite3"
    _make_v1_fixture(db)
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", db)

    get_db_connection()
    backups = list(tmp_path.glob("h.sqlite3.bak-*"))
    assert len(backups) == 1
    # The backup is a valid SQLite DB containing the original data
    bconn = sqlite3.connect(backups[0])
    n = bconn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    bconn.close()
    assert n == 1


def test_migration_of_empty_v1_creates_no_backup(tmp_path, monkeypatch):
    db = tmp_path / "h.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT NOT NULL, provider TEXT NOT NULL,
            total_found INTEGER NOT NULL, search_time_seconds REAL NOT NULL,
            timestamp TEXT NOT NULL, metrics_json TEXT NOT NULL)
    """)
    conn.commit()
    conn.close()

    monkeypatch.setattr(hist, "HISTORY_DB_FILE", db)
    get_db_connection()
    assert list(tmp_path.glob("*.bak-*")) == []  # nothing to preserve


def test_migration_failure_leaves_original_usable_and_unmarked(tmp_path, monkeypatch):
    """A failed migration must not silently replace user data or mark the schema."""
    db = tmp_path / "h.sqlite3"
    _make_v1_fixture(db)
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", db)

    import pop_linux.utils.history as hmod

    def failing_add_columns(conn):
        raise sqlite3.OperationalError("simulated migration failure")

    monkeypatch.setattr(hmod, "_add_v2_columns", failing_add_columns)

    with pytest.raises(sqlite3.OperationalError):
        get_db_connection()

    # The database must remain a usable unversioned v1 with intact data:
    # the ALTER transaction rolled back and schema version was never marked.
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(snapshots)").fetchall()}
    assert "request_json" not in cols  # structural change rolled back
    n = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    row = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    conn.close()
    assert n == 1
    assert row is None  # unmarked: next attempt will re-run migration


def test_migration_is_idempotent_on_reentry(tmp_path, monkeypatch):
    db = tmp_path / "h.sqlite3"
    _make_v1_fixture(db)
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", db)

    get_db_connection().close()
    # Re-open: must not re-backup or fail
    get_db_connection().close()
    backups = list(tmp_path.glob("*.bak-*"))
    assert len(backups) == 1  # only the original migration backed up


# ---------------------------------------------------------------------------
# Execution repository: persistence and reconstruction
# ---------------------------------------------------------------------------


def test_save_and_get_execution_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    env = _envelope()
    snap_id = save_execution(env)

    restored = get_execution(snap_id)
    assert restored is not None
    assert restored.status == "success"
    assert restored.request == env.request
    assert restored.app_version == "0.1.0-test"
    assert restored.schema_ == "pop-linux.execution/v1"
    assert [r.provider for r in restored.provider_reports] == ["openalex", "crossref"]
    assert restored.provider_reports[0].pages_or_requests == 2
    assert restored.provider_reports[0].filter_modes == {"issn": "native"}
    assert restored.counts.returned_raw == 2
    assert restored.metrics.h_index == 1
    assert restored.metrics_context.citation_selection_policy == "max_observed"
    assert restored.persistence.snapshot_id == 77
    assert restored.warnings[0].code == "FILTER_APPROXIMATED"
    assert len(restored.papers) == 2
    assert restored.provenance[0].canonical_id == "doi:10.1000/1"
    assert restored.provenance[0].preferred_citation_source == "openalex"


def test_papers_persist_canonical_identity_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    snap_id = save_execution(_envelope())

    conn = sqlite3.connect(tmp_path / "h.sqlite3")
    rows = conn.execute(
        "SELECT title, canonical_id FROM snapshot_papers WHERE snapshot_id = ? ORDER BY id", (snap_id,)
    ).fetchall()
    conn.close()
    ids = dict(rows)
    assert ids["V2 Paper One"] == "doi:10.1000/1"
    assert ids["V2 Paper Two"] == "doi:10.1000/2"


def test_rerun_lineage_parent_snapshot_id(tmp_path, monkeypatch):
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    parent = save_execution(_envelope())
    child = save_execution(_envelope(), parent_snapshot_id=parent)

    rows = {r["id"]: r["parent_snapshot_id"] for r in list_snapshots(limit=10)}
    assert rows[parent] is None
    assert rows[child] == parent


def test_legacy_row_cannot_be_falsely_reconstructed(tmp_path, monkeypatch):
    """Legacy-format rows return None from get_execution: no invented facts."""
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    legacy_qr = QueryResult(
        query="legacy only",
        provider="openalex",
        total_found=1,
        papers=[Paper(title="L", citations=1)],
        metrics=Metrics(),
        search_time_seconds=0.1,
    )
    snap_id = save_snapshot(legacy_qr)

    assert get_snapshot(snap_id) is not None  # legacy read works
    assert get_execution(snap_id) is None  # reconstruction truthfully unavailable
    assert is_execution(snap_id) is False


def test_sql_parameterization_with_hostile_values(tmp_path, monkeypatch):
    """User-controlled values pass through bound parameters unharmed."""
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    hostile = "'; DROP TABLE snapshots; --"
    qr = QueryResult(
        query=hostile,
        provider="openalex",
        total_found=1,
        papers=[Paper(title=hostile, citations=1)],
        metrics=Metrics(),
        search_time_seconds=0.1,
    )
    snap_id = save_snapshot(qr)

    conn = sqlite3.connect(tmp_path / "h.sqlite3")
    n = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    stored = conn.execute("SELECT query FROM snapshots WHERE id = ?", (snap_id,)).fetchone()[0]
    conn.close()
    assert n >= 1  # table still exists and row stored
    assert stored == hostile


# ---------------------------------------------------------------------------
# Shared-identity diff (Packet 15 dependency proven here)
# ---------------------------------------------------------------------------


def test_diff_uses_shared_identity_across_title_change(tmp_path, monkeypatch):
    """DOI-backed match survives a title rewrite; different DOIs never collapse."""
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")

    id1 = save_snapshot(QueryResult(
        query="q", provider="openalex", total_found=2,
        papers=[Paper(title="Original Long Title", citations=10, doi="10.1000/same", year=2021)],
        metrics=Metrics(total_papers=1, total_citations=10), search_time_seconds=0.1))
    id2 = save_snapshot(QueryResult(
        query="q", provider="openalex", total_found=2,
        papers=[
            Paper(title="Completely Rewritten Title", citations=15, doi="10.1000/same", year=2021),  # same DOI
            Paper(title="Original Long Title", citations=99, doi="10.1000/other", year=2021),       # different DOI: no collapse
        ],
        metrics=Metrics(total_papers=2, total_citations=114), search_time_seconds=0.2))

    diff = compute_snapshot_diff(id1, id2)
    assert diff["citation_deltas"][0]["delta"] == 5  # DOI matched across title change
    assert "Completely Rewritten Title" not in [p for p in diff["new_papers"]]
    assert "Original Long Title" in diff["new_papers"]  # different DOI -> new publication, not a merge


def test_diff_surfaces_ambiguous_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    twin1 = Paper(title="Ambiguous Study", citations=5, year=2021)   # no DOI, fuzzy-twin titles
    twin2 = Paper(title="Ambiguous Studyy", citations=6, year=2021)
    id1 = save_snapshot(QueryResult(query="q", provider="openalex", total_found=2,
                                    papers=[twin1, twin2], metrics=Metrics(), search_time_seconds=0.1))
    id2 = save_snapshot(QueryResult(query="q", provider="openalex", total_found=1,
                                    papers=[Paper(title="Ambiguous Study", citations=9, year=2021)],
                                    metrics=Metrics(), search_time_seconds=0.2))
    diff = compute_snapshot_diff(id1, id2)
    assert diff["ambiguous_matches"], "twin baselines must surface as ambiguous, not silently collapsed"
