"""Machine execution profile contract tests (Packet 4).

These treat stdout purity, exit codes, non-interactivity, persistence policy,
and secret redaction as a public machine contract.
"""

import json
from unittest.mock import AsyncMock, MagicMock

from typer.testing import CliRunner

from pop_linux.cli import _redact_secrets, app
from pop_linux.models import Metrics, Paper, QueryResult

runner = CliRunner(mix_stderr=False) if "mix_stderr" in CliRunner.__init__.__code__.co_varnames else CliRunner()


def _paper(title: str = "Machine Paper", citations: int = 5, provider: str = "openalex") -> Paper:
    return Paper(title=title, citations=citations, source_provider=provider)


def _qr(papers: list[Paper], total_found: int | None = None) -> QueryResult:
    return QueryResult(
        query="q",
        provider="stub",
        total_found=total_found if total_found is not None else len(papers),
        papers=papers,
        metrics=Metrics(total_papers=len(papers), total_citations=sum(p.citations for p in papers)),
        search_time_seconds=0.01,
    )


def _patch_registry(monkeypatch, registry: dict[str, object]):
    import pop_linux.execution as em

    classes = {k: type(f"Prov_{k}", (), {"name": k}) for k in registry}
    monkeypatch.setattr(em, "PROVIDERS", classes)

    def make(key: str):
        inst = registry[key]
        return inst

    def resolve(request):
        from pop_linux.execution_models import SearchRequest  # noqa: F401

        expanded = []
        for name in request.providers:
            k = name.lower()
            if k == "all":
                expanded.extend([x for x in registry if x != "google_scholar"])
            else:
                expanded.append(k)
        seen: list[str] = []
        for k in expanded:
            if k not in seen:
                seen.append(k)
        return [registry[k] for k in seen]

    monkeypatch.setattr(em, "resolve_providers", resolve)


def _provider(name: str, result) -> MagicMock:
    from pop_linux.providers.base import ProviderFetchResult

    inst = MagicMock()
    inst.name = name
    if isinstance(result, Exception):
        inst.fetch = AsyncMock(side_effect=result)
        inst.search = AsyncMock(side_effect=result)
        return inst
    fetch_result = ProviderFetchResult(
        papers=result.papers,
        matched_count=result.total_found,
        fetched_count=len(result.papers),
        returned_count=len(result.papers),
        elapsed_seconds=result.search_time_seconds,
        pages_or_requests=1,
    )
    inst.fetch = AsyncMock(return_value=fetch_result)
    inst.search = AsyncMock(return_value=result)
    return inst


def _parse_envelope(res) -> dict:
    """Parses machine stdout as exactly one JSON document (contract)."""
    return json.loads(res.stdout)


# ---------------------------------------------------------------------------
# stdout purity
# ---------------------------------------------------------------------------


def test_machine_search_stdout_is_exactly_one_json_document(monkeypatch, tmp_path):
    import pop_linux.cli as cli

    monkeypatch.setattr(cli, "save_snapshot", lambda *a, **k: 1)
    _patch_registry(monkeypatch, {"openalex": _provider("openalex", _qr([_paper()]))})

    res = runner.invoke(app, ["--machine", "search", "asthma", "--provider", "openalex", "--limit", "20"])
    assert res.exit_code == 0

    data = _parse_envelope(res)  # must parse without preprocessing
    assert data["schema"] == "pop-linux.execution/v1"
    assert data["status"] == "success"
    assert data["papers"][0]["title"] == "Machine Paper"
    # No Rich/ANSI contamination anywhere in stdout
    assert "\x1b" not in res.stdout
    assert "Harvest" not in res.stdout


def test_machine_output_has_no_progress_or_prose(monkeypatch):
    import pop_linux.cli as cli

    monkeypatch.setattr(cli, "save_snapshot", lambda *a, **k: 1)
    _patch_registry(monkeypatch, {"openalex": _provider("openalex", _qr([]))})

    res = runner.invoke(app, ["--machine", "search", "asthma", "--provider", "openalex"])
    assert res.exit_code == 0
    data = _parse_envelope(res)
    assert data["status"] == "empty"
    for forbidden in ("Initiating", "Searching", "Spinner", "progress", "No papers found"):
        assert forbidden not in res.stdout


# ---------------------------------------------------------------------------
# Exit-code contract
# ---------------------------------------------------------------------------


def test_machine_partial_failure_exits_zero(monkeypatch):
    _patch_registry(
        monkeypatch,
        {
            "openalex": _provider("openalex", _qr([_paper("Good", 3)])),
            "crossref": _provider("crossref", ConnectionError("down")),
        },
    )
    res = runner.invoke(app, ["--machine", "search", "q", "--provider", "all", "--limit", "5"])
    data = _parse_envelope(res)
    assert res.exit_code == 0
    assert data["status"] == "partial"
    failed = [r for r in data["provider_reports"] if r["status"] == "error"]
    assert len(failed) == 1
    assert failed[0]["provider"] == "crossref"


