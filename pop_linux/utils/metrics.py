import math
from datetime import datetime, timezone

from pop_linux.models import Metrics, Paper


def calculate_metrics(papers: list[Paper]) -> Metrics:
    """
    Computes Harzing bibliometric metrics from a list of Paper objects.
    Calculates: Total Papers, Total Citations, Average Citations/Paper,
    Citations/Author, h-index, g-index, e-index, hI-annual index, and i10-index.
    """
    if not papers:
        return Metrics()

    total_papers = len(papers)
    # Sort papers in descending order of citation counts
    sorted_citations = sorted([p.citations for p in papers], reverse=True)
    total_citations = sum(sorted_citations)
    avg_citations_per_paper = total_citations / total_papers

    # Citations per author (normalized sum of c_i / author_count_i)
    citations_per_author = sum(p.citations / p.author_count for p in papers)

    # 1. h-index: largest h where h papers have >= h citations
    h_index = 0
    for i, c in enumerate(sorted_citations, start=1):
        if c >= i:
            h_index = i
        else:
            break

    # 2. g-index: largest g where sum of top g citations >= g^2
    g_index = 0
    cum_sum = 0
    for i, c in enumerate(sorted_citations, start=1):
        cum_sum += c
        if cum_sum >= i * i:
            g_index = i

    # 3. e-index: sqrt(sum(c_i - h) for top h papers)
    e_index = 0.0
    if h_index > 0:
        h_core_citations = sorted_citations[:h_index]
        excess_citations = sum(c - h_index for c in h_core_citations)
        e_index = math.sqrt(max(0, excess_citations))

    # 4. hI-annual: (sum(c_i / author_count) for top h papers) / years_span
    hI_annual = 0.0
    if h_index > 0:
        # Find minimum publication year among all papers with valid years
        valid_years = [p.year for p in papers if p.year is not None and p.year > 1800]
        current_year = datetime.now(timezone.utc).year
        if valid_years:
            min_year = min(valid_years)
            years_span = float(max(1, current_year - min_year + 1))
        else:
            years_span = 1.0

        # Normalized citations in h-core
        sorted_papers = sorted(papers, key=lambda p: p.citations, reverse=True)
        h_core_papers = sorted_papers[:h_index]
        norm_h_citations = sum(p.citations / p.author_count for p in h_core_papers)
        hI_annual = norm_h_citations / years_span

    # 5. hL_norm: h-index computed over normalized citations (citations / author_count)
    norm_citations = sorted([p.citations / p.author_count for p in papers], reverse=True)
    hL_norm = 0.0
    for i, nc in enumerate(norm_citations, start=1):
        if nc >= i:
            hL_norm = float(i)
        else:
            break

    # 6. AWCR (Age-Weighted Citation Rate) and AW-index
    current_year = datetime.now(timezone.utc).year
    awcr = 0.0
    for p in papers:
        if p.citations > 0:
            pub_year = p.year if (p.year and p.year > 1800 and p.year <= current_year) else current_year
            age = max(1, current_year - pub_year + 1)
            awcr += p.citations / age

    aw_index = math.sqrt(awcr)

    # 7. i10-index: count of papers with citations >= 10
    i10_index = sum(1 for c in sorted_citations if c >= 10)

    return Metrics(
        total_papers=total_papers,
        total_citations=total_citations,
        avg_citations_per_paper=round(avg_citations_per_paper, 2),
        citations_per_author=round(citations_per_author, 2),
        h_index=h_index,
        g_index=g_index,
        e_index=round(e_index, 2),
        hI_annual=round(hI_annual, 2),
        hL_norm=round(hL_norm, 2),
        awcr=round(awcr, 2),
        aw_index=round(aw_index, 2),
        i10_index=i10_index
    )
