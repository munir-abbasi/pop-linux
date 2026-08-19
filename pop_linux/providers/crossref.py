import re
import time

import httpx

from pop_linux.models import Author, Paper, QueryResult
from pop_linux.providers.base import BaseProvider
from pop_linux.utils.metrics import calculate_metrics


def _clean_abstract(raw_abstract: str | None) -> str | None:
    """Strips XML/JATS markup tags from CrossRef abstract text."""
    if not raw_abstract:
        return None
    cleaned = re.sub(r'<[^>]+>', '', raw_abstract)
    return cleaned.strip()


class CrossRefProvider(BaseProvider):
    """CrossRef REST API search provider."""
    name = "crossref"
    API_URL = "https://api.crossref.org/works"

    async def search(self, query: str, limit: int = 50, **kwargs) -> QueryResult:
        start_time = time.time()
        author = kwargs.get("author")
        journal = kwargs.get("journal")
        issn = kwargs.get("issn")
        year_from = kwargs.get("year_from")
        year_to = kwargs.get("year_to")
        min_citations = kwargs.get("min_citations")

        params: dict[str, str | int] = {
            "rows": min(limit, 100),
            "sort": "is-referenced-by-count",
            "order": "desc"
        }
        if query:
            params["query"] = query
        if author:
            params["query.author"] = author
        if journal:
            params["query.container-title"] = journal

        filters = []
        if year_from is not None:
            filters.append(f"from-pub-date:{year_from}-01-01")
        if year_to is not None:
            filters.append(f"until-pub-date:{year_to}-12-31")
        if issn:
            filters.append(f"issn:{issn}")

        if filters:
            params["filter"] = ",".join(filters)

        headers = self.get_headers()
        async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
            response = await self._get_with_retry(client, self.API_URL, params)
            response.raise_for_status()
            data = response.json()

        message = data.get("message", {})
        total_found = message.get("total-results", 0)
        items = message.get("items", [])

        papers: list[Paper] = []
        for item in items:
            titles = item.get("title") or []
            title = titles[0] if titles else "Untitled"
            citations = item.get("is-referenced-by-count", 0)
            doi = item.get("DOI")
            url = item.get("URL") or (f"https://doi.org/{doi}" if doi else None)

            # Extract Journal / Venue
            containers = item.get("container-title") or []
            journal = containers[0] if containers else None

            # Extract Publication Year
            year = None
            date_parts = (
                item.get("published-print", {}).get("date-parts") or
                item.get("published-online", {}).get("date-parts") or
                item.get("created", {}).get("date-parts") or []
            )
            if date_parts and date_parts[0]:
                year = date_parts[0][0]

            # Extract Authors
            raw_authors = item.get("author") or []
            authors: list[Author] = []
            for a in raw_authors:
                given = a.get("given", "")
                family = a.get("family", "")
                name = f"{given} {family}".strip() or family or given
                if name:
                    affils = a.get("affiliation") or []
                    affil_name = affils[0].get("name") if affils else None
                    authors.append(Author(name=name, affiliation=affil_name))

            abstract = _clean_abstract(item.get("abstract"))

            paper = Paper(
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                citations=citations,
                doi=doi,
                url=url,
                abstract=abstract,
                source_provider=self.name,
                paper_id=doi
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
