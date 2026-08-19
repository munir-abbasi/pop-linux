import asyncio

import httpx
from abc import ABC, abstractmethod

from pop_linux.config import load_config
from pop_linux.models import Paper, QueryResult

#: HTTP status codes that indicate a transient server/throttling failure worth retrying
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class BaseProvider(ABC):
    """Abstract base class for all academic paper search providers."""
    name: str = "base"

    def get_headers(self) -> dict:
        """Constructs polite HTTP headers including User-Agent with contact email."""
        cfg = load_config()
        email = cfg.get("polite_email", "pop-linux@syntaxhouse.com")
        return {
            "User-Agent": f"pop-linux/0.1.0 (mailto:{email})"
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

    @abstractmethod
    async def search(self, query: str, limit: int = 50, **kwargs) -> QueryResult:
        """Executes academic paper search and returns a QueryResult with metrics."""

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
