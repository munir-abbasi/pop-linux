"""Packet 13 completion tests: Semantic Scholar pagination and filter-mode reporting."""

import asyncio
from unittest.mock import AsyncMock, MagicMock


from pop_linux.execution import execute_request
from pop_linux.execution_models import SearchFilters, SearchRequest
from pop_linux.models import Paper
from pop_linux.providers.base import ProviderFetchResult
from pop_linux.providers.semanticscholar import SemanticScholarProvider


def _request(**kw) -> SearchRequest:
    base = {"query": "page test", "providers": ["semanticscholar"], "limit": 5}
    base.update(kw)
    return SearchRequest(**base)


def _page(items, total, nxt):
    return {"total": total, "offset": 0, "next": nxt, "data": items}


def _items(*titles):
    return [{"paperId": t.replace(" ", "-").lower(), "title": t, "year": 2021, "citationCount": 1, "authors": []} for t in titles]


def _patch_s2(monkeypatch, pages: list[dict], sleep_calls: list | None = None):
    """Patches S2 HTTP transport to serve a scripted sequence of pages.

    Each _get_with_retry call serves the next scripted page; the response
    object captures its page payload at construction time so state stays
    consistent between json() and the call log.
    """
    provider = SemanticScholarProvider()
    calls: list[dict] = []
    state = {"page": 0}

    class FakeResponse:
        def __init__(self, payload: dict):
            self._payload = payload
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    async def fake_get_with_retry(client, url, params, headers=None):
        idx = min(state["page"], len(pages) - 1)
        state["page"] += 1
        calls.append(dict(params))
        return FakeResponse(pages[idx])

    async def fake_sleep(delay):
        if sleep_calls is not None:
            sleep_calls.append(delay)

    monkeypatch.setattr(provider, "_get_with_retry", fake_get_with_retry)
    monkeypatch.setattr("pop_linux.providers.semanticscholar.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("pop_linux.providers.semanticscholar.load_config", lambda: {"api_keys": {"semanticscholar": ""}})
    return provider, calls


def test_s2_paginates_through_three_pages(monkeypatch):
    pages = [
        _page(_items("A One", "B Two"), total=90, nxt=2),
        _page(_items("C Three", "D Four"), total=90, nxt=4),
        _page(_items("E Five"), total=90, nxt=6),
    ]
    provider, calls = _patch_s2(monkeypatch, pages)
    result = asyncio.run(provider.fetch(_request(limit=5)))

    assert result.fetched_count == 5
    assert result.returned_count == 5
    assert result.matched_count == 90
    assert result.pages_or_requests == 3
    assert [c["offset"] for c in calls] == [0, 2, 4]


def test_s2_respects_exact_requested_limit(monkeypatch):
    pages = [
        _page(_items("A", "B", "C"), total=50, nxt=3),
        _page(_items("D", "E", "F", "G"), total=50, nxt=7),
    ]
    provider, calls = _patch_s2(monkeypatch, pages)
    result = asyncio.run(provider.fetch(_request(limit=5)))
    assert result.returned_count == 5
    assert len(result.papers) == 5


def test_s2_stops_on_empty_page(monkeypatch):
    pages = [
        _page(_items("A", "B"), total=90, nxt=2),
        _page([], total=90, nxt=4),
    ]
    provider, calls = _patch_s2(monkeypatch, pages)
    result = asyncio.run(provider.fetch(_request(limit=10)))
    assert result.fetched_count == 2
    assert result.pages_or_requests == 2


def test_s2_stops_on_absent_next_token(monkeypatch):
    pages = [
        _page(_items("A"), total=90, nxt=2),
        _page(_items("B"), total=90, nxt=None),  # last page: no next token
    ]
    provider, calls = _patch_s2(monkeypatch, pages)
    result = asyncio.run(provider.fetch(_request(limit=10)))
    assert result.fetched_count == 2
    assert result.pages_or_requests == 2


def test_s2_detects_repeated_page(monkeypatch):
    dup = _items("A", "B")
    pages = [
        _page(dup, total=90, nxt=2),
        _page(dup, total=90, nxt=4),  # provider cycling
    ]
    provider, calls = _patch_s2(monkeypatch, pages)
    result = asyncio.run(provider.fetch(_request(limit=10)))
    assert result.fetched_count == 2
    assert result.pages_or_requests == 2


def test_s2_keyless_pages_are_paced(monkeypatch):
    pages = [
        _page(_items("A", "B"), total=90, nxt=2),
        _page(_items("C", "D"), total=90, nxt=4),
    ]
    sleep_calls: list = []
    provider, calls = _patch_s2(monkeypatch, pages, sleep_calls)
    asyncio.run(provider.fetch(_request(limit=4)))
    assert sleep_calls == [SemanticScholarProvider.KEYLESS_PAGE_PACE_SECONDS]


def test_s2_keyed_pages_not_paced(monkeypatch):
    pages = [
        _page(_items("A", "B"), total=90, nxt=2),
        _page(_items("C", "D"), total=90, nxt=4),
    ]
    sleep_calls: list = []
    provider, calls = _patch_s2(monkeypatch, pages, sleep_calls)
    monkeypatch.setattr(
        "pop_linux.providers.semanticscholar.load_config",
        lambda: {"api_keys": {"semanticscholar": "KEY"}},
    )
    asyncio.run(provider.fetch(_request(limit=4)))
    assert sleep_calls == []


# ---------------------------------------------------------------------------
# Filter-mode reporting (engine copies registry modes into reports)
# ---------------------------------------------------------------------------


def _fake_fetch(provider_name: str, papers: list[Paper]) -> MagicMock:
    inst = MagicMock()
    inst.name = provider_name
    inst.fetch = AsyncMock(
        return_value=ProviderFetchResult(
            papers=papers, matched_count=len(papers), fetched_count=len(papers), returned_count=len(papers)
        )
    )
    return inst


def test_report_carries_filter_modes_from_registry(monkeypatch):
    import pop_linux.execution as em

    provider = _fake_fetch("semanticscholar", [Paper(title="X", citations=1)])
    monkeypatch.setattr(em, "resolve_providers", lambda req: [provider])

    env = execute_request(
        _request(filters=SearchFilters(author="Smith", issn="1234-5678", year_from=2020, min_citations=1))
    )
    report = env.provider_reports[0]
    assert report.filter_modes == {
        "author": "query_hint",
        "issn": "query_hint",
        "year_from": "native",
        "min_citations": "post_filter",
    }


def test_unsupported_filter_produces_structured_warning(monkeypatch):
    import pop_linux.execution as em

    provider = _fake_fetch("semanticscholar", [Paper(title="X", citations=1)])
    monkeypatch.setattr(em, "resolve_providers", lambda req: [provider])

    env = execute_request(_request(filters=SearchFilters(issn="1234-5678")))
    report = env.provider_reports[0]
    codes = [w.code for w in report.warnings]
    assert "FILTER_UNSUPPORTED" not in codes  # issn is query_hint for S2, not unsupported

    # Google Scholar has issn: unsupported -> requesting it must warn
    scholar = _fake_fetch("google_scholar", [])
    monkeypatch.setattr(em, "resolve_providers", lambda req: [scholar])
    env2 = execute_request(_request(filters=SearchFilters(issn="1234-5678")))
    report2 = env2.provider_reports[0]
    assert any(w.code == "FILTER_UNSUPPORTED" and w.metadata == {"filter": "issn"} for w in report2.warnings)
    assert report2.filter_modes == {"issn": "unsupported"}


def test_no_filters_requested_means_no_filter_modes_section(monkeypatch):
    import pop_linux.execution as em

    provider = _fake_fetch("openalex", [])
    monkeypatch.setattr(em, "resolve_providers", lambda req: [provider])
    env = execute_request(_request())
    assert env.provider_reports[0].filter_modes is None
