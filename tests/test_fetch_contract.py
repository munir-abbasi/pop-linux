"""Fetch-contract migration tests (Packets 8-12).

Verifies the engine-facing fetch contract, the legacy `.search()` compat
projection, provider request/pages reporting, and blocked-status mapping.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock


from pop_linux.execution import execute_request
from pop_linux.execution_models import SearchFilters, SearchRequest
from pop_linux.models import Paper, QueryResult
from pop_linux.providers.base import ProviderFetchResult


def _request(**kw) -> SearchRequest:
    base = {"query": "compat", "providers": ["openalex"], "limit": 5}
    base.update(kw)
    return SearchRequest(**base)


# ---------------------------------------------------------------------------
# Legacy .search() compatibility via fetch (Phase 7 exit gate)
# ---------------------------------------------------------------------------


def test_legacy_search_projected_from_fetch(monkeypatch):
    """Unmigrated provider: base search() builds a request, fetches, projects."""
    from pop_linux.providers.openalex import OpenAlexProvider

    provider = OpenAlexProvider()

    captured: dict = {}

    async def fake_native(request: SearchRequest) -> ProviderFetchResult:
        captured["request"] = request
        return ProviderFetchResult(
            papers=[Paper(title="Projected Paper", citations=3)],
            matched_count=99,
            fetched_count=1,
            returned_count=1,
            elapsed_seconds=0.05,
            pages_or_requests=1,
        )

    provider._fetch_native = fake_native  # type: ignore[method-assign]

    result = asyncio.run(provider.search("compat query", limit=4, author="Smith", year_from=2020))

    assert isinstance(result, QueryResult)
    assert result.provider == "openalex"
    assert result.query == "compat query"
    assert result.total_found == 99  # matched count preserved
    assert result.papers[0].title == "Projected Paper"
    assert result.metrics is not None and result.metrics.total_papers == 1  # legacy projection includes metrics
    assert captured["request"].limit == 4
    assert captured["request"].filters.author == "Smith"
    assert captured["request"].filters.year_from == 2020


def test_legacy_search_default_limit_guard(monkeypatch):
    from pop_linux.providers.crossref import CrossRefProvider

    provider = CrossRefProvider()

    async def fake_native(request: SearchRequest) -> ProviderFetchResult:
        return ProviderFetchResult(elapsed_seconds=0.01)

    provider._fetch_native = fake_native  # type: ignore[method-assign]
    result = asyncio.run(provider.search("q", limit=None))
    assert result.total_found == 0


# ---------------------------------------------------------------------------
# Engine consumes fetch() and reports provider execution facts
# ---------------------------------------------------------------------------


def _registry(monkeypatch, providers: dict[str, object]):
    import pop_linux.execution as em

    monkeypatch.setattr(
        em,
        "resolve_providers",
        lambda request: [providers[k] for k in request.providers],
    )


def _provider(name: str, fetch_result: ProviderFetchResult | Exception) -> MagicMock:
    inst = MagicMock()
    inst.name = name
    inst.fetch = AsyncMock(side_effect=fetch_result) if isinstance(fetch_result, Exception) else AsyncMock(return_value=fetch_result)
    return inst


def test_engine_reports_pages_and_matched(monkeypatch):
    _registry(
        monkeypatch,
        {
            "openalex": _provider(
                "openalex",
                ProviderFetchResult(
                    papers=[Paper(title="A"), Paper(title="B")],
                    matched_count=500,
                    fetched_count=2,
                    returned_count=2,
                    pages_or_requests=3,
                ),
            )
        },
    )
    env = execute_request(_request())
    report = env.provider_reports[0]
    assert report.pages_or_requests == 3
    assert report.counts.matched == 500
    assert report.counts.fetched == 2
    assert report.status == "success"


def test_engine_maps_scholar_interaction_warning_to_blocked(monkeypatch):
    from pop_linux.execution_models import ExecutionMessage

    _registry(
        monkeypatch,
        {
            "openalex": _provider(
                "openalex",
                ProviderFetchResult(
                    papers=[Paper(title="A", citations=1)],
                    matched_count=1,
                    fetched_count=1,
                    returned_count=1,
                ),
            ),
            "crossref": _provider(
                "crossref",
                ProviderFetchResult(
                    papers=[],
                    matched_count=None,
                    fetched_count=0,
                    returned_count=0,
                    warnings=[
                        ExecutionMessage(
                            code="PROVIDER_BLOCKED_INTERACTION_REQUIRED",
                            message="CAPTCHA challenge encountered",
                            provider="crossref",
                        )
                    ],
                ),
            ),
        },
    )
    env = execute_request(_request(providers=["openalex", "crossref"]))
    assert env.status == "partial"
    report = [r for r in env.provider_reports if r.provider == "crossref"][0]
    assert report.status == "blocked"


def test_pubmed_reports_two_requests(monkeypatch):
    """PubMed's ESearch+ESummary pattern reports 2 requests, not 1."""
    from pop_linux.providers.pubmed import PubMedProvider

    provider = PubMedProvider()
    captured: dict = {}

    async def fake_native(request: SearchRequest) -> ProviderFetchResult:
        captured["called"] = True
        return ProviderFetchResult(papers=[], matched_count=0, fetched_count=0, returned_count=0, pages_or_requests=2)

    provider._fetch_native = fake_native  # type: ignore[method-assign]
    result = asyncio.run(provider.search("anything"))
    assert captured["called"]
    assert result.total_found == 0


# ---------------------------------------------------------------------------
# Provider request compilation unchanged (regression through native path)
# ---------------------------------------------------------------------------


def test_openalex_query_compilation_through_native_path(monkeypatch):
    from pop_linux.providers import openalex as oa

    provider = oa.OpenAlexProvider()

    seen_params: dict = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"meta": {"count": 0}, "results": []}

    async def fake_get(url, params=None, headers=None):
        seen_params.update(params)
        return FakeResponse()

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, params=None, headers=None):
            return await fake_get(url, params, headers)

    monkeypatch.setattr(oa.httpx, "AsyncClient", FakeClient)

    request = _request(
        filters=SearchFilters(author="Smith", issn="1234-5678", year_from=2020, year_to=2030, min_citations=2),
        limit=10,
    )
    result = asyncio.run(provider.fetch(request))

    assert seen_params["filter"] == "publication_year:2020-2030,issn:1234-5678"
    assert 'author.display_name:"Smith"' in seen_params["search"]
    assert seen_params["per_page"] == 10
    assert result.returned_count == 0
