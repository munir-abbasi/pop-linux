"""Tests for the execution contract models (Packet 2)."""

import json
from typing import get_args

import pytest
from pydantic import ValidationError

from pop_linux.execution_models import (
    EXECUTION_SCHEMA,
    AggregateCounts,
    CitationSelectionPolicy,
    ExecutionEnvelope,
    ExecutionMessage,
    ExecutionStatus,
    FilterMode,
    InteractionPolicy,
    MetricsContext,
    PersistencePolicy,
    PersistenceReport,
    ProviderCounts,
    ProviderReport,
    ProviderStatus,
    ResultCompleteness,
    SearchFilters,
    SearchRequest,
)
from pop_linux.models import Author, Metrics, Paper


def _request(**overrides) -> SearchRequest:
    base = {
        "query": "asthma",
        "providers": ["openalex"],
        "limit": 10,
    }
    base.update(overrides)
    return SearchRequest(**base)


def _report(provider: str = "openalex", status: ProviderStatus = "success", **overrides) -> ProviderReport:
    base = {
        "provider": provider,
        "status": status,
        "counts": ProviderCounts(matched=5, fetched=5, after_filter=4, returned=4),
    }
    base.update(overrides)
    return ProviderReport(**base)


def _envelope(**overrides) -> ExecutionEnvelope:
    base = {
        "app_version": "0.1.0",
        "status": "success",
        "request": _request(),
        "provider_reports": [_report()],
        "counts": AggregateCounts(returned_raw=4, merged=4),
        "papers": [Paper(title="T", citations=1)],
        "metrics": Metrics(total_papers=1, total_citations=1),
        "elapsed_seconds": 0.5,
    }
    base.update(overrides)
    return ExecutionEnvelope(**base)


# ---------------------------------------------------------------------------
# Literal-typed enums: values are stable plain strings
# ---------------------------------------------------------------------------


def test_enum_values_are_stable_strings():
    assert set(get_args(ExecutionStatus)) == {"success", "partial", "empty", "error"}
    assert set(get_args(ProviderStatus)) == {"success", "empty", "error", "blocked", "skipped"}
    assert set(get_args(FilterMode)) == {"native", "query_hint", "post_filter", "unsupported"}
    assert set(get_args(InteractionPolicy)) == {"allow", "never"}
    assert set(get_args(PersistencePolicy)) == {"auto", "off", "explicit"}
    assert set(get_args(CitationSelectionPolicy)) == {"provider_native", "max_observed"}
    assert set(get_args(ResultCompleteness)) == {"complete", "partial", "bounded"}


def test_schema_identifier_is_explicit_and_versioned():
    assert EXECUTION_SCHEMA == "pop-linux.execution/v1"
    env = _envelope()
    assert env.schema_ == "pop-linux.execution/v1"
    # Wire key stays "schema" via the serialization alias
    assert json.loads(env.model_dump_json())["schema"] == "pop-linux.execution/v1"
    # Schema identity is fixed, not derived from app version
    env2 = _envelope(app_version="9.9.9")
    assert env2.schema_ == EXECUTION_SCHEMA


# ---------------------------------------------------------------------------
# SearchFilters validation
# ---------------------------------------------------------------------------


def test_filters_defaults_and_acceptance():
    f = SearchFilters()
    assert f.author is None and f.year_from is None and f.min_citations is None
    f2 = SearchFilters(year_from=2020, year_to=2030, min_citations=5)
    assert f2.year_from == 2020


def test_filters_reject_incoherent_year_bounds():
    with pytest.raises(ValidationError):
        SearchFilters(year_from=2030, year_to=2020)


def test_filters_reject_negative_bounds():
    with pytest.raises(ValidationError):
        SearchFilters(min_citations=-1)


def test_filters_forbid_unknown_fields():
    with pytest.raises(ValidationError):
        SearchFilters(api_key="secret")


# ---------------------------------------------------------------------------
# SearchRequest validation
# ---------------------------------------------------------------------------


def test_request_defaults():
    req = _request()
    assert req.filters.author is None
    assert req.interaction_policy == "allow"
    assert req.persistence_policy == "auto"


