import json
import os
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path

from pop_linux.config import HISTORY_DB_FILE, ensure_config_dir
from pop_linux.execution_models import (
    AggregateCounts,
    ExecutionEnvelope,
    ExecutionMessage,
    MetricsContext,
    PersistenceReport,
    ProviderReport,
    ProvenanceEntry,
    SearchRequest,
)
from pop_linux.models import Metrics, Paper, QueryResult
from pop_linux.utils.identity import identity_token

#: History schema version. Version lives in the database (schema_meta table),
#: never derived from the application version.
SCHEMA_VERSION = 2

#: Columns added to `snapshots` in schema v2. Nullable: legacy-format rows
#: keep NULL for facts that were never recorded (never invent defaults).
_V2_SNAPSHOT_COLUMNS: dict[str, str] = {
    "request_json": "TEXT",
    "status": "TEXT",
    "app_version": "TEXT",
    "execution_schema": "TEXT",
    "provider_reports_json": "TEXT",
    "counts_json": "TEXT",
    "metrics_context_json": "TEXT",
    "provenance_json": "TEXT",
    "persistence_json": "TEXT",
    "warnings_json": "TEXT",
    "errors_json": "TEXT",
    "parent_snapshot_id": "INTEGER",
}

#: Column added to `snapshot_papers` in schema v2.
_V2_PAPER_COLUMNS: dict[str, str] = {
    "canonical_id": "TEXT",
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _get_schema_version(conn: sqlite3.Connection) -> int | None:
    """Reads the persisted schema version; None when the DB predates versioning."""
    if not _table_exists(conn, "schema_meta"):
        return None
    row = conn.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()
    if row is None:
        return None
    try:
        return int(row["value"])
    except (TypeError, ValueError):
        return None


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(version),),
    )


