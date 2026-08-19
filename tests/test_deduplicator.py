from pop_linux.models import Paper, Author
from pop_linux.utils.deduplicator import deduplicate_papers, is_same_paper, normalize_doi, normalize_title


def test_normalize_doi():
    assert normalize_doi("https://doi.org/10.1016/j.jaci.2020.01.001") == "10.1016/j.jaci.2020.01.001"
    assert normalize_doi("http://dx.doi.org/10.1000/182") == "10.1000/182"
    assert normalize_doi("10.1000/182") == "10.1000/182"
    assert normalize_doi(None) is None


def test_normalize_title():
    assert normalize_title("Asthma & COPD: A Review!") == "asthma  copd a review"


def test_is_same_paper():
    p1 = Paper(title="Asthma Management Guidelines", doi="10.1000/123", year=2021)
    p2 = Paper(title="Asthma Management Guidelines", doi="https://doi.org/10.1000/123", year=2021)
    p3 = Paper(title="Asthma Management Guideline", doi=None, year=2021)
    p4 = Paper(title="Different Paper Entirely", doi="10.1000/999", year=2021)

    assert is_same_paper(p1, p2) is True
    assert is_same_paper(p1, p3) is True
    assert is_same_paper(p1, p4) is False


def test_deduplicate_papers():
    p1 = Paper(title="Paper One", citations=10, doi="10.1000/1", source_provider="openalex", authors=[Author(name="Alice")])
    p2 = Paper(title="Paper One", citations=15, doi="10.1000/1", source_provider="crossref", authors=[Author(name="Alice"), Author(name="Bob")])
    p3 = Paper(title="Paper Two", citations=5, doi="10.1000/2", source_provider="pubmed")

    deduped = deduplicate_papers([p1, p2, p3])
    assert len(deduped) == 2
    merged = [p for p in deduped if p.doi == "10.1000/1"][0]
    assert merged.citations == 15
    assert len(merged.authors) == 2
    assert "crossref" in merged.source_provider
    assert "openalex" in merged.source_provider


def test_deduplicate_papers_doi_index_and_fuzzy_fallback():
    p_no_doi = Paper(title="Title A", citations=5, year=2021)
    p_doi = Paper(title="Title A", citations=9, doi="10.1000/x", year=2021)
    p_dup = Paper(title="Title A", citations=12, doi="10.1000/x", year=2021)

    deduped = deduplicate_papers([p_no_doi, p_doi, p_dup])
    assert len(deduped) == 1
    # Fuzzy merge registered the DOI; the third hit resolves via the index.
    assert deduped[0].citations == 12
    assert deduped[0].doi == "10.1000/x"


def test_deduplicate_papers_doi_index_does_not_false_merge():
    p1 = Paper(title="Uniquely Different One", citations=1, doi="10.1000/a", year=2021)
    p2 = Paper(title="Totally Unrelated Title", citations=2, doi="10.1000/b", year=2021)
    deduped = deduplicate_papers([p1, p2])
    assert len(deduped) == 2  # distinct DOIs + dissimilar titles must not be merged