def test_machine_total_failure_is_error_and_exits_nonzero(monkeypatch):
    _patch_registry(
        monkeypatch,
        {
            "openalex": _provider("openalex", ConnectionError("down")),
            "crossref": _provider("crossref", RuntimeError("boom")),
        },
    )
    res = runner.invoke(app, ["--machine", "search", "q", "--provider", "all", "--limit", "5"])
    data = _parse_envelope(res)
    assert res.exit_code == 1
    assert data["status"] == "error"


def test_machine_empty_result_exits_zero(monkeypatch):
    _patch_registry(monkeypatch, {"openalex": _provider("openalex", _qr([]))})
    res = runner.invoke(app, ["--machine", "search", "q", "--provider", "openalex"])
    data = _parse_envelope(res)
    assert res.exit_code == 0
    assert data["status"] == "empty"


def test_machine_usage_error_still_exit_two(monkeypatch):
    # Missing query without profile is a usage error handled by the CLI contract
    res = runner.invoke(app, ["--machine", "search"])
    assert res.exit_code != 0


# ---------------------------------------------------------------------------
# Non-interactivity
# ---------------------------------------------------------------------------


def test_machine_google_scholar_refused_without_browser(monkeypatch):
    """Machine mode must refuse Scholar rather than ever launch Chromium."""
    launched: list = []

    import pop_linux.providers.google_scholar as gs

    monkeypatch.setattr(gs, "solve_google_scholar_captcha", lambda url: launched.append(url))

    res = runner.invoke(app, ["--machine", "search", "q", "--provider", "google_scholar"])
    assert res.exit_code == 1
    data = _parse_envelope(res)
    assert data["status"] == "error"
    assert any(e["code"] == "INTERACTION_FORBIDDEN" for e in data["errors"])
    assert launched == []  # Playwright bridge never invoked


def test_machine_profile_harvest_refused(monkeypatch):
    res = runner.invoke(app, ["--machine", "search", "--profile", "SOMEUSER"])
    assert res.exit_code == 1
    data = _parse_envelope(res)
    assert any(e["code"] == "INTERACTION_FORBIDDEN" for e in data["errors"])


# ---------------------------------------------------------------------------
# Persistence policy
# ---------------------------------------------------------------------------


def test_machine_search_does_not_write_history_by_default(monkeypatch, tmp_path):
    import pop_linux.cli as cli

    written: list = []
    monkeypatch.setattr(cli, "save_snapshot", lambda result: written.append(result) or 1)
    _patch_registry(monkeypatch, {"openalex": _provider("openalex", _qr([_paper()]))})

    res = runner.invoke(app, ["--machine", "search", "q", "--provider", "openalex"])
    assert res.exit_code == 0
    assert written == []
    data = _parse_envelope(res)
    assert data["persistence"]["snapshot_written"] is False
    assert data["request"]["persistence_policy"] == "off"


def test_machine_explicit_save_history_writes_and_reports(monkeypatch, tmp_path):
    import pop_linux.cli as cli

    monkeypatch.setattr(cli, "save_snapshot", lambda result: 77)
    _patch_registry(monkeypatch, {"openalex": _provider("openalex", _qr([_paper()]))})

    res = runner.invoke(app, ["--machine", "search", "q", "--provider", "openalex", "--save-history"])
    assert res.exit_code == 0
    data = _parse_envelope(res)
    assert data["persistence"]["snapshot_written"] is True
    assert data["persistence"]["snapshot_id"] == 77
    assert data["request"]["persistence_policy"] == "explicit"


def test_machine_explicit_export_writes_and_reports(monkeypatch, tmp_path):
    import pop_linux.cli as cli

    monkeypatch.setattr(cli, "save_snapshot", lambda *a, **k: 1)
    _patch_registry(monkeypatch, {"openalex": _provider("openalex", _qr([_paper("Exported Paper", 4)]))})

    out = tmp_path / "out.json"
    res = runner.invoke(app, ["--machine", "search", "q", "--provider", "openalex", "--export", str(out)])
    assert res.exit_code == 0
    data = _parse_envelope(res)
    assert data["persistence"]["exported"] == [{"format": "json", "path": str(out)}]
    content = json.loads(out.read_text())
    assert content["papers"][0]["title"] == "Exported Paper"
    # Export remains a QueryResult projection, not the envelope
    assert "schema" not in content


def test_machine_export_failure_reported_not_fatal(monkeypatch, tmp_path):
    import pop_linux.cli as cli

    monkeypatch.setattr(cli, "save_snapshot", lambda *a, **k: 1)
    _patch_registry(monkeypatch, {"openalex": _provider("openalex", _qr([_paper()]))})

    res = runner.invoke(
        app,
        ["--machine", "search", "q", "--provider", "openalex", "--export", "/proc/nonexistent-dir/out.json"],
    )
    data = _parse_envelope(res)
    assert data["status"] == "success"  # retrieval result preserved
    assert any(e["code"] == "EXPORT_FAILED" for e in data["persistence"]["errors"])


