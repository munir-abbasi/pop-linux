
import httpx

from pop_linux.execution_models import SearchRequest
from pop_linux.models import Author, Paper
from pop_linux.providers.base import BaseProvider, ProviderFetchResult


def _clean_abstract(raw_abstract: str | None) -> str | None:
    """Strips XML/JATS markup tags from CrossRef abstract text."""
    if not raw_abstract:
        return None
    cleaned = re.sub(r'<[^>]+>', '', raw_abstract)
    return cleaned.strip()


import re  # noqa: E402  (used by _clean_abstract above)


class CrossRefProvider(BaseProvider):
    """CrossRef REST API search provider."""
    name = "crossref"
    API_URL = "https://api.crossref.org/works"
    #: CrossRef per-request row ceiling per current official API docs.
    MAX_PER_PAGE = 100

    async def _fetch_native(self, request: SearchRequest) -> ProviderFetchResult:
        """CrossRef native retrieval with cursor pagination.

        Cursor semantics verified against the live API (2026-09): works
        queries accept cursor="*" plus sort/order and return
        message.next-cursor for subsequent pages. The cursor deep-paging
        model avoids the offset ceiling that applies to plain offset paging.
        """
        f = request.filters

        params: dict[str, str | int] = {
            "rows": min(request.limit, self.MAX_PER_PAGE),
            "sort": "is-referenced-by-count",
            "order": "desc",
        }
        if request.query:
            params["query"] = request.query
        if f.author:
            params["query.author"] = f.author
        if f.journal:
            params["query.container-title"] = f.journal

        filters = []
        if f.year_from is not None:
            filters.append(f"from-pub-date:{f.year_from}-01-01")
        if f.year_to is not None:
            filters.append(f"until-pub-date:{f.year_to}-12-31")
        if f.issn:
            filters.append(f"issn:{f.issn}")
        if filters:
            params["filter"] = ",".join(filters)

        headers = self.get_headers()

        async def fetch_page(cursor: str):
            page_params = dict(params)
            page_params["cursor"] = cursor or "*"
            async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
                response = await self._get_with_retry(client, self.API_URL, page_params)
                response.raise_for_status()
                data = response.json()
            message = data.get("message", {})
            papers = [self._parse_item(item) for item in message.get("items", [])]
            return papers, message.get("total-results"), message.get("next-cursor")

        return await self._paginate(request, fetch_page, page_size=params["rows"])

    def _parse_item(self, item: dict) -> Paper:
        """Parses one CrossRef work record into a normalized Paper."""
        titles = item.get("title") or []
        title = titles[0] if titles else "Untitled"
        citations = item.get("is-referenced-by-count", 0)
        doi = item.get("DOI")
        url = item.get("URL") or (f"https://doi.org/{doi}" if doi else None)

        containers = item.get("container-title") or []
        journal = containers[0] if containers else None

        year = None
        date_parts = (
            item.get("published-print", {}).get("date-parts")
            or item.get("published-online", {}).get("date-parts")
            or item.get("created", {}).get("date-parts")
            or []
        )
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

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

        return Paper(
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            citations=citations,
            doi=doi,
            url=url,
            abstract=_clean_abstract(item.get("abstract")),
            source_provider=self.name,
            paper_id=doi,
        )
