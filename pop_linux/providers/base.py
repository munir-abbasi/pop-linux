import asyncio
import time

import httpx
from abc import ABC, abstractmethod
from pydantic import BaseModel, ConfigDict, Field

from pop_linux.config import load_config
from pop_linux.execution_models import ExecutionMessage, SearchFilters, SearchRequest
from pop_linux.models import Paper, QueryResult
from pop_linux.utils.metrics import calculate_metrics

#: HTTP status codes that indicate a transient server/throttling failure worth retrying
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class ProviderFetchResult(BaseModel):
    """Engine-facing provider fetch result (implementation_plan.md Phase 7).

    Providers own retrieval, query compilation, pagination, parsing, and
    provider execution reporting through `fetch()`. They do NOT own global
    metrics, SQLite history, or terminal rendering.
    """

    model_config = ConfigDict(extra="forbid")

    papers: list[Paper] = Field(default_factory=list)
    #: upstream provider-reported total match count when available
    matched_count: int | None = None
    #: records parsed before common post-filtering
    fetched_count: int = 0
    #: records surviving provider post-filtering (contributed to aggregation)
    returned_count: int = 0
    elapsed_seconds: float = 0.0
    pages_or_requests: int | None = None
    warnings: list[ExecutionMessage] = Field(default_factory=list)


def _filters_from_request(request: SearchRequest) -> dict:
    f = request.filters
    return {
        "author": f.author,
        "journal": f.journal,
        "issn": f.issn,
        "year_from": f.year_from,
        "year_to": f.year_to,
        "min_citations": f.min_citations,
    }


def _filters_from_kwargs(kwargs: dict) -> SearchFilters:
    return SearchFilters(
        author=kwargs.get("author"),
        journal=kwargs.get("journal"),
        issn=kwargs.get("issn"),
        year_from=kwargs.get("year_from"),
        year_to=kwargs.get("year_to"),
        min_citations=kwargs.get("min_citations"),
    )


def _project_to_query_result(provider_name: str, query: str, fetch_result: ProviderFetchResult) -> QueryResult:
    """Projects a fetch result onto the legacy QueryResult contract."""
    return QueryResult(
        query=query,
        provider=provider_name,
        total_found=fetch_result.matched_count if fetch_result.matched_count is not None else fetch_result.returned_count,
        papers=fetch_result.papers,
        metrics=calculate_metrics(fetch_result.papers),
        search_time_seconds=fetch_result.elapsed_seconds,
    )


class BaseProvider(ABC):
    """Abstract base class for all academic paper search providers."""

    name: str = "base"

    #: Maximum pages fetchable in one execution regardless of requested limit
    #: (safety guard; actual pages are also bounded by the requested limit).
    MAX_PAGES = 10

    async def _paginate(
        self,
        request: SearchRequest,
        fetch_page,
        page_size: int,
    ) -> ProviderFetchResult:
        """Generic bounded pagination loop for the engine fetch contract.

        fetch_page(token) is an async callable returning
        (papers, matched_count, next_token) where token is the provider's
        cursor/offset token ("" on the first call).

        Stop conditions: requested limit reached, empty page, absent next
        token, repeated page content, or the MAX_PAGES safety guard.
        """
        start = time.time()
        collected: list[Paper] = []
        matched: int | None = None
        pages = 0
        token: str | None = ""
        seen_fingerprints: set[str] = set()

        while len(collected) < request.limit and token is not None and pages < self.MAX_PAGES:
            page_papers, page_matched, token = await fetch_page(token)
            pages += 1
            if page_matched is not None:
                matched = page_matched
            if not page_papers:
                break
            fingerprint = "|".join((p.paper_id or p.title) for p in page_papers)
            if fingerprint in seen_fingerprints:
                break  # repeated page: provider is cycling
            seen_fingerprints.add(fingerprint)
            collected.extend(page_papers)

        filtered = self.filter_papers(
            collected[: request.limit],
            year_from=request.filters.year_from,
            year_to=request.filters.year_to,
            min_citations=request.filters.min_citations,
        )
        return ProviderFetchResult(
            papers=filtered,
            matched_count=matched,
            fetched_count=len(collected),
            returned_count=len(filtered),
            elapsed_seconds=round(time.time() - start, 2),
            pages_or_requests=pages,
        )

    @abstractmethod
    async def _fetch_native(self, request: SearchRequest) -> ProviderFetchResult:
        """Provider-specific retrieval (implemented by each provider)."""

    async def fetch(self, request: SearchRequest) -> ProviderFetchResult:
        """Engine-facing contract: wraps native retrieval with timing."""
        start = time.time()
        result = await self._fetch_native(request)
        if result.elapsed_seconds <= 0:
            result.elapsed_seconds = round(time.time() - start, 2)
        return result

    def get_headers(self) -> dict:
        """Constructs polite HTTP headers including User-Agent with contact email."""
        cfg = load_config()
        email = (cfg.get("polite_email") or "").strip()
        ua = "pop-linux/0.1.0"
        if email:
            ua += f" (mailto:{email})"
        return {
            "User-Agent": ua
        }

    async def _get_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict,
        headers: dict | None = None,
        retries: int = 3,
    ) -> httpx.Response:
        """GETs a URL with exponential backoff on transient failures (429/502/503/504, network errors).

        Returns the first non-transient response, or the last transient response once
        retries are exhausted so callers can surface the real status via raise_for_status().
        """
        last_response = None
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                response = await client.get(url, params=params, headers=headers)
                if response.status_code in _TRANSIENT_STATUS_CODES:
                    last_response = response
                    if attempt < retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    continue
                return response
            except httpx.TransportError as err:
                last_error = err
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
        if last_response is not None:
            return last_response
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Exhausted {retries} retries for {url}")

    async def search(self, query: str, limit: int = 50, **kwargs) -> QueryResult:
        """Legacy library/CLI compatibility contract.

        Builds a resolved request, executes the native fetch contract, and
        projects the result into the historical QueryResult shape (including
        metrics, which remain part of the legacy projection only).
        """
        request = SearchRequest(
            query=query,
            providers=[self.name],
            limit=limit if limit and limit > 0 else 1,
            filters=_filters_from_kwargs(kwargs),
        )
        fetch_result = await self.fetch(request)
        return _project_to_query_result(self.name, query, fetch_result)

    def filter_papers(
        self,
        papers: list["Paper"],
        year_from: int | None = None,
        year_to: int | None = None,
        min_citations: int | None = None,
    ) -> list["Paper"]:
        """Filters papers based on year range and minimum citation threshold."""
        filtered = papers
        if year_from is not None:
            filtered = [p for p in filtered if p.year is None or p.year >= year_from]
        if year_to is not None:
            filtered = [p for p in filtered if p.year is None or p.year <= year_to]
        if min_citations is not None:
            filtered = [p for p in filtered if p.citations >= min_citations]
        return filtered
