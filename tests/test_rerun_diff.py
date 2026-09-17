"""Packet 15 tests: rerun with lineage, legacy-refusal, identity-consistent diff."""

import json

from typer.testing import CliRunner

from pop_linux.cli import app
from pop_linux.execution_models import (
    AggregateCounts,
    ExecutionEnvelope,
    MetricsContext,
    ProviderCounts,
    ProviderReport,
    SearchFilters,
    SearchRequest,
)
from pop_linux.models import Metrics, Paper, QueryResult
from pop_linux.utils.history import save_execution, save_snapshot

runner = CliRunner()


def _envelope(query="rerun me", providers=("openalex",), doi="10.1000/r") -> ExecutionEnvelope:
    return ExecutionEnvelope(
        app_version="0.1.0-test",
        status="success",
        request=SearchRequest(query=query, providers=list(providers), limit=8,
                              filters=SearchFilters(year_from=2020), persistence_policy="explicit"),
        provider_reports=[
            ProviderReport(provider=p, status="success",
                           counts=ProviderCounts(matched=5, fetched=1, after_filter=1, returned=1))
            for p in providers
        ],
        counts=AggregateCounts(returned_raw=1, merged=1),
        papers=[Paper(title="Rerun Target", citations=10, doi=doi, year=2021)],
        metrics=Metrics(total_papers=1, total_citations=10),
        metrics_context=MetricsContext(paper_count=1, citation_selection_policy="max_observed"),
        elapsed_seconds=0.3,
    )


def _patch_engine(monkeypatch, result_envelope):
    import pop_linux.cli as cli

    captured: dict = {}

    def fake_execute(request):
        captured["request"] = request
        return result_envelope

    monkeypatch.setattr(cli, "execute_request", fake_execute)
    return captured


def test_rerun_reconstructs_exact_stored_request_and_records_lineage(tmp_path, monkeypatch):
    import pop_linux.utils.history as hist
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")

    original_id = save_execution(_envelope())

    rerun_envelope = _envelope()  # same request; new execution object
    rerun_envelope.persistence = type(rerun_envelope.persistence)(
        history_policy="explicit", snapshot_written=False, snapshot_id=None, exported=[], errors=[]
    )
    captured = _patch_engine(monkeypatch, rerun_envelope)

    res = runner.invoke(app, ["rerun", str(original_id)])
    assert res.exit_code == 0, res.stdout
    assert f"#{original_id}" in res.stdout

    # The exact stored request was re-executed
    sent = captured["request"]
    assert sent.query == "rerun me"
    assert sent.providers == ["openalex"]
    assert sent.limit == 8
    assert sent.filters.year_from == 2020

    # Lineage persisted: new row points at the original
    rows = {r["id"]: r["parent_snapshot_id"] for r in hist.list_snapshots(limit=10)}
    new_ids = [i for i, p in rows.items() if p == original_id]
    assert len(new_ids) == 1


def test_rerun_legacy_snapshot_refused_without_false_reconstruction(tmp_path, monkeypatch):
    import pop_linux.utils.history as hist
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")

    legacy_id = save_snapshot(
        QueryResult(
            query="old", provider="openalex", total_found=0, papers=[],
            metrics=Metrics(), search_time_seconds=0.1,
        )
    )
    res = runner.invoke(app, ["rerun", str(legacy_id)])
    assert res.exit_code == 1
    assert "cannot be reconstructed" in res.stdout


def test_rerun_missing_snapshot_errors(tmp_path, monkeypatch):
    import pop_linux.utils.history as hist
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    res = runner.invoke(app, ["rerun", "999"])
    assert res.exit_code == 1
    assert "does not exist" in res.stdout


def test_machine_rerun_emits_envelope_with_lineage(tmp_path, monkeypatch):
    import pop_linux.utils.history as hist
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")

    original_id = save_execution(_envelope())
    rerun_envelope = _envelope()
    _patch_engine(monkeypatch, rerun_envelope)

    res = runner.invoke(app, ["--machine", "rerun", str(original_id)])
    assert res.exit_code == 0
    data = json.loads(res.stdout)  # stdout purity contract holds for rerun
    assert data["schema"] == "pop-linux.execution/v1"
    assert data["persistence"]["snapshot_written"] is True
    assert data["persistence"]["snapshot_id"] > original_id
    assert data["persistence"]["history_policy"] == "explicit"


def test_machine_rerun_legacy_snapshot_is_structured_error(tmp_path, monkeypatch):
    import pop_linux.utils.history as hist
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")

    legacy_id = save_snapshot(
        QueryResult(
            query="old", provider="openalex", total_found=0, papers=[],
            metrics=Metrics(), search_time_seconds=0.1,
        )
    )
    res = runner.invoke(app, ["--machine", "rerun", str(legacy_id)])
    assert res.exit_code == 1
    data = json.loads(res.stdout)
    assert any(e["code"] == "RERUN_UNAVAILABLE" for e in data["errors"])


def test_diff_command_reports_ambiguity_section(tmp_path, monkeypatch):
    import pop_linux.utils.history as hist
    from pop_linux.models import QueryResult
    monkeypatch.setattr(hist, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")

    twin1 = Paper(title="Ambiguous Study", citations=5, year=2021)
    twin2 = Paper(title="Ambiguous Studyy", citations=6, year=2021)
    id1 = save_snapshot(QueryResult(query="q", provider="openalex", total_found=2,
                                    papers=[twin1, twin2], metrics=Metrics(), search_time_seconds=0.1))
    id2 = save_snapshot(QueryResult(query="q", provider="openalex", total_found=1,
                                    papers=[Paper(title="Ambiguous Study", citations=9, year=2021)],
                                    metrics=Metrics(), search_time_seconds=0.2))

    res = runner.invoke(app, ["diff", str(id1), str(id2)])
    assert res.exit_code == 0
    assert "ambiguous" in res.stdout.lower()
