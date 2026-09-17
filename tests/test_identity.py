"""Publication identity service tests (Packet 6): the adversarial fixture matrix.

Expected outcomes come from implementation_plan.md Phase 5 and the fixed
decision that different non-empty normalized DOIs must not fuzzy-merge.
"""

import pytest

from pop_linux.models import Paper
from pop_linux.utils.identity import (
    FUZZY_TITLE_THRESHOLD,
    compare_papers,
    identity_token,
    normalize_doi,
    normalize_title,
)


def _paper(title="Some Title", doi=None, year=None, **kwargs) -> Paper:
    return Paper(title=title, doi=doi, year=year, **kwargs)


# ---------------------------------------------------------------------------
# Normalization determinism
# ---------------------------------------------------------------------------


def test_normalize_doi_strips_prefixes_and_lowercases():
    assert normalize_doi("https://doi.org/10.1016/j.jaci.2020.01.001") == "10.1016/j.jaci.2020.01.001"
    assert normalize_doi("http://dx.doi.org/10.1000/182") == "10.1000/182"
    assert normalize_doi("10.1000/ABC") == "10.1000/abc"
    assert normalize_doi("  10.1000/x  ") == "10.1000/x"
    assert normalize_doi(None) is None
    assert normalize_doi("") is None
    assert normalize_doi("   ") is None


def test_normalize_title_unicode_and_punctuation_deterministic():
    assert normalize_title("Asthma & COPD: A Review!") == "asthma copd a review"
    assert normalize_title("Café  science") == normalize_title("caf\xe9 science")
    # NFKC fold: full-width latin becomes ascii
    assert normalize_title("Ｔｅｓｔ") == "test"
    # Multiple runs produce identical output (determinism)
    t = "Größe und Größe – Übung"
    assert normalize_title(t) == normalize_title(t)


def test_normalize_title_empty_is_falsy():
    assert normalize_title("") == ""
    assert not normalize_title("   ")


# ---------------------------------------------------------------------------
# Fixture matrix (plan Phase 5)
# ---------------------------------------------------------------------------


def test_same_doi_punctuation_title_variant_merges():
    """same DOI, punctuation/title variant -> merge (DOI rule wins)."""
    p1 = _paper("Asthma  Management: Guidelines!", doi="10.1000/abc", year=2021)
    p2 = _paper("Asthma Management Guidelines", doi="https://doi.org/10.1000/ABC", year=2021)
    decision = compare_papers(p1, p2)
    assert decision.same is True
    assert decision.reason == "doi_exact"


def test_doi_url_vs_bare_doi_merges():
    p1 = _paper("One", doi="https://doi.org/10.1000/xyz")
    p2 = _paper("One", doi="10.1000/xyz")
    assert compare_papers(p1, p2).reason == "doi_exact"


def test_different_doi_similar_title_does_not_merge():
    """THE fixed rule: different non-empty DOIs block fuzzy merge."""
    p1 = _paper("Extremely Similar Title About Asthma", doi="10.1000/aaa", year=2021)
    p2 = _paper("Extremely Similar Title About Asthma", doi="10.1000/bbb", year=2021)
    decision = compare_papers(p1, p2)
    assert decision.same is False
    assert decision.detail and "different non-empty DOIs" in decision.detail


def test_no_doi_minor_variant_same_year_merges_at_threshold():
    p1 = _paper("Asthma Management Guideline", doi=None, year=2021)
    p2 = _paper("Asthma Management Guidelines", doi=None, year=2021)
    decision = compare_papers(p1, p2)
    assert decision.same is True
    assert decision.reason == "fuzzy_title"
    assert decision.similarity >= FUZZY_TITLE_THRESHOLD


def test_no_doi_same_title_conflicting_year_no_merge():
    p1 = _paper("Same Title", year=2021)
    p2 = _paper("Same Title", year=2023)
    decision = compare_papers(p1, p2)
    assert decision.same is False
    assert decision.detail == "conflicting known years"


def test_one_doi_present_strong_match_is_explicit_fallback():
    p1 = _paper("Asthma Management Guideline", doi="10.1000/has-doi", year=2021)
    p2 = _paper("Asthma Management Guideline", doi=None, year=2021)
    decision = compare_papers(p1, p2)
    assert decision.same is True
    assert decision.reason == "fuzzy_title_doi_fallback"