# ---------------------------------------------------------------------------
# Secret redaction in machine output
# ---------------------------------------------------------------------------


def test_redact_secrets_masks_credential_patterns():
    assert "sk-live-abc123" not in _redact_secrets("api_key=sk-live-abc123 failed")
    assert "Bearer abc.def.ghi" not in _redact_secrets("auth: Bearer abc.def.ghi")
    assert "[REDACTED]" in _redact_secrets("x-api-key: 12345")


def test_machine_error_message_redacts_secrets(monkeypatch):
    _patch_registry(
        monkeypatch,
        {
            "openalex": _provider("openalex", RuntimeError("auth failed api_key=supersecret123")),
            "crossref": _provider("crossref", _qr([_paper("OK", 2)])),
        },
    )
    res = runner.invoke(app, ["--machine", "search", "q", "--provider", "all", "--limit", "5"])
    data = _parse_envelope(res)
    serialized = json.dumps(data)
    assert "supersecret123" not in serialized
    # The message text must be redacted, not dropped
    assert "[REDACTED]" in serialized


# ---------------------------------------------------------------------------
# Envelope content contracts
# ---------------------------------------------------------------------------


def test_machine_envelope_carries_resolved_request_and_provider_reports(monkeypatch):
    _patch_registry(monkeypatch, {"openalex": _provider("openalex", _qr([_paper("A", 9)]))})

    res = runner.invoke(
        app,
        ["--machine", "search", "asthma", "--provider", "openalex", "--limit", "7", "--year-from", "2020", "--min-citations", "2"],
    )
    data = _parse_envelope(res)
    req = data["request"]
    assert req["query"] == "asthma"
    assert req["providers"] == ["openalex"]
    assert req["limit"] == 7
    assert req["filters"]["year_from"] == 2020
    assert req["filters"]["min_citations"] == 2
    assert req["interaction_policy"] == "never"
    assert req["persistence_policy"] == "off"

    assert data["counts"]["merged"] == 1
    assert data["metrics_context"]["citation_selection_policy"] == "max_observed"
    assert data["elapsed_seconds"] >= 0


def test_machine_counted_provider_reports_present(monkeypatch):
    _patch_registry(
        monkeypatch,
        {
            "openalex": _provider("openalex", _qr([_paper("A", 9)], total_found=42)),
            "crossref": _provider("crossref", _qr([_paper("B", 3)], total_found=17)),
        },
    )
    res = runner.invoke(app, ["--machine", "search", "q", "--provider", "all", "--limit", "5"])
    data = _parse_envelope(res)
    reports = {r["provider"]: r for r in data["provider_reports"]}
    assert reports["openalex"]["counts"]["matched"] == 42
    assert reports["crossref"]["counts"]["matched"] == 17
    assert reports["openalex"]["status"] == "success"
    assert data["counts"]["returned_raw"] == 2
    assert data["counts"]["merged"] == 2


def test_machine_schema_constant_is_stable():
    from pop_linux.execution_models import EXECUTION_SCHEMA

    assert EXECUTION_SCHEMA == "pop-linux.execution/v1"


# ---------------------------------------------------------------------------
# Human profile unchanged
# ---------------------------------------------------------------------------


def test_human_search_still_renders_tables(monkeypatch, tmp_path):
    import pop_linux.cli as cli

    monkeypatch.setattr(cli, "save_snapshot", lambda result: 1)
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _provider("openalex", _qr([_paper("Human Paper")])))

    res = runner.invoke(app, ["search", "q", "--provider", "openalex"])
    assert res.exit_code == 0
    assert "Human Paper" in res.stdout
    assert "Search Results" in res.stdout


def test_human_no_history_flag_suppresses_snapshot(monkeypatch, tmp_path):
    import pop_linux.cli as cli

    written: list = []
    monkeypatch.setattr(cli, "save_snapshot", lambda result: written.append(result) or 1)
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _provider("openalex", _qr([_paper("H2")])))

    res = runner.invoke(app, ["search", "q", "--provider", "openalex", "--no-history"])
    assert res.exit_code == 0
    assert written == []
    assert "suppressed" in res.stdout


def test_human_save_history_flag_forces_snapshot(monkeypatch, tmp_path):
    import pop_linux.cli as cli

    written: list = []
    monkeypatch.setattr(cli, "save_snapshot", lambda result: written.append(result) or 5)
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _provider("openalex", _qr([])))

    # Empty result still skips snapshot (existing semantic), so use a paper
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _provider("openalex", _qr([_paper("H3")])))
    res = runner.invoke(app, ["search", "q", "--provider", "openalex", "--save-history"])
    assert res.exit_code == 0
    assert len(written) == 1
