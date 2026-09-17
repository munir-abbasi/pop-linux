
import httpx

from pop_linux.execution_models import SearchRequest
from pop_linux.models import Author, Paper
from pop_linux.providers.base import BaseProvider, ProviderFetchResult


def _reconstruct_openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """Reconstructs abstract string from OpenAlex's inverted index format."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return None
    try:
        pos_word_map = {}
        for word, positions in inverted_index.items():
            for pos in positions:
                pos_word_map[pos] = word
        if not pos_word_map:
            return None
        words = [pos_word_map[i] for i in sorted(pos_word_map)]
        return " ".join(words).strip()
    except Exception:
        return None


class OpenAlexProvider(BaseProvider):
    """OpenAlex REST search provider (default fast, structured provider)."""
    name = "openalex"
    API_URL = "https://api.openalex.org/works"
    #: OpenAlex per-page ceiling per current official API docs.
    MAX_PER_PAGE = 200

    async def _fetch_native(self, request: SearchRequest) -> ProviderFetchResult:
        """OpenAlex native retrieval with cursor pagination.

        Cursor semantics verified against the live API (2026-09): the first
        request uses cursor="*" and each response's meta.next_cursor feeds the
        next request until the requested limit is satisfied or the token is
        absent.
        """
        f = request.filters
        query_terms = [request.query] if request.query else []
        if f.author:
            query_terms.append(f'author.display_name:"{f.author}"')
        if f.journal:
            query_terms.append(f'primary_location.source.display_name:"{f.journal}"')
        full_query = " ".join(query_terms).strip()

        params: dict[str, str | int] = {
            "search": full_query,
            "per_page": min(request.limit, self.MAX_PER_PAGE),
            "sort": "cited_by_count:desc",
        }

        oa_filters = []
        if f.year_from is not None and f.year_to is not None:
            oa_filters.append(f"publication_year:{f.year_from}-{f.year_to}")
        elif f.year_from is not None:
            oa_filters.append(f"publication_year:>{f.year_from - 1}")
        elif f.year_to is not None:
            oa_filters.append(f"publication_year:<{f.year_to + 1}")
        if f.issn:
            oa_filters.append(f"issn:{f.issn}")
        if oa_filters:
            params["filter"] = ",".join(oa_filters)

        headers = self.get_headers()

        async def fetch_page(cursor: str):
            page_params = dict(params)
            page_params["cursor"] = cursor or "*"
            async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
                response = await self._get_with_retry(client, self.API_URL, page_params)
                response.raise_for_status()
                data = response.json()
            meta = data.get("meta", {})
            papers = [self._parse_work(item) for item in data.get("results", [])]
            return papers, meta.get("count"), meta.get("next_cursor")

        return await self._paginate(request, fetch_page, page_size=params["per_page"])

    def _parse_work(self, item: dict) -> Paper:
        """Parses one OpenAlex work record into a normalized Paper."""
        title = item.get("display_name") or item.get("title") or "Untitled"
        doi = item.get("doi")

        primary_loc = item.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        journal_name = source.get("display_name")
        url = primary_loc.get("landing_page_url") or doi

        authorships = item.get("authorships") or []
        authors: list[Author] = []
        for auth_item in authorships:
            auth_data = auth_item.get("author") or {}
            auth_name = auth_data.get("display_name")
            if auth_name:
                insts = auth_item.get("institutions") or []
                inst_name = insts[0].get("display_name") if insts else None
                authors.append(Author(name=auth_name, affiliation=inst_name, author_id=auth_data.get("id")))

        return Paper(
            title=title,
            authors=authors,
            year=item.get("publication_year"),
            journal=journal_name,
            citations=item.get("cited_by_count", 0),
            doi=doi,
            url=url,
            abstract=_reconstruct_openalex_abstract(item.get("abstract_inverted_index")),
            source_provider=self.name,
            paper_id=item.get("id"),
        )