def test_one_doi_present_weak_match_no_merge():
    p1 = _paper("Asthma Management Guideline", doi="10.1000/has-doi", year=2021)
    p2 = _paper("Completely Different Research Topic", doi=None, year=2021)
    assert compare_papers(p1, p2).same is False


def test_unicode_variant_outcome_deterministic():
    p1 = _paper("Respiratory – Disease: Study", doi=None, year=2020)
    p2 = _paper("Respiratory — Disease  Study", doi=None, year=2020)
    d1 = compare_papers(p1, p2)
    d2 = compare_papers(p2, p1)
    assert d1.same is True and d2.same is True
    assert d1.similarity == d2.similarity


def test_preprint_vs_final_is_conservative_default():
    """Same title, different years -> conflicting years block merge (conservative)."""
    preprint = _paper("A Study of X", year=2022)
    final = _paper("A Study of X", year=2023, doi="10.1000/final")
    assert compare_papers(preprint, final).same is False


def test_generic_short_titles_do_not_accidentally_merge():
    p1 = _paper("Review", doi=None, year=2020)
    p2 = _paper("Overview", doi=None, year=2020)
    assert compare_papers(p1, p2).same is False


def test_empty_title_never_matches():
    p1 = _paper("", doi=None)
    p2 = _paper("Anything", doi=None)
    assert compare_papers(p1, p2).same is False


# ---------------------------------------------------------------------------
# Identity token
# ---------------------------------------------------------------------------


def test_identity_token_doi_backed_is_stable_and_normalized():
    t1 = identity_token(_paper("A", doi="https://doi.org/10.1000/ABC"))
    t2 = identity_token(_paper("A", doi="10.1000/abc"))
    assert t1 == t2 == "doi:10.1000/abc"


def test_identity_token_doi_missing_is_stable_fingerprint():
    p = _paper("Title Here", year=2021)
    t1 = identity_token(p)
    t2 = identity_token(_paper("Title Here", year=2021))
    assert t1 == t2
    assert t1.startswith("fp:")
    # Different year state changes the fingerprint
    assert identity_token(_paper("Title Here", year=2022)) != t1
    # Unknown year differs from any known year
    assert identity_token(_paper("Title Here")) != t1


# ---------------------------------------------------------------------------
# Deduplicator integration (behavior change vs. baseline documented)
# ---------------------------------------------------------------------------


def test_deduplicator_respects_doi_conflict_block():
    """Regression: baseline fuzzy-merged different-DOI records; now blocked."""
    from pop_linux.utils.deduplicator import deduplicate_papers

    p1 = _paper("Extremely Similar Title About Asthma", doi="10.1000/aaa", year=2021, citations=5, source_provider="openalex")
    p2 = _paper("Extremely Similar Title About Asthma", doi="10.1000/bbb", year=2021, citations=9, source_provider="crossref")
    deduped = deduplicate_papers([p1, p2])
    assert len(deduped) == 2  # changed from baseline: no merge


def test_deduplicator_still_fast_paths_doi_index():
    from pop_linux.utils.deduplicator import deduplicate_papers

    p1 = _paper("Title A", citations=5, doi="10.1000/x", year=2021)
    p2 = _paper("Title A", citations=12, doi="10.1000/x", year=2021)
    assert len(deduplicate_papers([p1, p2])) == 1
    assert deduplicate_papers([p1, p2])[0].citations == 12


def test_deduplicator_registers_fuzzy_merged_doi_in_index():
    from pop_linux.utils.deduplicator import deduplicate_papers

    p_no_doi = _paper("Title A", citations=5, year=2021)
    p_doi = _paper("Title A", citations=9, doi="10.1000/x", year=2021)
    p_dup = _paper("Title A", citations=12, doi="10.1000/x", year=2021)
    deduped = deduplicate_papers([p_no_doi, p_doi, p_dup])
    assert len(deduped) == 1
    assert deduped[0].citations == 12


def test_merge_policy_keeps_richer_metadata():
    from pop_linux.utils.deduplicator import merge_paper_pair

    p1 = _paper("Short", citations=1, authors=[], source_provider="openalex")
    p2 = _paper("Much Longer Title Wins", citations=2, authors=[pytest.importorskip("pop_linux.models").Author(name="A")], source_provider="crossref")
    merged = merge_paper_pair(p1, p2)
    assert merged.title == "Much Longer Title Wins"
    assert merged.citations == 2
    assert set(merged.source_provider.split(",")) == {"openalex", "crossref"}
