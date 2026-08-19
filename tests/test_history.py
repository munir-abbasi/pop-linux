from pop_linux.models import QueryResult, Paper, Metrics
from pop_linux.utils.history import save_snapshot, list_snapshots, get_snapshot, compute_snapshot_diff


def test_history_save_and_get(tmp_path, monkeypatch):
    test_db = tmp_path / "history_test.sqlite3"
    monkeypatch.setattr("pop_linux.utils.history.HISTORY_DB_FILE", test_db)

    paper1 = Paper(title="Paper Alpha", citations=10, year=2021)
    paper2 = Paper(title="Paper Beta", citations=20, year=2022)
    metrics = Metrics(total_papers=2, total_citations=30, h_index=2)

    res1 = QueryResult(
        query="Asthma Test",
        provider="openalex",
        total_found=2,
        papers=[paper1, paper2],
        metrics=metrics,
        search_time_seconds=1.5
    )

    s1_id = save_snapshot(res1)
    assert s1_id > 0

    snapshots = list_snapshots()
    assert len(snapshots) == 1
    assert snapshots[0]["id"] == s1_id
    assert snapshots[0]["query"] == "Asthma Test"

    retrieved = get_snapshot(s1_id)
    assert retrieved is not None
    assert len(retrieved.papers) == 2
    assert retrieved.metrics.h_index == 2


def test_compute_snapshot_diff(tmp_path, monkeypatch):
    test_db = tmp_path / "history_test2.sqlite3"
    monkeypatch.setattr("pop_linux.utils.history.HISTORY_DB_FILE", test_db)

    p1_s1 = Paper(title="Paper Alpha", citations=10, year=2021)
    p2_s1 = Paper(title="Paper Beta", citations=20, year=2022)

    p1_s2 = Paper(title="Paper Alpha", citations=15, year=2021) # +5 citations
    p2_s2 = Paper(title="Paper Beta", citations=20, year=2022)  # no change
    p3_s2 = Paper(title="Paper Gamma", citations=5, year=2023)  # new paper

    res1 = QueryResult(
        query="COPD",
        provider="crossref",
        total_found=2,
        papers=[p1_s1, p2_s1],
        metrics=Metrics(total_papers=2, total_citations=30, h_index=2),
        search_time_seconds=1.0
    )
    res2 = QueryResult(
        query="COPD",
        provider="crossref",
        total_found=3,
        papers=[p1_s2, p2_s2, p3_s2],
        metrics=Metrics(total_papers=3, total_citations=40, h_index=3),
        search_time_seconds=1.1
    )

    id1 = save_snapshot(res1)
    id2 = save_snapshot(res2)

    diff = compute_snapshot_diff(id1, id2)
    assert diff["snapshot1_id"] == id1
    assert diff["snapshot2_id"] == id2
    assert len(diff["citation_deltas"]) == 1
    assert diff["citation_deltas"][0]["delta"] == 5
    assert len(diff["new_papers"]) == 1
    assert diff["new_papers"][0] == "Paper Gamma"
    assert diff["metrics_diff"]["total_citations_delta"] == 10
    assert diff["metrics_diff"]["h_index_delta"] == 1