def test_request_requires_positive_limit():
    with pytest.raises(ValidationError):
        _request(limit=0)


def test_request_requires_nonempty_providers():
    with pytest.raises(ValidationError):
        _request(providers=[])


def test_request_rejects_empty_provider_names():
    with pytest.raises(ValidationError):
        _request(providers=["openalex", "  "])


def test_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        _request(api_key="secret")


def test_request_serializes_policies_as_plain_strings():
    req = _request(interaction_policy="never", persistence_policy="off")
    data = json.loads(req.model_dump_json())
    assert data["interaction_policy"] == "never"
    assert data["persistence_policy"] == "off"
    assert isinstance(data["filters"], dict)


# ---------------------------------------------------------------------------
# ExecutionMessage
# ---------------------------------------------------------------------------


def test_message_shape():
    msg = ExecutionMessage(
        code="PROVIDER_HTTP_ERROR",
        message="upstream 500",
        provider="openalex",
        retryable=True,
        metadata={"status": 500},
    )
    assert msg.code == "PROVIDER_HTTP_ERROR"
    assert msg.retryable is True


# ---------------------------------------------------------------------------
# ProviderReport / ProviderCounts
# ---------------------------------------------------------------------------


def test_report_counts_distinct_concepts():
    report = _report()
    assert report.counts.matched == 5
    assert report.counts.fetched == 5
    assert report.counts.after_filter == 4
    assert report.counts.returned == 4


def test_report_partial_failure_shape():
    report = _report(
        provider="semanticscholar",
        status="error",
        filter_modes={"issn": "query_hint"},
        errors=[ExecutionMessage(code="PROVIDER_HTTP_ERROR", message="boom", provider="semanticscholar")],
    )
    data = json.loads(report.model_dump_json())
    assert data["status"] == "error"
    assert data["errors"][0]["code"] == "PROVIDER_HTTP_ERROR"


# ---------------------------------------------------------------------------
# MetricsContext / PersistenceReport
# ---------------------------------------------------------------------------


def test_metrics_context_defaults_name_max_observed_policy():
    ctx = MetricsContext(paper_count=4, providers_contributing=["openalex"])
    assert ctx.citation_selection_policy == "max_observed"
    assert ctx.completeness == "complete"


def test_metrics_context_serializes_policy():
    ctx = MetricsContext(citation_selection_policy="max_observed", bounded_by_limit=True)
    data = json.loads(ctx.model_dump_json())
    assert data["citation_selection_policy"] == "max_observed"


def test_persistence_report_defaults_to_no_side_effects():
    pr = PersistenceReport()
    assert pr.snapshot_written is False
    assert pr.exported == []
    assert pr.errors == []


# ---------------------------------------------------------------------------
# Envelope round-trip
# ---------------------------------------------------------------------------


def test_envelope_json_round_trip():
    env = _envelope(
        status="partial",
        metrics_context=MetricsContext(paper_count=4, providers_contributing=["openalex"]),
        warnings=[ExecutionMessage(code="FILTER_APPROXIMATED", message="issn approximated", provider="semanticscholar")],
    )
    raw = env.model_dump_json()
    data = json.loads(raw)
    assert data["schema"] == "pop-linux.execution/v1"
    assert data["status"] == "partial"

    restored = ExecutionEnvelope.model_validate(data)
    assert restored == env  # Pydantic equality over all nested models


def test_envelope_rejects_unknown_status():
    with pytest.raises(ValidationError):
        _envelope(status="catastrophe")


def test_envelope_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        _envelope(api_key="secret")


def test_envelope_additive_optional_metadata():
    """Optional metadata can be present or absent without breaking validation."""
    minimal = _envelope(metrics_context=None)
    assert minimal.metrics_context is None
    full = _envelope(
        metrics_context=MetricsContext(),
        persistence=PersistenceReport(snapshot_written=True, snapshot_id=9),
    )
    assert full.persistence.snapshot_id == 9


def test_envelope_papers_use_stable_domain_model():
    env = _envelope(papers=[Paper(title="X", authors=[Author(name="A")], citations=7)])
    data = json.loads(env.model_dump_json())
    assert data["papers"][0]["title"] == "X"
    assert data["papers"][0]["citations"] == 7
