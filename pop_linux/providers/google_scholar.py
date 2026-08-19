import re
import time

import httpx
from bs4 import BeautifulSoup

from pop_linux.config import DEFAULT_USER_AGENT, load_config
from pop_linux.models import Author, Paper, QueryResult
from pop_linux.providers.base import BaseProvider
from pop_linux.utils.cookie_bridge import load_cookies, solve_google_scholar_captcha
from pop_linux.utils.metrics import calculate_metrics


def _parse_scholar_author_line(byline: str) -> tuple[list[Author], str | None, int | None]:
    """Parses Google Scholar byline string (e.g. 'A Smith, B Jones - Journal of AI, 2021 - publisher')."""
    if not byline:
        return [], None, None

    parts = [p.strip() for p in byline.split("-")]
    authors: list[Author] = []
    journal = None
    year = None

    if len(parts) >= 1:
        raw_authors = parts[0].split(",")
        for a in raw_authors:
            cleaned = a.strip()
            if cleaned and not cleaned.startswith("..."):
                authors.append(Author(name=cleaned))

    if len(parts) >= 2:
        venue_part = parts[1]
        year_match = re.search(r'\b(19|20)\d{2}\b', venue_part)
        if year_match:
            year = int(year_match.group(0))
        # Remove year from venue to extract journal title
        journal_candidate = re.sub(r',?\s*\b(19|20)\d{2}\b', '', venue_part).strip()
        if journal_candidate:
            journal = journal_candidate

    return authors, journal, year


def parse_google_scholar_html(html_content: str) -> list[Paper]:
    """Parses Google Scholar HTML search results into a list of Paper objects."""
    soup = BeautifulSoup(html_content, "html.parser")
    entries = soup.select(".gs_r.gs_or.gs_scl")
    papers: list[Paper] = []

    for entry in entries:
        title_tag = entry.select_one(".gs_rt a")
        if not title_tag:
            title_tag = entry.select_one(".gs_rt")
            title = title_tag.text.strip() if title_tag else "Untitled"
            url = None
        else:
            title = title_tag.text.strip()
            raw_url = title_tag.get("href")
            url = str(raw_url) if raw_url else None

        # Strip [PDF], [HTML], [BOOK], [CITATION] prefixes from title
        title = re.sub(r'^(\[[A-Za-z]+\]\s*)+', '', title)

        byline_tag = entry.select_one(".gs_a")
        byline_text = byline_tag.text.strip() if byline_tag else ""
        authors, journal, year = _parse_scholar_author_line(byline_text)

        abstract_tag = entry.select_one(".gs_rs")
        abstract = abstract_tag.text.strip() if abstract_tag else None

        # Citations
        citations = 0
        cite_link = entry.find("a", string=re.compile(r'Cited by \d+', re.IGNORECASE))
        if cite_link:
            match = re.search(r'Cited by (\d+)', cite_link.text, re.IGNORECASE)
            if match:
                citations = int(match.group(1))

        # DOI extraction if present in URL
        doi = None
        if url and "doi.org/" in url:
            match = re.search(r'doi\.org/(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)', url)
            if match:
                doi = match.group(1)

        paper = Paper(
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            citations=citations,
            doi=doi,
            url=url,
            abstract=abstract,
            source_provider="google_scholar"
        )
        papers.append(paper)

    return papers


