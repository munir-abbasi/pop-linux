import time

import httpx

from pop_linux.models import Author, Paper, QueryResult
from pop_linux.providers.base import BaseProvider
from pop_linux.utils.metrics import calculate_metrics


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

    async def search(self, query: str, limit: int = 50, **kwargs) -> QueryResult:
        start_time = time.time()
        author = kwargs.get("author")
        journal = kwargs.get("journal")
        issn = kwargs.get("issn")
        year_from = kwargs.get("year_from")
        year_to = kwargs.get("year_to")
        min_citations = kwargs.get("min_citations")

        # Build query string with author/journal terms if provided
        query_terms = [query] if query else []
        if author:
            query_terms.append(f'author.display_name:"{author}"')
        if journal:
            query_terms.append(f'primary_location.source.display_name:"{journal}"')

        full_query = " ".join(query_terms).strip()

        params: dict[str, str | int] = {
            "search": full_query,
            "per_page": min(limit, 200),
            "sort": "cited_by_count:desc"
        }

        # Apply OpenAlex publication_year filter if year range supplied
        filters = []
        if year_from is not None and year_to is not None:
            filters.append(f"publication_year:{year_from}-{year_to}")
        elif year_from is not None:
            filters.append(f"publication_year:>{year_from - 1}")
        elif year_to is not None:
            filters.append(f"publication_year:<{year_to + 1}")

        if issn:
            filters.append(f"issn:{issn}")

        if filters:
            params["filter"] = ",".join(filters)

        headers = self.get_headers()
        async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
            response = await self._get_with_retry(client, self.API_URL, params)
            response.raise_for_status()
            data = response.json()

        total_found = data.get("meta", {}).get("count", 0)
        results = data.get("results", [])

        papers: list[Paper] = []
        for item in results:
            title = item.get("display_name") or item.get("title") or "Untitled"
            year = item.get("publication_year")
            citations = item.get("cited_by_count", 0)
            doi = item.get("doi")

            # Extract Primary Location / Journal / URL
            primary_loc = item.get("primary_location") or {}
            source = primary_loc.get("source") or {}
            journal_name = source.get("display_name")
            url = primary_loc.get("landing_page_url") or doi

            # Extract Authors
            authorships = item.get("authorships") or []
            authors: list[Author] = []
            for auth_item in authorships:
                auth_data = auth_item.get("author") or {}
                auth_name = auth_data.get("display_name")
                if auth_name:
                    insts = auth_item.get("institutions") or []
                    inst_name = insts[0].get("display_name") if insts else None
                    authors.append(Author(name=auth_name, affiliation=inst_name, author_id=auth_data.get("id")))

            abstract = _reconstruct_openalex_abstract(item.get("abstract_inverted_index"))

            paper = Paper(
                title=title,
                authors=authors,
                year=year,
                journal=journal_name,
                citations=citations,
                doi=doi,
                url=url,
                abstract=abstract,
                source_provider=self.name,
                paper_id=item.get("id")
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