def _create_base_schema(conn: sqlite3.Connection) -> None:
    """Creates the base tables (v1-compatible column set) if absent."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
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
        CREATE TABLE IF NOT EXISTS snapshot_papers (
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


def _backup_database(conn: sqlite3.Connection) -> Path:
    """Creates a timestamped backup copy next to the database.

    Called before structural migration of a database that contains user data,
    so a failed migration can never silently destroy the original.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = HISTORY_DB_FILE.parent / f"{HISTORY_DB_FILE.name}.bak-{stamp}"
    dest = sqlite3.connect(backup_path)
    try:
        conn.backup(dest)
        dest.commit()
    finally:
        dest.close()
    try:
        os.chmod(backup_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Best-effort hardening; not fatal.
    return backup_path


def _add_v2_columns(conn: sqlite3.Connection) -> None:
    """Adds v2 columns (idempotent) inside the caller's transaction."""
    snap_cols = _columns(conn, "snapshots")
    for column, decl in _V2_SNAPSHOT_COLUMNS.items():
        if column not in snap_cols:
            conn.execute(f"ALTER TABLE snapshots ADD COLUMN {column} {decl}")
    paper_cols = _columns(conn, "snapshot_papers")
    for column, decl in _V2_PAPER_COLUMNS.items():
        if column not in paper_cols:
            conn.execute(f"ALTER TABLE snapshot_papers ADD COLUMN {column} {decl}")


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Migrates a pre-versioning (v1) database to schema v2.

    Safety contract (implementation_plan.md Phase 9):
    1. detect schema version (caller);
    2. create a timestamped backup copy before structural migration when the
       DB contains user data;
    3. execute ALTERs in a transaction; schema version is set only after
       success so a failed migration leaves the original usable and unmarked;
    4. legacy rows keep NULL for facts that were never recorded.
    """
    row_count = conn.execute("SELECT COUNT(*) AS n FROM snapshots").fetchone()["n"]
    if row_count > 0:
        _backup_database(conn)
    try:
        with conn:
            _add_v2_columns(conn)
            _set_schema_version(conn, SCHEMA_VERSION)
    except Exception:
        # Rollback restores the pre-migration structure; the original remains
        # a usable v1 database and the backup (if created) preserves the data.
        raise


def get_db_connection() -> sqlite3.Connection:
    """Initializes and returns an active SQLite database connection.

    Handles schema detection and migration: a fresh database is created at v2;
    a legacy (pre-versioning) database is migrated with a backup first; an
    already-v2 database is opened as-is. File permissions are best-effort 0600.
    """
    ensure_config_dir()
    conn = sqlite3.connect(HISTORY_DB_FILE)
    conn.row_factory = sqlite3.Row

    with conn:
        _create_base_schema(conn)

    version = _get_schema_version(conn)
    if version is None:
        # Pre-versioning database (possibly with user data) -> migrate.
        _migrate_v1_to_v2(conn)
    elif version < SCHEMA_VERSION:
        with conn:
            _add_v2_columns(conn)
            _set_schema_version(conn, SCHEMA_VERSION)

    try:
        os.chmod(HISTORY_DB_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Best-effort hardening; not fatal if the filesystem rejects it.

    return conn


# ---------------------------------------------------------------------------
# Legacy snapshot API (QueryResult shape; retained for the human CLI)
# ---------------------------------------------------------------------------


def save_snapshot(result: QueryResult) -> int:
    """Saves a QueryResult as a snapshot (legacy-format row).

    The row records what the legacy contract knew: query, provider label,
    returned papers, metrics, timing. Request flags and provider execution
    diagnostics are unknown for such rows and stay NULL (never synthesized).
    """
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()
    metrics_str = result.metrics.model_dump_json() if result.metrics else "{}"

    with conn:
        cursor = conn.execute(
            """
            INSERT INTO snapshots (query, provider, total_found, search_time_seconds, timestamp, metrics_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (result.query, result.provider, result.total_found, result.search_time_seconds, now_iso, metrics_str)
        )
        snapshot_id = cursor.lastrowid

        for p in result.papers:
            authors_json = json.dumps([a.model_dump() for a in p.authors])
            conn.execute(
                """
                INSERT INTO snapshot_papers (snapshot_id, title, authors_json, year, journal, citations, doi, url, source_provider, paper_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (snapshot_id, p.title, authors_json, p.year, p.journal, p.citations, p.doi, p.url, p.source_provider, p.paper_id)
            )

    conn.close()
    return snapshot_id or 0


def list_snapshots(limit: int = 20) -> list[dict]:
    """Retrieves the most recent snapshots (legacy + execution rows)."""
    conn = get_db_connection()
    with conn:
        rows = conn.execute(
            """
            SELECT id, query, provider, total_found, timestamp, metrics_json, status, parent_snapshot_id
            FROM snapshots
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

    conn.close()
    results = []
    for r in rows:
        m_dict = json.loads(r["metrics_json"]) if r["metrics_json"] else {}
        results.append({
            "id": r["id"],
            "query": r["query"],
            "provider": r["provider"],
            "total_found": r["total_found"],
            "timestamp": r["timestamp"],
            "h_index": m_dict.get("h_index", 0),
            "total_citations": m_dict.get("total_citations", 0),
            # v2-only facts are None for legacy-format rows:
            "status": r["status"] if "status" in r.keys() else None,
            "parent_snapshot_id": r["parent_snapshot_id"] if "parent_snapshot_id" in r.keys() else None,
        })
    return results


def get_snapshot(snapshot_id: int) -> QueryResult | None:
    """Retrieves a single snapshot as the legacy QueryResult shape."""
    conn = get_db_connection()
    try:
        s_row = conn.execute(
            "SELECT query, provider, total_found, search_time_seconds, metrics_json FROM snapshots WHERE id = ?",
            (snapshot_id,)
        ).fetchone()

        if not s_row:
            return None

        p_rows = conn.execute(
            "SELECT title, authors_json, year, journal, citations, doi, url, source_provider, paper_id FROM snapshot_papers WHERE snapshot_id = ?",
            (snapshot_id,)
        ).fetchall()
    finally:
        conn.close()

    papers = []
    for pr in p_rows:
        authors_raw = json.loads(pr["authors_json"]) if pr["authors_json"] else []
        papers.append(
            Paper(
                title=pr["title"],
                authors=authors_raw,
                year=pr["year"],
                journal=pr["journal"],
                citations=pr["citations"],
                doi=pr["doi"],
                url=pr["url"],
                source_provider=pr["source_provider"] or "",
                paper_id=pr["paper_id"]
            )
        )

    metrics_obj = Metrics.model_validate_json(s_row["metrics_json"]) if s_row["metrics_json"] else Metrics()

    return QueryResult(
        query=s_row["query"],
        provider=s_row["provider"],
        total_found=s_row["total_found"],
        papers=papers,
        metrics=metrics_obj,
        search_time_seconds=s_row["search_time_seconds"]
    )


# ---------------------------------------------------------------------------
# Execution repository (schema v2)
# ---------------------------------------------------------------------------


def save_execution(envelope: ExecutionEnvelope, parent_snapshot_id: int | None = None) -> int:
    """Persists a complete execution envelope (schema v2 row).

    Stores the resolved request, execution status, app/execution schema
    versions, provider reports, aggregate counts, metrics and context,
    normalized publications with identity tokens, provenance observations,
    persistence report, warnings/errors, and rerun lineage.
    """
    conn = get_db_connection()
    now_iso = datetime.now(timezone.utc).isoformat()

    request_json = envelope.request.model_dump_json()
    provider_reports_json = json.dumps(
        [r.model_dump(mode="json") for r in envelope.provider_reports]
    )
    counts_json = envelope.counts.model_dump_json()
    metrics_json = envelope.metrics.model_dump_json() if envelope.metrics else "{}"
    metrics_context_json = envelope.metrics_context.model_dump_json() if envelope.metrics_context else None
    provenance_json = json.dumps([p.model_dump(mode="json") for p in envelope.provenance])
    persistence_json = envelope.persistence.model_dump_json()
    warnings_json = json.dumps([w.model_dump(mode="json") for w in envelope.warnings])
    errors_json = json.dumps([e.model_dump(mode="json") for e in envelope.errors])

    with conn:
        cursor = conn.execute(
            """
            INSERT INTO snapshots (
                query, provider, total_found, search_time_seconds, timestamp, metrics_json,
                request_json, status, app_version, execution_schema,
                provider_reports_json, counts_json, metrics_context_json,
                provenance_json, persistence_json, warnings_json, errors_json,
                parent_snapshot_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                envelope.request.query,
                "all (deduplicated)" if len(envelope.request.providers) > 1 else envelope.request.providers[0],
                envelope.counts.merged,
                envelope.elapsed_seconds,
                now_iso,
                metrics_json,
                request_json,
                envelope.status,
                envelope.app_version,
                envelope.schema_,
                provider_reports_json,
                counts_json,
                metrics_context_json,
                provenance_json,
                persistence_json,
                warnings_json,
                errors_json,
                parent_snapshot_id,
            )
        )
        snapshot_id = cursor.lastrowid

        for p in envelope.papers:
            authors_json = json.dumps([a.model_dump() for a in p.authors])
            conn.execute(
                """
                INSERT INTO snapshot_papers (snapshot_id, title, authors_json, year, journal, citations, doi, url, source_provider, paper_id, canonical_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    p.title,
                    authors_json,
                    p.year,
                    p.journal,
                    p.citations,
                    p.doi,
                    p.url,
                    p.source_provider,
                    p.paper_id,
                    identity_token(p),
                )
            )

    conn.close()
    return snapshot_id or 0


def is_execution(snapshot_id: int) -> bool:
    """True when the row stores a full reconstructable execution (v2 format)."""
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT request_json FROM snapshots WHERE id = ?",
            (snapshot_id,)
        ).fetchone()
        return row is not None and row["request_json"] is not None
    finally:
        conn.close()


def get_execution(snapshot_id: int) -> ExecutionEnvelope | None:
    """Reconstructs a persisted execution envelope.

    Returns None for missing IDs and for legacy-format rows whose request was
    never recorded — such executions cannot be truthfully reconstructed and
    are never synthesized from current defaults.
    """
    conn = get_db_connection()
    try:
        s_row = conn.execute(
            """
            SELECT request_json, status, app_version, execution_schema,
                   provider_reports_json, counts_json, metrics_context_json,
                   provenance_json, persistence_json, warnings_json, errors_json,
                   metrics_json, search_time_seconds, parent_snapshot_id
            FROM snapshots WHERE id = ?
            """,
            (snapshot_id,)
        ).fetchone()

        if not s_row or s_row["request_json"] is None:
            return None

        p_rows = conn.execute(
            "SELECT title, authors_json, year, journal, citations, doi, url, source_provider, paper_id, canonical_id FROM snapshot_papers WHERE snapshot_id = ?",
            (snapshot_id,)
        ).fetchall()
    finally:
        conn.close()

    request = SearchRequest.model_validate_json(s_row["request_json"])

    papers: list[Paper] = []
    for pr in p_rows:
        authors_raw = json.loads(pr["authors_json"]) if pr["authors_json"] else []
        papers.append(
            Paper(
                title=pr["title"],
                authors=authors_raw,
                year=pr["year"],
                journal=pr["journal"],
                citations=pr["citations"],
                doi=pr["doi"],
                url=pr["url"],
                source_provider=pr["source_provider"] or "",
                paper_id=pr["paper_id"],
            )
        )

    provider_reports = [ProviderReport.model_validate(r) for r in json.loads(s_row["provider_reports_json"])] if s_row["provider_reports_json"] else []
    counts = AggregateCounts.model_validate_json(s_row["counts_json"]) if s_row["counts_json"] else AggregateCounts()
    metrics = Metrics.model_validate_json(s_row["metrics_json"]) if s_row["metrics_json"] else None
    metrics_context = MetricsContext.model_validate_json(s_row["metrics_context_json"]) if s_row["metrics_context_json"] else None
    provenance = [ProvenanceEntry.model_validate(p) for p in json.loads(s_row["provenance_json"])] if s_row["provenance_json"] else []
    persistence = PersistenceReport.model_validate_json(s_row["persistence_json"]) if s_row["persistence_json"] else PersistenceReport()
    warnings = [ExecutionMessage.model_validate(w) for w in json.loads(s_row["warnings_json"])] if s_row["warnings_json"] else []
    errors = [ExecutionMessage.model_validate(e) for e in json.loads(s_row["errors_json"])] if s_row["errors_json"] else []

    envelope = ExecutionEnvelope(
        app_version=s_row["app_version"] or "unknown",
        status=s_row["status"] or "error",  # type: ignore[arg-type]
        request=request,
        provider_reports=provider_reports,
        counts=counts,
        papers=papers,
        provenance=provenance,
        metrics=metrics,
        metrics_context=metrics_context,
        persistence=persistence,
        warnings=warnings,
        errors=errors,
        elapsed_seconds=s_row["search_time_seconds"] or 0.0,
    )
    if s_row["execution_schema"]:
        object.__setattr__(envelope, "schema_", s_row["execution_schema"])
    return envelope


# ---------------------------------------------------------------------------
# Diff (Packet 15 consumes the shared identity service)
# ---------------------------------------------------------------------------


def compute_snapshot_diff(snapshot1_id: int, snapshot2_id: int) -> dict:
    """Computes citation delta, new papers, and metric trajectory between two snapshots.

    Identity is decided by the shared publication-identity service (Packet 15):
    DOI-backed equivalence first, fuzzy title/year fallback under the same rules
    as live deduplication. Papers that match multiple baselines ambiguously are
    surfaced separately instead of being silently collapsed.
    """
    from pop_linux.utils.identity import compare_papers

    q1 = get_snapshot(snapshot1_id)
    q2 = get_snapshot(snapshot2_id)

    if not q1 or not q2:
        raise ValueError(f"One or both snapshot IDs ({snapshot1_id}, {snapshot2_id}) do not exist.")

    m1 = q1.metrics or Metrics()
    m2 = q2.metrics or Metrics()

    citation_deltas = []
    new_papers: list[str] = []
    ambiguous: list[dict] = []

    for p2 in q2.papers:
        matches = [p1 for p1 in q1.papers if compare_papers(p2, p1).same]
        if len(matches) > 1:
            ambiguous.append({
                "title": p2.title,
                "matched_baselines": [p1.title for p1 in matches],
            })
            continue
        if matches:
            p1 = matches[0]
            diff = p2.citations - p1.citations
            if diff != 0:
                citation_deltas.append({
                    "title": p2.title,
                    "old_citations": p1.citations,
                    "new_citations": p2.citations,
                    "delta": diff,
                })
        else:
            new_papers.append(p2.title)

    return {
        "snapshot1_id": snapshot1_id,
        "snapshot2_id": snapshot2_id,
        "query": q2.query,
        "citation_deltas": citation_deltas,
        "new_papers": new_papers,
        "ambiguous_matches": ambiguous,
        "metrics_diff": {
            "total_papers_delta": m2.total_papers - m1.total_papers,
            "total_citations_delta": m2.total_citations - m1.total_citations,
            "h_index_delta": m2.h_index - m1.h_index,
            "g_index_delta": m2.g_index - m1.g_index,
            "awcr_delta": round(m2.awcr - m1.awcr, 2),
        }
    }
