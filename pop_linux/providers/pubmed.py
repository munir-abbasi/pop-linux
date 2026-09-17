import asyncio
import re
import time

import httpx

from pop_linux.config import load_config
from pop_linux.execution_models import SearchRequest
from pop_linux.models import Author, Paper
from pop_linux.providers.base import BaseProvider, ProviderFetchResult


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
    #: ESearch retmax ceiling per current official E-utilities documentation.
    MAX_PER_PAGE = 100

    def _build_term(self, query: str, f) -> str:
        """Compiles the Entrez query term from the resolved request filters."""
        term_parts = [query] if query else []
        if f.author:
            term_parts.append(f'"{f.author}"[Author]')
        if f.journal:
            term_parts.append(f'"{f.journal}"[Journal]')
        if f.issn:
            term_parts.append(f'"{f.issn}"[ISSN]')
        if f.year_from is not None and f.year_to is not None:
            term_parts.append(f"{f.year_from}:{f.year_to}[PDAT]")
        elif f.year_from is not None:
            term_parts.append(f"{f.year_from}:3000[PDAT]")
        elif f.year_to is not None:
            term_parts.append(f"1800:{f.year_to}[PDAT]")
        return " AND ".join(term_parts).strip()

    async def _esearch_page(self, client, term: str, retmax: int, retstart: int, ncbi_key: str):
        """Executes one ESearch page, falling back to keyless on auth rejection."""
        params: dict[str, str | int] = {
            "db": "pubmed",
            "term": term,
            "retmax": retmax,
            "retstart": retstart,
            "retmode": "json",
        }
        if ncbi_key:
            params["api_key"] = ncbi_key

        resp = await self._get_with_retry(client, self.ESEARCH_URL, params)
        if resp.status_code in [400, 401, 403] and ncbi_key:
            # Fallback to keyless request if user's API key is invalid
            params = {k: v for k, v in params.items() if k != "api_key"}
            resp = await self._get_with_retry(client, self.ESEARCH_URL, params)
        resp.raise_for_status()
        data = resp.json().get("esearchresult", {})
        total = int(data.get("count", 0))
        ids = data.get("idlist", [])
        return total, ids, params.get("api_key")

    async def _fetch_native(self, request: SearchRequest) -> ProviderFetchResult:
        """PubMed native retrieval with retstart offset pagination.

        Pagination semantics per the official E-utilities documentation
        (E-utilities In-Depth, NBK25499): ESearch supports retstart/retmax
        paging; retmax ceiling 100. Keyless requests remain paced to NCBI's
        3 req/s shared-tier limit.
        """
        start_time = time.time()
        term = self._build_term(request.query, request.filters)
        limit = request.limit
        cfg = load_config()
        ncbi_key = cfg.get("api_keys", {}).get("ncbi", "")
        headers = self.get_headers()
        keyless = not ncbi_key
        requests_made = 0

        all_ids: list[str] = []
        total_found: int | None = None
        retstart = 0
        retmax = min(limit, self.MAX_PER_PAGE)

        async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
            while len(all_ids) < limit and (total_found is None or retstart < total_found):
                if keyless and requests_made:
                    await asyncio.sleep(0.34)  # pace keyless requests (3/sec)

                total, ids, used_key = await self._esearch_page(client, term, retmax, retstart, ncbi_key)
                requests_made += 1
                keyless = keyless or used_key is None
                total_found = total
                if not ids:
                    break
                all_ids.extend(ids)
                retstart += len(ids)
                if not used_key:
                    keyless = True

            if not all_ids:
                return ProviderFetchResult(
                    matched_count=total_found or 0,
                    fetched_count=0,
                    returned_count=0,
                    elapsed_seconds=round(time.time() - start_time, 2),
                    pages_or_requests=requests_made,
                )

            if keyless:
                await asyncio.sleep(0.34)
            requests_made += 1

            result_dict, _ = await self._esummary(client, all_ids, ncbi_key)

        papers: list[Paper] = []
        for pmid in all_ids:
            item = result_dict.get(pmid)
            if not item:
                continue
            papers.append(self._parse_summary(pmid, item))

        filtered = self.filter_papers(
            papers,
            year_from=request.filters.year_from,
            year_to=request.filters.year_to,
            min_citations=request.filters.min_citations,
        )
        return ProviderFetchResult(
            papers=filtered,
            matched_count=total_found,
            fetched_count=len(papers),
            returned_count=len(filtered),
            elapsed_seconds=round(time.time() - start_time, 2),
            pages_or_requests=requests_made,
        )

    async def _esummary(self, client, id_list: list[str], ncbi_key: str):
        """Fetches ESummary records for PMIDs with keyless fallback."""
        params: dict[str, str] = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "json",
        }
        if ncbi_key:
            params["api_key"] = ncbi_key
        resp = await self._get_with_retry(client, self.ESUMMARY_URL, params)
        if resp.status_code in [400, 401, 403] and ncbi_key:
            params = {k: v for k, v in params.items() if k != "api_key"}
            await asyncio.sleep(0.34)  # pace the keyless fallback per NCBI's 3 req/s limit
            resp = await self._get_with_retry(client, self.ESUMMARY_URL, params)
        resp.raise_for_status()
        return resp.json().get("result", {}), params.get("api_key")

    def _parse_summary(self, pmid: str, item: dict) -> Paper:
        """Parses one ESummary record into a normalized Paper."""
        title = item.get("title") or "Untitled"
        title = re.sub(r'\[|\]', '', title)  # Remove bracket artifacts in translations

        year = _extract_year_from_pubdate(item.get("pubdate", ""))
        journal = item.get("source")
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

        doi = None
        for art_id in item.get("articleids", []):
            if art_id.get("idtype") == "doi":
                doi = art_id.get("value")
                break

        authors: list[Author] = [
            Author(name=a.get("name"))
            for a in item.get("authors", []) if a.get("name")
        ]

        return Paper(
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            citations=0,  # PubMed API does not include citation counts natively
            doi=doi,
            url=url,
            source_provider=self.name,
            paper_id=pmid,
        )
