"""Desktop integration boundaries without a Qt dependency."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from pop_linux import execution
from pop_linux.execution_models import SearchRequest
from pop_linux.models import Paper
from pop_linux.providers.base import ProviderFetchResult


def test_desktop_engine_matches_sync_and_preserves_linux_paths(monkeypatch, tmp_path):
    from pop_linux import config
    from pop_linux.config import application_directory
    from pop_linux.gui.service import export_result, make_request, result_from_envelope
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.toml")

    assert application_directory("linux", tmp_path, {}) == tmp_path / ".config/pop_linux"
    assert application_directory("darwin", tmp_path, {}) == tmp_path / "Library/Application Support/pop_linux"
    assert application_directory("win32", tmp_path, {"APPDATA": str(tmp_path / "Roaming")}) == tmp_path / "Roaming/pop_linux"
    provider = AsyncMock()
    provider.name = "openalex"
    provider.fetch.return_value = ProviderFetchResult(
        papers=[Paper(title="Research", citations=12, doi="10.1/test")],
        returned_count=1, fetched_count=1, pages_or_requests=1,
    )
    monkeypatch.setattr(execution, "resolve_providers", lambda request: [provider])
    request = make_request(" Research ", "openalex", 25, {"year_from": 2020, "min_citations": 3})
    assert request.query == "Research" and request.filters.year_from == 2020
    sync = execution.execute_request(request)
    asynchronous = asyncio.run(execution.execute_request_async(request))
    assert asynchronous.papers == sync.papers
    assert asynchronous.metrics == sync.metrics
    assert asynchronous.metrics.h_index == 1 and asynchronous.metrics.total_citations == 12
    from typer.testing import CliRunner
    from pop_linux.cli import app
    cli = CliRunner().invoke(app, ["--machine", "search", "Research", "--provider", "openalex", "--limit", "25",
                                   "--year-from", "2020", "--min-citations", "3", "--no-history"])
    assert cli.exit_code == 0, cli.output
    wire = json.loads(cli.stdout)
    assert wire["papers"] == [paper.model_dump() for paper in asynchronous.papers]
    assert wire["metrics"] == asynchronous.metrics.model_dump()
    assert make_request("query", "all", 25, {}).providers == ["openalex", "semanticscholar", "crossref", "pubmed"]
    from pop_linux.providers.google_scholar import GoogleScholarProvider
    from pop_linux.models import QueryResult
    scholar = GoogleScholarProvider()
    profile_result = QueryResult(query="profile", provider="google_scholar", papers=[Paper(title="Profile paper", citations=7)], total_found=1)
    monkeypatch.setattr(scholar, "search_profile", AsyncMock(return_value=profile_result))
    monkeypatch.setattr(scholar, "_fetch_scholar", AsyncMock(return_value="<html></html>"))
    profile_request = make_request("", "google_scholar", 25, {"year_from": 2020, "author": "Somebody"}, "researcher-id")
    profile_fetch = asyncio.run(scholar.fetch(profile_request))
    assert profile_fetch.papers[0].title == "Profile paper"
    modes, warnings = execution._resolve_filter_modes("google_scholar", profile_request)
    assert modes == {"year_from": "post_filter", "author": "unsupported"}
    assert warnings[0].code == "FILTER_UNSUPPORTED"
    result = result_from_envelope(asynchronous)
    for extension in ("json", "csv", "bib", "ris"):
        output = tmp_path / f"research.{extension}"
        export_result(result, output, result.papers)
        assert output.stat().st_size > 0
    report = {"status": asynchronous.status, "papers": len(result.papers), "h_index": result.metrics.h_index}
    (tmp_path / "engine-artifact.json").write_text(json.dumps(report))


def test_desktop_cancellation_stops_fetch_and_invalid_filters_fail(monkeypatch, tmp_path):
    from pop_linux.gui.service import make_request, safe_external_url

    with pytest.raises(ValueError):
        make_request("", "openalex", 50, {})
    with pytest.raises(ValueError):
        make_request("test", "openalex", 50, {"year_from": 2025, "year_to": 2020})
    assert safe_external_url(Paper(title="Untrusted link", url="https://[invalid")) is None

    async def scenario():
        started = asyncio.Event()
        stopped = asyncio.Event()

        async def fetch(request):
            started.set()
            try:
                await asyncio.sleep(30)
            finally:
                stopped.set()

        provider = AsyncMock()
        provider.name = "openalex"
        provider.fetch.side_effect = fetch
        monkeypatch.setattr(execution, "resolve_providers", lambda request: [provider])
        task = asyncio.create_task(execution.execute_request_async(SearchRequest(query="cancel", providers=["openalex"], limit=5)))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()

    asyncio.run(scenario())
    (tmp_path / "cancellation-artifact.json").write_text('{"cancelled_fetch_stopped": true}')
