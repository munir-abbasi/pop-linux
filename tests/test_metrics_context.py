"""Packet 16 tests: metrics reproducibility and calculation context."""

from datetime import datetime, timezone

from pop_linux.execution import execute_request
from pop_linux.execution_models import SearchRequest
from pop_linux.models import Author, Paper
from pop_linux.utils.metrics import calculate_metrics


def _paper(citations: int, year: int | None) -> Paper:
    return Paper(title=f"P{citations}", citations=citations, year=year, authors=[Author(name="A")])


# ---------------------------------------------------------------------------
# as_of_year reproducibility (formulas unchanged; only the time basis is pinned)
# ---------------------------------------------------------------------------


def test_default_behavior_equals_prior_utc_year_semantics():
    """Default path must remain identical to the pre-Packet-16 behavior."""
    papers = [_paper(10, 2020), _paper(5, 2022)]
    m_default = calculate_metrics(papers)
    m_explicit = calculate_metrics(papers, as_of_year=datetime.now(timezone.utc).year)
    assert m_default.awcr == m_explicit.awcr
    assert m_default.hI_annual == m_explicit.hI_annual
    assert m_default.aw_index == m_explicit.aw_index


def test_as_of_year_pins_age_derived_metrics():
    papers = [_paper(10, 2020)]
    now_metrics = calculate_metrics(papers, as_of_year=2026)
    later_metrics = calculate_metrics(papers, as_of_year=2036)
    # Same citations, older effective "now" -> higher per-year rates in the earlier year
    assert later_metrics.awcr < now_metrics.awcr
    assert later_metrics.hI_annual < now_metrics.hI_annual
    # Non-age metrics are unaffected by the time basis
    assert now_metrics.h_index == later_metrics.h_index == 1
    assert now_metrics.total_citations == later_metrics.total_citations == 10


def test_as_of_year_reproducible_across_calls():
    papers = [_paper(8, 2019), _paper(3, 2023)]
    m1 = calculate_metrics(papers, as_of_year=2030)
    m2 = calculate_metrics(papers, as_of_year=2030)
    assert m1.awcr == m2.awcr and m1.hI_annual == m2.hI_annual


def test_unknown_year_paper_uses_effective_year_for_age():
    """Papers with unknown/invalid years currently age from the effective year."""
    papers = [_paper(6, None)]
    m_2026 = calculate_metrics(papers, as_of_year=2026)
    assert m_2026.awcr > 0  # age defaults to 1 from effective year


# ---------------------------------------------------------------------------
# Engine populates calculation context
# ---------------------------------------------------------------------------


def test_engine_metrics_context_records_calculation_year_and_timestamp():
    from unittest.mock import AsyncMock, MagicMock

    import pop_linux.execution as em
    from pop_linux.providers.base import ProviderFetchResult

    provider = MagicMock()
    provider.name = "openalex"
    provider.fetch = AsyncMock(
        return_value=ProviderFetchResult(
            papers=[_paper(4, 2021)], matched_count=1, fetched_count=1, returned_count=1
        )
    )
    monkey = em.resolve_providers
    em.resolve_providers = lambda req: [provider]
    try:
        env = execute_request(SearchRequest(query="ctx", providers=["openalex"], limit=5))
    finally:
        em.resolve_providers = monkey

    ctx = env.metrics_context
    assert ctx is not None
    assert ctx.calculation_year == datetime.now(timezone.utc).year
    assert ctx.calculation_timestamp is not None
    parsed = datetime.fromisoformat(ctx.calculation_timestamp)
    assert parsed.tzinfo is not None  # timezone-aware UTC timestamp persisted
