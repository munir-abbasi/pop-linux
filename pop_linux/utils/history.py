import json
import os
import sqlite3
import stat
from datetime import datetime, timezone
from pop_linux.config import HISTORY_DB_FILE, ensure_config_dir
from pop_linux.models import Metrics, Paper, QueryResult


def get_db_connection() -> sqlite3.Connection:
    """Initializes and returns an active SQLite database connection with schema created and 0600 permissions."""
    ensure_config_dir()
    conn = sqlite3.connect(HISTORY_DB_FILE)
    conn.row_factory = sqlite3.Row

    with conn:
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

    try:
        os.chmod(HISTORY_DB_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Best-effort hardening; not fatal if the filesystem rejects it.

    return conn


def save_snapshot(result: QueryResult) -> int:
    """Saves a QueryResult object as a persistent snapshot in the SQLite database."""
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
    """Retrieves list of stored search snapshots."""
    conn = get_db_connection()
    with conn:
        rows = conn.execute(
            """
            SELECT id, query, provider, total_found, timestamp, metrics_json
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
            "total_citations": m_dict.get("total_citations", 0)
        })
    return results


def get_snapshot(snapshot_id: int) -> QueryResult | None:
    """Retrieves a single QueryResult snapshot by ID."""
    conn = get_db_connection()
    with conn:
        s_row = conn.execute(
            "SELECT query, provider, total_found, search_time_seconds, metrics_json FROM snapshots WHERE id = ?",
            (snapshot_id,)
        ).fetchone()

        if not s_row:
            conn.close()
            return None

        p_rows = conn.execute(
            "SELECT title, authors_json, year, journal, citations, doi, url, source_provider, paper_id FROM snapshot_papers WHERE snapshot_id = ?",
            (snapshot_id,)
        ).fetchall()

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


def compute_snapshot_diff(snapshot1_id: int, snapshot2_id: int) -> dict:
    """Computes citation delta, new papers, and metric trajectory between two search snapshots."""
    q1 = get_snapshot(snapshot1_id)
    q2 = get_snapshot(snapshot2_id)

    if not q1 or not q2:
        raise ValueError(f"One or both snapshot IDs ({snapshot1_id}, {snapshot2_id}) do not exist.")

    m1 = q1.metrics or Metrics()
    m2 = q2.metrics or Metrics()

    # Map paper titles to citations in q1 and q2
    p1_map = {p.title.lower().strip(): p for p in q1.papers}
    p2_map = {p.title.lower().strip(): p for p in q2.papers}

    citation_deltas = []
    for title, p2 in p2_map.items():
        if title in p1_map:
            p1 = p1_map[title]
            diff = p2.citations - p1.citations
            if diff != 0:
                citation_deltas.append({
                    "title": p2.title,
                    "old_citations": p1.citations,
                    "new_citations": p2.citations,
                    "delta": diff
                })

    new_papers = [p2.title for title, p2 in p2_map.items() if title not in p1_map]

    return {
        "snapshot1_id": snapshot1_id,
        "snapshot2_id": snapshot2_id,
        "query": q2.query,
        "citation_deltas": citation_deltas,
        "new_papers": new_papers,
        "metrics_diff": {
            "total_papers_delta": m2.total_papers - m1.total_papers,
            "total_citations_delta": m2.total_citations - m1.total_citations,
            "h_index_delta": m2.h_index - m1.h_index,
            "g_index_delta": m2.g_index - m1.g_index,
            "awcr_delta": round(m2.awcr - m1.awcr, 2),
        }
    }
