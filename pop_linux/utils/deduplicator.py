import re
from difflib import SequenceMatcher
from pop_linux.models import Paper


def normalize_doi(doi: str | None) -> str | None:
    """Normalizes DOI string by removing HTTP/HTTPS prefixes and converting to lowercase."""
    if not doi:
        return None
    cleaned = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE)
    return cleaned.lower() if cleaned else None


def normalize_title(title: str) -> str:
    """Cleans title by removing non-alphanumeric characters and converting to lowercase."""
    return re.sub(r"[^\w\s]", "", title.lower()).strip()


def is_same_paper(p1: Paper, p2: Paper) -> bool:
    """Determines if two paper objects represent the same publication."""
    # 1. Exact DOI match
    doi1 = normalize_doi(p1.doi)
    doi2 = normalize_doi(p2.doi)
    if doi1 and doi2 and doi1 == doi2:
        return True

    # 2. Fuzzy Title match (SequenceMatcher >= 0.92) when years match or are missing
    t1 = normalize_title(p1.title)
    t2 = normalize_title(p2.title)
    if not t1 or not t2:
        return False

    if p1.year and p2.year and p1.year != p2.year:
        return False

    similarity = SequenceMatcher(None, t1, t2).ratio()
    return similarity >= 0.92


def merge_paper_pair(p1: Paper, p2: Paper) -> Paper:
    """Merges two duplicate paper objects, preserving maximum metadata and highest citation count."""
    best_citations = max(p1.citations, p2.citations)
    best_doi = p1.doi or p2.doi
    best_url = p1.url or p2.url
    best_abstract = p1.abstract if (p1.abstract and len(p1.abstract) >= len(p2.abstract or "")) else (p2.abstract or p1.abstract)
    best_journal = p1.journal or p2.journal
    best_year = p1.year or p2.year
    best_authors = p1.authors if len(p1.authors) >= len(p2.authors) else p2.authors

    providers = set()
    if p1.source_provider:
        providers.update(p1.source_provider.split(","))
    if p2.source_provider:
        providers.update(p2.source_provider.split(","))

    combined_provider = ",".join(sorted(providers))

    return Paper(
        title=p1.title if len(p1.title) >= len(p2.title) else p2.title,
        authors=best_authors,
        year=best_year,
        journal=best_journal,
        citations=best_citations,
        doi=best_doi,
        url=best_url,
        abstract=best_abstract,
        source_provider=combined_provider,
        paper_id=p1.paper_id or p2.paper_id
    )


def deduplicate_papers(papers: list[Paper]) -> list[Paper]:
    """Deduplicates a list of Paper objects by merging duplicate records."""
    if not papers:
        return []

    unique_papers: list[Paper] = []
    doi_index: dict[str, int] = {}  # normalized DOI -> index into unique_papers

    for paper in papers:
        doi_key = normalize_doi(paper.doi)
        doi_hit = doi_index.get(doi_key) if doi_key else None

        if doi_hit is not None:
            unique_papers[doi_hit] = merge_paper_pair(unique_papers[doi_hit], paper)
            continue

        merged = False
        for idx, existing in enumerate(unique_papers):
            if is_same_paper(paper, existing):
                unique_papers[idx] = merge_paper_pair(existing, paper)
                merged_doi = normalize_doi(unique_papers[idx].doi)
                if merged_doi and merged_doi not in doi_index:
                    doi_index[merged_doi] = idx
                merged = True
                break
        if not merged:
            doi_key = normalize_doi(paper.doi)
            if doi_key:
                doi_index[doi_key] = len(unique_papers)
            unique_papers.append(paper)

    return unique_papers
