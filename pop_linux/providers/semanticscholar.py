import asyncio
import time

import httpx

from pop_linux.config import load_config
from pop_linux.execution_models import SearchRequest
from pop_linux.models import Author, Paper
from pop_linux.providers.base import BaseProvider, ProviderFetchResult


class SemanticScholarProvider(BaseProvider):
    """Semantic Scholar Academic Graph API search provider."""
    name = "semanticscholar"
    API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
    #: S2 relevance-search per-request ceiling per current Graph API docs.
    MAX_PER_PAGE = 100
    #: Keyless shared tier is rate limited; pace subsequent pages.
    KEYLESS_PAGE_PACE_SECONDS = 1.0

    def _build_params(self, request: SearchRequest, page_size: int) -> dict:
        """Compiles S2 query parameters from the resolved request.

        The S2 Graph search API has no native ISSN/author/journal filters;
        those become keyword hints so `--issn` is not silently dropped.
        Year bounds use the native `year` range parameter.
        """
        f = request.filters
        search_query_parts = [q for q in [request.query, f.author, f.journal] if q]
        if f.issn:
            search_query_parts.append(f"ISSN:{f.issn}")
        search_query = " ".join(search_query_parts).strip() if search_query_parts else request.query

        params: dict[str, str | int] = {
            "query": search_query,
            "limit": page_size,
            "fields": "paperId,title,authors,year,venue,citationCount,externalIds,url,abstract",
        }
        if f.year_from is not None and f.year_to is not None:
            params["year"] = f"{f.year_from}-{f.year_to}"
        elif f.year_from is not None:
            params["year"] = f"{f.year_from}-"
        elif f.year_to is not None:
            params["year"] = f"-{f.year_to}"
        return params

    async def _search_page(self, client: httpx.AsyncClient, params: dict, headers: dict, api_key: str):
        """Executes one S2 search page with keyless fallback on auth rejection."""
        response = await self._get_with_retry(client, self.API_URL, params, headers=headers)
        if response.status_code in [400, 401, 403] and api_key:
            # Retry keyless from a clean client — client-level headers still carry the
            # key, so deleting it from the local dict is not enough.
            keyless_headers = {k: v for k, v in headers.items() if k != "x-api-key"}
            async with httpx.AsyncClient(timeout=20.0, headers=keyless_headers) as keyless_client:
                response = await self._get_with_retry(keyless_client, self.API_URL, params)
        response.raise_for_status()
        data = response.json()
        return data, params

    def _parse_item(self, item: dict) -> Paper:
        """Parses one S2 paper record into a normalized Paper."""
        ext_ids = item.get("externalIds") or {}
        raw_authors = item.get("authors") or []
        return Paper(
            title=item.get("title") or "Untitled",
            authors=[
                Author(name=a.get("name"), author_id=a.get("authorId"))
                for a in raw_authors if a.get("name")
            ],
            year=item.get("year"),
            journal=item.get("venue"),
            citations=item.get("citationCount", 0),
            doi=ext_ids.get("DOI"),
            url=item.get("url"),
            abstract=item.get("abstract"),
            source_provider=self.name,
            paper_id=item.get("paperId"),
        )

    async def _fetch_native(self, request: SearchRequest) -> ProviderFetchResult:
        """Semantic Scholar native retrieval with offset/next pagination.

        Page semantics per the S2 Graph API relevance-search contract:
        requests take `offset` + `limit`; responses carry `total`, `offset`,
        and `next` (absent on the last page). Keyless requests are paced to
        respect the shared 1 req/s tier. Collection is bounded by the
        requested limit and the MAX_PAGES safety guard.
        """
        start_time = time.time()
        limit = request.limit
        page_size = min(limit, self.MAX_PER_PAGE)
        params = self._build_params(request, page_size)

        cfg = load_config()
        api_key = cfg.get("api_keys", {}).get("semanticscholar", "")
        headers = self.get_headers()
        if api_key:
            headers["x-api-key"] = api_key

        collected: list[Paper] = []
        matched: int | None = None
        offset = 0
        pages = 0
        next_token: int | None = 0
        seen_fingerprints: set[str] = set()

        async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
            while (
                len(collected) < limit
                and next_token is not None
                and pages < self.MAX_PAGES
            ):
                if pages and not api_key:
                    await asyncio.sleep(self.KEYLESS_PAGE_PACE_SECONDS)

                page_params = dict(params)
                page_params["offset"] = offset
                data, _ = await self._search_page(client, page_params, headers, api_key)
                pages += 1

                page_matched = data.get("total")
                if page_matched is not None:
                    matched = int(page_matched)
                items = data.get("data", [])
                if not items:
                    break

                page_papers = [self._parse_item(item) for item in items]
                fingerprint = "|".join((p.paper_id or p.title) for p in page_papers)
                if fingerprint in seen_fingerprints:
                    break  # repeated page: provider is cycling
                seen_fingerprints.add(fingerprint)
                collected.extend(page_papers)

                nxt = data.get("next")
                next_token = int(nxt) if nxt is not None else None
                offset = next_token if next_token is not None else offset + len(items)

        filtered = self.filter_papers(
            collected[:limit],
            year_from=request.filters.year_from,
            year_to=request.filters.year_to,
            min_citations=request.filters.min_citations,
        )
        return ProviderFetchResult(
            papers=filtered,
            matched_count=matched,
            fetched_count=len(collected),
            returned_count=len(filtered),
            elapsed_seconds=round(time.time() - start_time, 2),
            pages_or_requests=pages,
        )
