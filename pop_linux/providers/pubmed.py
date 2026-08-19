import asyncio
import re
import time

import httpx

from pop_linux.config import load_config
from pop_linux.models import Author, Paper, QueryResult
from pop_linux.providers.base import BaseProvider
from pop_linux.utils.metrics import calculate_metrics


def _extract_year_from_pubdate(pubdate: str) -> int | None:
    """Extracts 4-digit year from PubMed pubdate string (e.g. '2023 Jan 15')."""
    if not pubdate:
        return None
    match = re.search(r'\b(19|20)\d{2}\b', pubdate)
    return int(match.group(0)) if match else None


class PubMedProvider(BaseProvider):
    """NCBI PubMed / Entrez REST API search provider."""
    name = "pubmed"
    ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

    async def search(self, query: str, limit: int = 50, **kwargs) -> QueryResult:
        start_time = time.time()
        author = kwargs.get("author")
        journal = kwargs.get("journal")
        issn = kwargs.get("issn")
        year_from = kwargs.get("year_from")
        year_to = kwargs.get("year_to")
        min_citations = kwargs.get("min_citations")

        term_parts = [query] if query else []
        if author:
            term_parts.append(f'"{author}"[Author]')
        if journal:
            term_parts.append(f'"{journal}"[Journal]')
        if issn:
            term_parts.append(f'"{issn}"[ISSN]')
        if year_from is not None and year_to is not None:
            term_parts.append(f"{year_from}:{year_to}[PDAT]")
        elif year_from is not None:
            term_parts.append(f"{year_from}:3000[PDAT]")
        elif year_to is not None:
            term_parts.append(f"1800:{year_to}[PDAT]")

        full_term = " AND ".join(term_parts).strip()

        headers = self.get_headers()

        cfg = load_config()
        ncbi_key = cfg.get("api_keys", {}).get("ncbi", "")

        async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
            keyless = not ncbi_key
            # 1. Execute ESearch to retrieve matching PMIDs
            esearch_params: dict[str, str | int] = {
                "db": "pubmed",
                "term": full_term,
                "retmax": min(limit, 100),
                "retmode": "json"
            }
            if ncbi_key:
                esearch_params["api_key"] = ncbi_key

            search_resp = await self._get_with_retry(client, self.ESEARCH_URL, esearch_params)
            if search_resp.status_code in [400, 401, 403] and "api_key" in esearch_params:
                # Fallback to keyless request if user's API key is invalid
                keyless_params = {k: v for k, v in esearch_params.items() if k != "api_key"}
                search_resp = await self._get_with_retry(client, self.ESEARCH_URL, keyless_params)
                keyless = True

            search_resp.raise_for_status()
            search_data = search_resp.json().get("esearchresult", {})

            total_found = int(search_data.get("count", 0))
            id_list = search_data.get("idlist", [])

            if not id_list:
                return QueryResult(
                    query=query,
                    provider=self.name,
                    total_found=0,
                    papers=[],
                    metrics=calculate_metrics([]),
                    search_time_seconds=round(time.time() - start_time, 2)
                )

            # NCBI rate-limits keyless requests (max 3/sec); pace the second call.
            if keyless:
                await asyncio.sleep(0.34)

            # 2. Execute ESummary to get paper details for PMIDs
            esummary_params: dict[str, str] = {
                "db": "pubmed",
                "id": ",".join(id_list),
                "retmode": "json"
            }
            if ncbi_key:
                esummary_params["api_key"] = ncbi_key

            summary_resp = await self._get_with_retry(client, self.ESUMMARY_URL, esummary_params)
            if summary_resp.status_code in [400, 401, 403] and "api_key" in esummary_params:
                keyless_params = {k: v for k, v in esummary_params.items() if k != "api_key"}
                await asyncio.sleep(0.34)  # Pace the keyless fallback per NCBI's 3 req/s limit.
                summary_resp = await self._get_with_retry(client, self.ESUMMARY_URL, keyless_params)

            summary_resp.raise_for_status()
            result_dict = summary_resp.json().get("result", {})

        papers: list[Paper] = []
        for pmid in id_list:
            item = result_dict.get(pmid)
            if not item:
                continue

            title = item.get("title") or "Untitled"
            title = re.sub(r'\[|\]', '', title)  # Remove bracket artifacts in translations

            year = _extract_year_from_pubdate(item.get("pubdate", ""))
            journal = item.get("source")
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

            # Extract DOI from articleids
            doi = None
            for art_id in item.get("articleids", []):
                if art_id.get("idtype") == "doi":
                    doi = art_id.get("value")
                    break

            # Extract Authors
            authors: list[Author] = [
                Author(name=a.get("name"))
                for a in item.get("authors", []) if a.get("name")
            ]

            paper = Paper(
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                citations=0,  # PubMed API does not include citation counts natively
                doi=doi,
                url=url,
                source_provider=self.name,
                paper_id=pmid
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