class GoogleScholarProvider(BaseProvider):
    """Google Scholar HTML scraper provider with Playwright CAPTCHA solver fallback."""
    name = "google_scholar"
    BASE_URL = "https://scholar.google.com/scholar"
    PROFILE_URL = "https://scholar.google.com/citations"

    @staticmethod
    def _is_blocked(status_code: int, url: str, html: str) -> bool:
        """Detects Google Scholar CAPTCHA / rate-limit responses."""
        return (
            status_code == 429 or
            "sorry/index" in url or
            "recaptcha" in html.lower() or
            "please show you're not a robot" in html.lower()
        )

    async def _fetch_scholar(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict,
        cookies: dict[str, str] | None = None,
    ) -> str:
        """GETs a Scholar URL; if blocked, solves the CAPTCHA via Playwright and retries.

        Raises RuntimeError if still blocked after the interactive solve.
        """
        # Register cookies in the client jar with the Scholar domain so they are
        # forwarded across redirects (e.g. scholar.google.com -> www.scholar.google.com).
        if cookies:
            for name, value in cookies.items():
                client.cookies.set(name, value, domain=".scholar.google.com", path="/")

        resp = await client.get(url, params=params)
        html_content = resp.text
        if not self._is_blocked(resp.status_code, str(resp.url), html_content):
            return html_content

        # Trigger Playwright CAPTCHA solver
        new_cookies = await solve_google_scholar_captcha(str(resp.url))
        if new_cookies:
            for name, value in new_cookies.items():
                client.cookies.set(name, value, domain=".scholar.google.com", path="/")
        retry_resp = await client.get(url, params=params)
        retry_html = retry_resp.text
        if self._is_blocked(retry_resp.status_code, str(retry_resp.url), retry_html):
            raise RuntimeError(
                "Google Scholar is still blocking requests after CAPTCHA solve. "
                "Try again later or solve the CAPTCHA in your browser manually."
            )
        return retry_html

    async def search(self, query: str, limit: int = 50, **kwargs) -> QueryResult:
        start_time = time.time()
        author = kwargs.get("author")
        journal = kwargs.get("journal")
        year_from = kwargs.get("year_from")
        year_to = kwargs.get("year_to")
        min_citations = kwargs.get("min_citations")

        search_terms = [query] if query else []
        if author:
            search_terms.append(f'author:"{author}"')
        if journal:
            search_terms.append(f'source:"{journal}"')

        full_query = " ".join(search_terms).strip()

        cookies = load_cookies()
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9"
        }

        page_size = min(limit, 20)

        base_params: dict[str, str | int] = {
            "q": full_query,
            "hl": "en",
            "num": page_size
        }
        if year_from is not None:
            base_params["as_ylo"] = year_from
        if year_to is not None:
            base_params["as_yhi"] = year_to

        timeout = load_config().get("google_scholar_timeout", 25.0)
        collected_papers: list[Paper] = []
        offset = 0
        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
            while offset < limit:
                page_params = dict(base_params)
                if offset:
                    page_params["start"] = offset
                html_content = await self._fetch_scholar(client, self.BASE_URL, page_params, cookies=cookies)
                page_papers = parse_google_scholar_html(html_content)
                collected_papers.extend(page_papers)
                if not page_papers:
                    break  # No further pages available
                offset += page_size
                if offset >= limit * 2:
                    break  # Safety cap: prevent runaway pagination

        papers = self.filter_papers(collected_papers[:limit], year_from=year_from, year_to=year_to, min_citations=min_citations)
        metrics = calculate_metrics(papers)
        elapsed = round(time.time() - start_time, 2)

        return QueryResult(
            query=query,
            provider=self.name,
            total_found=len(papers),
            papers=papers,
            metrics=metrics,
            search_time_seconds=elapsed
        )

    async def search_profile(self, user_id: str, limit: int = 100, **kwargs) -> QueryResult:
        """Harvests publications directly from a Google Scholar user profile ID."""
        start_time = time.time()
        year_from = kwargs.get("year_from")
        year_to = kwargs.get("year_to")
        min_citations = kwargs.get("min_citations")

        cookies = load_cookies()
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9"
        }

        page_size = min(limit, 100)
        collected_papers: list[Paper] = []
        cstart = 0

        timeout = load_config().get("google_scholar_timeout", 25.0)
        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
            while len(collected_papers) < limit:
                params: dict[str, str | int] = {
                    "user": user_id,
                    "hl": "en",
                    "cstart": cstart,
                    "pagesize": page_size
                }
                html_content = await self._fetch_scholar(client, self.PROFILE_URL, params, cookies=cookies)
                page_papers = parse_google_scholar_profile_html(html_content)
                if not page_papers:
                    break  # No further pages available
                collected_papers.extend(page_papers)
                cstart += page_size
                if cstart >= limit * 2:
                    break  # Safety cap: prevent runaway pagination

        papers = self.filter_papers(collected_papers[:limit], year_from=year_from, year_to=year_to, min_citations=min_citations)
        metrics = calculate_metrics(papers)
        elapsed = round(time.time() - start_time, 2)

        return QueryResult(
            query=f"Google Scholar Profile: {user_id}",
            provider="google_scholar_profile",
            total_found=len(papers),
            papers=papers,
            metrics=metrics,
            search_time_seconds=elapsed
        )


def parse_google_scholar_profile_html(html_content: str) -> list[Paper]:
    """Parses Google Scholar profile page HTML into a list of Paper objects."""
    soup = BeautifulSoup(html_content, "html.parser")
    rows = soup.select(".gsc_a_tr")
    papers: list[Paper] = []

    for row in rows:
        title_tag = row.select_one(".gsc_a_at")
        if not title_tag:
            continue
        title = title_tag.text.strip()
        raw_url = title_tag.get("href")
        url = None
        if raw_url:
            if raw_url.startswith("http"):
                url = raw_url
            else:
                url = f"https://scholar.google.com{raw_url}"

        gray_tags = row.select(".gs_gray")
        authors: list[Author] = []
        journal = None

        if len(gray_tags) >= 1:
            raw_authors = gray_tags[0].text.strip().split(",")
            authors = [Author(name=a.strip()) for a in raw_authors if a.strip()]
        if len(gray_tags) >= 2:
            journal = gray_tags[1].text.strip()

        citations = 0
        cite_tag = row.select_one(".gsc_a_ac")
        if cite_tag and cite_tag.text.strip().isdigit():
            citations = int(cite_tag.text.strip())

        year = None
        year_tag = row.select_one(".gsc_a_y span")
        if year_tag and year_tag.text.strip().isdigit():
            year = int(year_tag.text.strip())

        paper = Paper(
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            citations=citations,
            url=url,
            source_provider="google_scholar"
        )
        papers.append(paper)

    return papers
