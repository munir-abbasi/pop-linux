import time

import httpx

from pop_linux.config import load_config
from pop_linux.models import Author, Paper, QueryResult
from pop_linux.providers.base import BaseProvider
from pop_linux.utils.metrics import calculate_metrics


class SemanticScholarProvider(BaseProvider):
    """Semantic Scholar Academic Graph API search provider."""
    name = "semanticscholar"
    API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

    async def search(self, query: str, limit: int = 50, **kwargs) -> QueryResult:
        start_time = time.time()
        author = kwargs.get("author")
        journal = kwargs.get("journal")
        issn = kwargs.get("issn")
        year_from = kwargs.get("year_from")
        year_to = kwargs.get("year_to")
        min_citations = kwargs.get("min_citations")

        # The S2 Graph search API has no native ISSN filter; include it as a
        # keyword hint so `--issn` is not silently dropped in multi-provider mode.
        search_query_parts = [q for q in [query, author, journal] if q]
        if issn:
            search_query_parts.append(f"ISSN:{issn}")
        search_query = " ".join(search_query_parts).strip() if search_query_parts else query

        params: dict[str, str | int] = {
            "query": search_query,
            "limit": min(limit, 100),
            "fields": "paperId,title,authors,year,venue,citationCount,externalIds,url,abstract"
        }

        # Apply publication year filter if specified
        if year_from is not None and year_to is not None:
            params["year"] = f"{year_from}-{year_to}"
        elif year_from is not None:
            params["year"] = f"{year_from}-"
        elif year_to is not None:
            params["year"] = f"-{year_to}"

        cfg = load_config()
        api_key = cfg.get("api_keys", {}).get("semanticscholar", "")
        headers = self.get_headers()
        if api_key:
            headers["x-api-key"] = api_key

        async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
            response = await self._get_with_retry(client, self.API_URL, params)
            if response.status_code in [400, 401, 403] and api_key:
                # Retry keyless from a clean client — client-level headers still carry the
                # key, so deleting it from the local dict is not enough.
                keyless_headers = {k: v for k, v in headers.items() if k != "x-api-key"}
                async with httpx.AsyncClient(timeout=20.0, headers=keyless_headers) as keyless_client:
                    response = await self._get_with_retry(keyless_client, self.API_URL, params)

            response.raise_for_status()
            data = response.json()

        total_found = data.get("total", 0)
        items = data.get("data", [])

        papers: list[Paper] = []
        for item in items:
            title = item.get("title") or "Untitled"
            year = item.get("year")
            citations = item.get("citationCount", 0)
            venue = item.get("venue")
            abstract = item.get("abstract")
            url = item.get("url")

            ext_ids = item.get("externalIds") or {}
            doi = ext_ids.get("DOI")

            raw_authors = item.get("authors") or []
            authors: list[Author] = [
                Author(name=a.get("name"), author_id=a.get("authorId"))
                for a in raw_authors if a.get("name")
            ]

            paper = Paper(
                title=title,
                authors=authors,
                year=year,
                journal=venue,
                citations=citations,
                doi=doi,
                url=url,
                abstract=abstract,
                source_provider=self.name,
                paper_id=item.get("paperId")
            )
            papers.append(paper)

        papers = self.filter_papers(papers, year_from=year_from, year_to=year_to, min_citations=min_citations)
        metrics = calculate_metrics(papers)
        elapsed = round(time.time() - start_time, 2)

        return QueryResult(
            query=query,
            provider=self.name,
            total_found=total_found,
            papers=papers,
            metrics=metrics,
            search_time_seconds=elapsed
        )
