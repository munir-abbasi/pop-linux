"""Deduplication merge policy.

Equivalence decisions are owned exclusively by pop_linux.utils.identity (the
single publication-identity service). This module retains the merge policy
(preferred-value selection) and the DOI-index fast path, and delegates
equivalence to the identity service.

Identity helpers remain importable from here for backwards compatibility, but
they are thin re-exports; new code must import from pop_linux.utils.identity
directly.
"""

from pop_linux.models import Paper
from pop_linux.utils.identity import is_same_paper, normalize_doi, normalize_title

__all__ = [
    "deduplicate_papers",
    "is_same_paper",
    "merge_paper_pair",
    "normalize_doi",
    "normalize_title",
]


def merge_paper_pair(p1: Paper, p2: Paper) -> Paper:
    """Merges two duplicate paper objects, preserving maximum metadata and highest citation count.

    The citation policy is explicitly `max_observed` (see MetricsContext); the
    losing observation is retained at the provenance layer (Packet 7).
    """
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
    """Deduplicates a list of Paper objects by merging duplicate records.

    Equivalence is decided by the shared identity service; the DOI index is
    the fast path. A fuzzy merge that acquires a DOI registers it in the index
    so later identical-DOI records hit the fast path.
    """
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
            if doi_key:
                doi_index[doi_key] = len(unique_papers)
            unique_papers.append(paper)

    return unique_papers
