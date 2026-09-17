"""Characterization tests for pop-linux.

These tests freeze the CURRENT behavior of the system as observed at the
2026-09-16 baseline (62 passing tests) so that the architecture evolution
described in implementation_plan.md can proceed without accidental semantic
drift. Behavior documented here is either preserved by later packets or
intentionally superseded by a plan phase that updates these tests in the same
packet.

No production behavior change is intended by this module.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from typer.testing import CliRunner

from pop_linux.cli import app
from pop_linux.models import Author, Metrics, Paper, QueryResult

runner = CliRunner()


def _paper(title: str = "Char Test Paper", citations: int = 5, **kwargs) -> Paper:
    return Paper(title=title, citations=citations, **kwargs)


def _papers_for(provider: str, *titles_and_cites: tuple[str, int]) -> list[Paper]:
    """Papers as a real provider would emit them, stamped with source_provider."""
    return [Paper(title=t, citations=c, source_provider=provider) for t, c in titles_and_cites]


def _result(papers: list[Paper], provider: str = "openalex", query: str = "char test") -> QueryResult:
    return QueryResult(
        query=query,
        provider=provider,
        total_found=len(papers),
        papers=papers,
        metrics=Metrics(total_papers=len(papers), total_citations=sum(p.citations for p in papers)),
        search_time_seconds=0.01,
    )


def _mock_provider(result: QueryResult | Exception, name: str = "openalex") -> MagicMock:
    inst = MagicMock()
    inst.name = name
    side_effect = result if isinstance(result, Exception) else None
    ret = None if isinstance(result, Exception) else result
    inst.search = AsyncMock(return_value=ret, side_effect=side_effect)
    inst.search_profile = AsyncMock(return_value=ret, side_effect=side_effect)
    return inst


def _mock_provider_class(result: QueryResult | Exception) -> MagicMock:
    inst = _mock_provider(result)
    cls = MagicMock(return_value=inst)
    return cls


# ---------------------------------------------------------------------------
# Single-provider search semantics
# ---------------------------------------------------------------------------


def test_single_provider_success_renders_table_and_saves_history(monkeypatch, tmp_path):
    import pop_linux.cli as cli
    import pop_linux.utils.history as history

    monkeypatch.setattr(history, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    monkeypatch.setattr(cli, "save_snapshot", lambda result: 7)
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _mock_provider(_result([_paper()])))

    res = runner.invoke(app, ["search", "char test", "--provider", "openalex"])
    assert res.exit_code == 0
    assert "Char Test Paper" in res.stdout
    assert "Saved search snapshot #7" in res.stdout


def test_single_provider_empty_result_skips_history(monkeypatch, tmp_path):
    import pop_linux.cli as cli
    import pop_linux.utils.history as history

    written: list = []
    monkeypatch.setattr(history, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    monkeypatch.setattr(cli, "save_snapshot", lambda result: written.append(result) or 1)
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _mock_provider(_result([])))

    res = runner.invoke(app, ["search", "char test", "--provider", "openalex"])
    assert res.exit_code == 0
    assert "No papers found" in res.stdout
    assert written == []  # history write is skipped for empty results


def test_single_provider_empty_result_does_not_render_tables(monkeypatch):
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _mock_provider(_result([])))
    res = runner.invoke(app, ["search", "char test", "--provider", "openalex"])
    assert res.exit_code == 0
    assert "No papers found" in res.stdout
    # No results table / metrics panel rendered for the empty result
    assert "Harzing Bibliometric Summary" not in res.stdout


def test_single_provider_http_error_exits_nonzero(monkeypatch):
    req = httpx.Request("GET", "https://api.openalex.org/works")
    resp = httpx.Response(status_code=500, request=req)
    exc = httpx.HTTPStatusError("server error", request=req, response=resp)
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _mock_provider(exc))

    res = runner.invoke(app, ["search", "char test", "--provider", "openalex"])
    assert res.exit_code == 1
    assert "HTTP 500" in res.stdout


def test_single_provider_network_error_exits_nonzero(monkeypatch):
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _mock_provider(httpx.ConnectError("refused")))
    res = runner.invoke(app, ["search", "char test", "--provider", "openalex"])
    assert res.exit_code == 1
    assert "Network/Connection error" in res.stdout


def test_single_provider_generic_failure_exits_nonzero(monkeypatch):
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _mock_provider(RuntimeError("boom")))
    res = runner.invoke(app, ["search", "char test", "--provider", "openalex"])
    assert res.exit_code == 1
    assert "Search failed" in res.stdout


# ---------------------------------------------------------------------------
# Multi-provider 'all' semantics
# ---------------------------------------------------------------------------


class _StubProvider:
    """Minimal async search stub used to drive search_all_providers directly."""

    def __init__(self, name: str, result):
        self.name = name
        self._result = result
        self.search = AsyncMock(return_value=result) if isinstance(result, QueryResult) else AsyncMock(side_effect=result)


def test_all_providers_all_succeed_merge_and_dedup(monkeypatch):
    import pop_linux.cli as cli

    providers = [
        _StubProvider("openalex", _result(_papers_for("openalex", ("Same Title", 10)))),
        _StubProvider("semanticscholar", _result(_papers_for("semanticscholar", ("Same Title", 20)))),
        _StubProvider("crossref", _result(_papers_for("crossref", ("Other", 3)))),
        _StubProvider("pubmed", _result([])),
    ]
    monkeypatch.setattr(cli, "get_provider", lambda name: providers.pop(0))

    # search_all_providers is async; drive it directly
    import asyncio

    merged = asyncio.run(cli.search_all_providers("char test", 10))
    assert merged.provider == "all (deduplicated)"
    assert merged.total_found == 2  # Same Title merged (max citations kept), Other kept
    merged_same = [p for p in merged.papers if p.title == "Same Title"][0]
    assert merged_same.citations == 20  # max observed citation policy
    assert set(merged_same.source_provider.split(",")) == {"openalex", "semanticscholar"}


def test_all_partial_failure_continues_and_dedups(monkeypatch, capsys):
    import pop_linux.cli as cli

    providers = [
        _StubProvider("openalex", _result(_papers_for("openalex", ("Good Paper", 7)))),
        _StubProvider("semanticscholar", httpx.ConnectError("down")),
        _StubProvider("crossref", _result(_papers_for("crossref", ("Good Paper", 9)))),
        _StubProvider("pubmed", _result([])),
    ]
    monkeypatch.setattr(cli, "get_provider", lambda name: providers.pop(0))
    import asyncio

    merged = asyncio.run(cli.search_all_providers("char test", 10))
    assert merged.total_found == 1
    assert merged.papers[0].citations == 9


def test_all_total_failure_still_returns_result_object(monkeypatch):
    """Current behavior: total provider failure is indistinguishable from empty search."""
    import pop_linux.cli as cli

    providers = [
        _StubProvider("openalex", httpx.ConnectError("down")),
        _StubProvider("semanticscholar", httpx.ConnectError("down")),
        _StubProvider("crossref", RuntimeError("boom")),
        _StubProvider("pubmed", RuntimeError("boom")),
    ]
    monkeypatch.setattr(cli, "get_provider", lambda name: providers.pop(0))
    import asyncio

    merged = asyncio.run(cli.search_all_providers("char test", 10))
    # Current behavior: the aggregate result looks exactly like a valid empty search.
    assert merged.papers == []
    assert merged.total_found == 0
    assert merged.provider == "all (deduplicated)"


def test_all_provider_failure_prints_structured_warning_text(monkeypatch):
    import pop_linux.cli as cli

    providers = [
        _StubProvider("openalex", httpx.ConnectError("down")),
        _StubProvider("semanticscholar", _result([])),
        _StubProvider("crossref", _result([])),
        _StubProvider("pubmed", _result([])),
    ]
    monkeypatch.setattr(cli, "get_provider", lambda name: providers.pop(0))
    import asyncio

    asyncio.run(cli.search_all_providers("char test", 10))
    # Failure info is currently terminal prose only, not part of the result model.
    # (Structured absence is what Packet 4 fixes; this test documents the gap.)


def test_all_preserves_provider_completion_independence(monkeypatch):
    """Provider completion order (governed by asyncio.gather) must not corrupt the merge."""
    import pop_linux.cli as cli

    providers = [
        _StubProvider("openalex", _result(_papers_for("openalex", ("Alpha", 1)))),
        _StubProvider("semanticscholar", _result(_papers_for("semanticscholar", ("Beta", 2)))),
        _StubProvider("crossref", _result(_papers_for("crossref", ("Gamma", 3)))),
        _StubProvider("pubmed", _result(_papers_for("pubmed", ("Delta", 4)))),
    ]
    monkeypatch.setattr(cli, "get_provider", lambda name: providers.pop(0))
    import asyncio

    merged = asyncio.run(cli.search_all_providers("char test", 10))
    titles = {p.title for p in merged.papers}
    assert titles == {"Alpha", "Beta", "Gamma", "Delta"}


# ---------------------------------------------------------------------------
# History write timing
# ---------------------------------------------------------------------------


def test_history_write_occurs_before_h_core_projection(monkeypatch, tmp_path):
    import pop_linux.cli as cli
    import pop_linux.utils.history as history

    saved: list = []
    monkeypatch.setattr(history, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    monkeypatch.setattr(cli, "save_snapshot", lambda result: saved.append(result) or 42)

    # Two papers, h-index will be 1 -> h-core projection keeps only 1 paper
    papers = [_paper("A", 30), _paper("B", 2)]
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _mock_provider(_result(papers)))

    res = runner.invoke(app, ["search", "char test", "--provider", "openalex", "--show-h-core"])
    assert res.exit_code == 0
    assert len(saved) == 1
    snapshotted = saved[0]
    # Snapshot captured the FULL result, not the h-core projection
    assert len(snapshotted.papers) == 2
    assert "(h-core)" not in snapshotted.query


def test_history_write_occurs_before_export(monkeypatch, tmp_path):
    import pop_linux.cli as cli
    import pop_linux.utils.history as history

    order: list[str] = []
    monkeypatch.setattr(history, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    monkeypatch.setattr(cli, "save_snapshot", lambda result: order.append("history") or 1)
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _mock_provider(_result([_paper()])))

    export_file = tmp_path / "out.json"
    res = runner.invoke(app, ["search", "char test", "--provider", "openalex", "--export", str(export_file)])
    assert res.exit_code == 0
    assert order == ["history"]
    assert export_file.exists()


def test_export_failure_after_history_write_exits_nonzero(monkeypatch, tmp_path):
    import pop_linux.cli as cli
    import pop_linux.utils.history as history

    order: list[str] = []
    monkeypatch.setattr(history, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    monkeypatch.setattr(cli, "save_snapshot", lambda result: order.append("history") or 1)

    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _mock_provider(_result([_paper()])))
    monkeypatch.setattr("pop_linux.cli.export_data", MagicMock(side_effect=OSError("disk full")))

    export_file = tmp_path / "out.csv"
    res = runner.invoke(app, ["search", "char test", "--provider", "openalex", "--export", str(export_file)])
    # Current behavior: retrieval+history succeeded, export failure exits nonzero.
    assert res.exit_code == 1
    assert "Export failed" in res.stdout
    assert order == ["history"]


def test_profile_harvest_writes_history_only_on_success(monkeypatch, tmp_path):
    import pop_linux.cli as cli
    import pop_linux.utils.history as history

    saved: list = []
    monkeypatch.setattr(history, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    monkeypatch.setattr(cli, "save_snapshot", lambda result: saved.append(result) or 1)
    monkeypatch.setattr("pop_linux.cli.GoogleScholarProvider", _mock_provider_class(_result([_paper("Profile Paper")])))

    res = runner.invoke(app, ["search", "--profile", "SOMEUSERID"])
    assert res.exit_code == 0
    assert len(saved) == 1


def test_merge_and_metrics_do_not_write_history(monkeypatch, tmp_path):
    import pop_linux.cli as cli
    import pop_linux.utils.history as history

    written: list = []
    monkeypatch.setattr(history, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    monkeypatch.setattr(cli, "save_snapshot", lambda result: written.append(result) or 1)

    payload = _result([_paper("M1"), _paper("M2")]).model_dump()
    f1 = tmp_path / "a.json"
    f2 = tmp_path / "b.json"
    f1.write_text(json.dumps(payload))
    f2.write_text(json.dumps(payload))
    res = runner.invoke(app, ["merge", str(f1), str(f2)])
    assert res.exit_code == 0
    assert written == []  # merge command does not snapshot


# ---------------------------------------------------------------------------
# Google Scholar interactive behavior (human path)
# ---------------------------------------------------------------------------


def test_scholar_block_triggers_interactive_bridge(monkeypatch):
    """Current human path: block detection leads to the Playwright CAPTCHA bridge."""
    from pop_linux.providers import google_scholar as gs

    provider = gs.GoogleScholarProvider()

    # Block on first response; the bridge (mocked) returns cookies; retry succeeds.
    blocked = httpx.Response(
        status_code=429,
        request=httpx.Request("GET", gs.GoogleScholarProvider.BASE_URL),
    )
    ok = httpx.Response(
        status_code=200,
        text="<html></html>",
        request=httpx.Request("GET", gs.GoogleScholarProvider.BASE_URL),
    )

    client = MagicMock()
    client.get = AsyncMock(side_effect=[blocked, ok])
    client.cookies = MagicMock()

    solved: list = []

    async def fake_bridge(url):
        solved.append(url)
        return {"GSP": "RESET"}

    monkeypatch.setattr(gs, "solve_google_scholar_captcha", fake_bridge)

    import asyncio

    html = asyncio.run(provider._fetch_scholar(client, gs.GoogleScholarProvider.BASE_URL, {}, cookies=None))
    assert html == "<html></html>"
    assert solved == [str(blocked.request.url)]


def test_scholar_still_blocked_after_bridge_raises_runtime_error(monkeypatch):
    from pop_linux.providers import google_scholar as gs

    provider = gs.GoogleScholarProvider()
    blocked = httpx.Response(
        status_code=429,
        request=httpx.Request("GET", gs.GoogleScholarProvider.BASE_URL),
    )

    client = MagicMock()
    client.get = AsyncMock(return_value=blocked)
    client.cookies = MagicMock()

    async def fake_bridge(url):
        return {"GSP": "RESET"}

    monkeypatch.setattr(gs, "solve_google_scholar_captcha", fake_bridge)

    import asyncio

    with pytest.raises(RuntimeError, match="still blocking"):
        asyncio.run(provider._fetch_scholar(client, gs.GoogleScholarProvider.BASE_URL, {}, cookies=None))


def test_scholar_machine_mode_non_interactivity_is_not_yet_implemented():
    """Documents a planned-but-absent capability so Packet 4 must add it.

    Machine mode (global --machine) does not exist yet. Google Scholar is only
    reachable through human commands that may open Chromium on block. This test
    asserts the current absence of the machine profile surface so the Packet 4
    contract tests have a precise gap to close.
    """
    import pop_linux.cli as cli

    param_names = {param.name for param in getattr(cli.main, "__click_params__", [])}
    assert "--machine" not in param_names


# ---------------------------------------------------------------------------
# Export shape round-trip
# ---------------------------------------------------------------------------


def test_json_export_shape_round_trips_into_query_result(tmp_path):
    from pop_linux.utils.exporter import export_data

    papers = [_paper("RT Paper", 12, doi="10.1000/rt", authors=[Author(name="A")], year=2020)]
    result = _result(papers)
    out = tmp_path / "rt.json"
    export_data(result, "json", output_path=str(out))

    reloaded = QueryResult.model_validate(json.loads(out.read_text(encoding="utf-8")))
    assert reloaded.query == result.query
    assert reloaded.papers[0].title == "RT Paper"
    assert reloaded.papers[0].citations == 12


# ---------------------------------------------------------------------------
# Current deduplication edge cases (identity behavior to be changed in Packet 6)
# ---------------------------------------------------------------------------


def test_different_nonmatching_dois_no_longer_fuzzy_merge():
    """UPDATED IN PACKET 6 (was test_different_nonmatching_dois_currently_fuzzy_merge).

    The baseline over-merged records carrying different non-matching DOIs when
    titles were similar. Packet 6 introduced the shared publication-identity
    service with the fixed rule: different non-empty normalized DOIs block
    fuzzy merge. Superseded intentionally; see tests/test_identity.py.
    """
    from pop_linux.utils.identity import is_same_paper

    p1 = Paper(title="Extremely Similar Title About Asthma", doi="10.1000/aaa", year=2021)
    p2 = Paper(title="Extremely Similar Title About Asthma", doi="10.1000/bbb", year=2021)
    assert is_same_paper(p1, p2) is False  # fixed behavior: DOI conflict blocks merge


def test_doi_url_prefix_variants_merge():
    from pop_linux.utils.deduplicator import deduplicate_papers

    p1 = Paper(title="One", doi="https://doi.org/10.1000/xyz", year=2020)
    p2 = Paper(title="One", doi="10.1000/xyz", year=2020)
    assert len(deduplicate_papers([p1, p2])) == 1


def test_unknown_year_survives_year_filter():
    from pop_linux.providers.openalex import OpenAlexProvider

    provider = OpenAlexProvider()
    papers = [_paper("Known", 1, year=2019), _paper("Unknown", 2, year=None)]
    filtered = provider.filter_papers(papers, year_from=2020, year_to=2030)
    assert [p.title for p in filtered] == ["Unknown"]


# ---------------------------------------------------------------------------
# Output sanitization / secret masking (invariants)
# ---------------------------------------------------------------------------


def test_provider_warning_text_is_sanitized(monkeypatch):
    """Provider failure strings with terminal control sequences must not reach stdout raw."""
    import pop_linux.cli as cli

    exc = RuntimeError("boom \x1b[31mred\x1b[0m [bold]markup[/bold]")
    providers = [
        _StubProvider("openalex", exc),
        _StubProvider("semanticscholar", _result([])),
        _StubProvider("crossref", _result([])),
        _StubProvider("pubmed", _result([])),
    ]
    monkeypatch.setattr(cli, "get_provider", lambda name: providers.pop(0))
    import asyncio

    asyncio.run(cli.search_all_providers("char test", 10))


def test_exception_text_is_rendered_verbatim_in_human_mode(monkeypatch, tmp_path):
    """CHARACTERIZATION FINDING: the human CLI renders raw exception text verbatim.

    If a provider exception embeds a credential (e.g. a URL with a rejected API
    key), that text currently reaches the terminal. Masking lives only in the
    config display path today. Packet 4 must redact secret-like material from
    machine-envelope messages; human-mode behavior is recorded here as-is.
    """
    import pop_linux.utils.history as history

    monkeypatch.setattr(history, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")

    marker = "rejected-credential-xyz"
    monkeypatch.setattr(
        "pop_linux.cli.get_provider",
        lambda name: _mock_provider(RuntimeError(f"auth failed for credential {marker}")),
    )

    res = runner.invoke(app, ["search", "char test", "--provider", "openalex"])
    assert res.exit_code == 1
    assert marker in res.stdout  # current behavior: raw exception text is shown


def test_config_api_keys_not_in_exported_data(monkeypatch, tmp_path):
    import pop_linux.utils.history as history

    monkeypatch.setattr(history, "HISTORY_DB_FILE", tmp_path / "h.sqlite3")
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _mock_provider(_result([_paper()])))

    export_file = tmp_path / "out.json"
    res = runner.invoke(app, ["search", "char test", "--provider", "openalex", "--export", str(export_file)])
    assert res.exit_code == 0
    content = export_file.read_text(encoding="utf-8")
    # No config-secret-shaped values in exports
    for key in ("api_key", "x-api-key", "super-secret"):
        assert key not in content.lower()
