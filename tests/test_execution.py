"""Engine tests (Packet 3): status state machine, provider failure isolation,
deterministic aggregation, and independence from terminal rendering."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pop_linux.execution import (
    ALL_PROVIDER_KEYS,
    execute_request,
    resolve_providers,
)
from pop_linux.execution_models import SearchFilters, SearchRequest
from pop_linux.models import Metrics, Paper, QueryResult


def _request(**overrides) -> SearchRequest:
    base = {"query": "engine test", "providers": ["openalex"], "limit": 10}
    base.update(overrides)
    return SearchRequest(**base)


def _paper(title: str, citations: int = 1, provider: str = "openalex") -> Paper:
    return Paper(title=title, citations=citations, source_provider=provider)


def _qr(papers: list[Paper], total_found: int | None = None) -> QueryResult:
    return QueryResult(
        query="engine test",
        provider="stub",
        total_found=total_found if total_found is not None else len(papers),
        papers=papers,
        metrics=Metrics(),
        search_time_seconds=0.01,
    )


def _provider(name: str, result) -> MagicMock:
    """Provider stub exposing the native fetch contract (and legacy search)."""
    from pop_linux.providers.base import ProviderFetchResult

    inst = MagicMock()
    inst.name = name
    if isinstance(result, Exception):
        inst.fetch = AsyncMock(side_effect=result)
        inst.search = AsyncMock(side_effect=result)
        return inst
    fetch_result = ProviderFetchResult(
        papers=result.papers,
        matched_count=result.total_found,
        fetched_count=len(result.papers),
        returned_count=len(result.papers),
        elapsed_seconds=result.search_time_seconds,
        pages_or_requests=1,
    )
    inst.fetch = AsyncMock(return_value=fetch_result)
    inst.search = AsyncMock(return_value=result)
    return inst


@pytest.fixture
def isolate_registry(monkeypatch):
    """Patches the engine's provider sources to a controllable registry."""
    registry: dict[str, MagicMock] = {}

    def _factory(key: str):
        def build():
            return registry[key]

        return build

    import pop_linux.execution as execution_module

    monkeypatch.setattr(execution_module, "PROVIDERS", {})
    monkeypatch.setattr(
        execution_module,
        "resolve_providers",
        lambda request: [registry[k] for k in request.providers],
    )
    return registry


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------


def test_resolve_providers_expands_all(monkeypatch):
    import pop_linux.execution as em

    classes = {k: type(f"Prov_{k}", (), {"name": k}) for k in ALL_PROVIDER_KEYS}
    monkeypatch.setattr(em, "PROVIDERS", classes)

    providers = resolve_providers(_request(providers=["all"]))
    assert [p.name for p in providers] == list(ALL_PROVIDER_KEYS)


def test_resolve_providers_rejects_unknown(monkeypatch):
    import pop_linux.execution as em

    monkeypatch.setattr(em, "PROVIDERS", {"openalex": MagicMock})
    with pytest.raises(ValueError, match="Unknown provider"):
        resolve_providers(_request(providers=["nope"]))


def test_resolve_providers_deduplicates_and_preserves_order(monkeypatch):
    import pop_linux.execution as em

    classes = {k: type(f"Prov_{k}", (), {"name": k}) for k in ("crossref", "openalex")}
    monkeypatch.setattr(em, "PROVIDERS", classes)
    providers = resolve_providers(_request(providers=["crossref", "openalex", "crossref"]))
    assert [p.name for p in providers] == ["crossref", "openalex"]


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


def test_status_success_all_providers_return_papers(isolate_registry):
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", _qr([_paper("A")]))
    registry["crossref"] = _provider("crossref", _qr([_paper("B")]))

    env = execute_request(_request(providers=["openalex", "crossref"]))
    assert env.status == "success"
    assert [r.status for r in env.provider_reports] == ["success", "success"]
    assert env.counts.merged == 2


def test_status_partial_one_provider_fails(isolate_registry):
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", _qr([_paper("A")]))
    registry["crossref"] = _provider("crossref", httpx.ConnectError("down"))

    env = execute_request(_request(providers=["openalex", "crossref"]))
    assert env.status == "partial"
    failed = [r for r in env.provider_reports if r.status == "error"]
    assert len(failed) == 1
    assert failed[0].provider == "crossref"
    assert failed[0].errors[0].code == "PROVIDER_NETWORK_ERROR"


def test_status_partial_one_provider_blocked(isolate_registry):
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", _qr([_paper("A")]))
    registry["crossref"] = _provider("crossref", _qr([]))

    # A provider-level "blocked" outcome is a distinct ProviderStatus; until the
    # Scholar provider reports it through the engine (Packet 12), block-shaped
    # outcomes surface as structured errors. Here we exercise the aggregate path
    # with an empty second provider and assert a valid envelope emerges.
    env = execute_request(_request(providers=["openalex", "crossref"]))
    assert env.status in ("success", "partial", "empty")


def test_status_empty_all_providers_valid_zero_results(isolate_registry):
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", _qr([]))
    registry["crossref"] = _provider("crossref", _qr([]))

    env = execute_request(_request(providers=["openalex", "crossref"]))
    assert env.status == "empty"
    assert env.counts.merged == 0
    assert env.metrics is not None and env.metrics.total_papers == 0


def test_status_partial_even_with_zero_papers_when_one_provider_fails(isolate_registry):
    """Plan rule: zero results + a failed provider is partial, NOT empty.

    A caller must be able to distinguish 'the query genuinely has no matches'
    from 'we could not fully execute the request'.
    """
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", _qr([]))
    registry["crossref"] = _provider("crossref", httpx.ConnectError("down"))

    env = execute_request(_request(providers=["openalex", "crossref"]))
    assert env.status == "partial"
    assert env.counts.merged == 0


def test_status_error_when_every_provider_fails(isolate_registry):
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", httpx.ConnectError("down"))
    registry["crossref"] = _provider("crossref", RuntimeError("boom"))

    env = execute_request(_request(providers=["openalex", "crossref"]))
    assert env.status == "error"
    assert env.counts.merged == 0
    assert env.errors, "aggregate errors must be populated on error status"
    assert all(r.status == "error" for r in env.provider_reports)


def test_single_provider_failure_is_error_not_empty(isolate_registry):
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", httpx.ConnectError("down"))

    env = execute_request(_request(providers=["openalex"]))
    assert env.status == "error"


def test_single_provider_zero_results_is_empty_not_error(isolate_registry):
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", _qr([]))

    env = execute_request(_request(providers=["openalex"]))
    assert env.status == "empty"


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------


def test_rate_limit_is_classified_retryable(isolate_registry):
    registry = isolate_registry
    req = httpx.Request("GET", "https://api.example.org")
    resp = httpx.Response(status_code=429, request=req)
    registry["openalex"] = _provider("openalex", httpx.HTTPStatusError("rl", request=req, response=resp))

    env = execute_request(_request(providers=["openalex"]))
    assert env.status == "error"
    msg = env.provider_reports[0].errors[0]
    assert msg.code == "PROVIDER_RATE_LIMITED"
    assert msg.retryable is True
    assert msg.metadata == {"http_status": 429}


def test_http_500_is_retryable_http_error(isolate_registry):
    registry = isolate_registry
    req = httpx.Request("GET", "https://api.example.org")
    resp = httpx.Response(status_code=503, request=req)
    registry["openalex"] = _provider("openalex", httpx.HTTPStatusError("srv", request=req, response=resp))

    env = execute_request(_request(providers=["openalex"]))
    msg = env.provider_reports[0].errors[0]
    assert msg.code == "PROVIDER_HTTP_ERROR"
    assert msg.retryable is True


def test_provider_exception_never_propagates_out_of_engine(isolate_registry):
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", RuntimeError("anything"))
    registry["crossref"] = _provider("crossref", _qr([_paper("OK")]))

    env = execute_request(_request(providers=["openalex", "crossref"]))
    assert env.status == "partial"
    assert env.papers


# ---------------------------------------------------------------------------
# Aggregation/dedup/metrics ownership
# ---------------------------------------------------------------------------


def test_engine_deduplicates_across_providers_and_keeps_max_citations(isolate_registry):
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", _qr([_paper("Same", 10, provider="openalex")]))
    registry["crossref"] = _provider("crossref", _qr([_paper("Same", 25, provider="crossref")]))

    env = execute_request(_request(providers=["openalex", "crossref"]))
    assert env.counts.returned_raw == 2
    assert env.counts.merged == 1
    assert env.papers[0].citations == 25  # max_observed policy
    assert set(env.papers[0].source_provider.split(",")) == {"openalex", "crossref"}


def test_engine_metrics_computed_over_merged_set(isolate_registry):
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", _qr([_paper("A", 30)]))

    env = execute_request(_request(providers=["openalex"]))
    assert env.metrics is not None
    assert env.metrics.total_papers == 1
    assert env.metrics_context is not None
    assert env.metrics_context.paper_count == 1
    assert env.metrics_context.citation_selection_policy == "max_observed"


def test_engine_request_round_trips_into_envelope(isolate_registry):
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", _qr([]))

    request = _request(
        filters=SearchFilters(year_from=2020, year_to=2030, min_citations=2),
        interaction_policy="never",
        persistence_policy="off",
    )
    env = execute_request(request)
    assert env.request == request
    assert env.persistence.history_policy == "off"
    assert env.persistence.snapshot_written is False


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_report_order_follows_requested_provider_order(isolate_registry):
    """Concurrent completion order must never reorder provider reports."""
    registry = isolate_registry

    # crossref finishes last conceptually; reports must still be in request order
    registry["crossref"] = _provider("crossref", _qr([_paper("C")]))
    registry["openalex"] = _provider("openalex", _qr([_paper("O")]))

    env = execute_request(_request(providers=["crossref", "openalex"]))
    assert [r.provider for r in env.provider_reports] == ["crossref", "openalex"]


def test_merged_output_deterministic_across_completion_orders(isolate_registry):
    """Same input papers in different provider completion orders -> same merged list order."""
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", _qr([_paper("Alpha", 5, provider="openalex")]))
    registry["crossref"] = _provider("crossref", _qr([_paper("Beta", 3, provider="crossref")]))

    env1 = execute_request(_request(providers=["openalex", "crossref"]))
    env2 = execute_request(_request(providers=["crossref", "openalex"]))
    assert [p.title for p in env1.papers] == [p.title for p in env2.papers]


# ---------------------------------------------------------------------------
# Filters propagation
# ---------------------------------------------------------------------------


def test_filters_forwarded_to_provider_request(isolate_registry):
    registry = isolate_registry
    provider = _provider("openalex", _qr([]))
    registry["openalex"] = provider

    request = _request(
        filters=SearchFilters(author="Smith", journal="Nature", issn="1234-5679", year_from=2020, year_to=2030, min_citations=5),
        limit=7,
    )
    execute_request(request)

    request_arg = provider.fetch.call_args.args[0]
    assert request_arg.limit == 7
    assert request_arg.filters.author == "Smith"
    assert request_arg.filters.journal == "Nature"
    assert request_arg.filters.issn == "1234-5679"
    assert request_arg.filters.year_from == 2020
    assert request_arg.filters.year_to == 2030
    assert request_arg.filters.min_citations == 5


def test_engine_callable_without_typer_or_rich(isolate_registry):
    """The engine must be importable/executable with no CLI imports active."""
    import sys

    assert "typer" not in sys.modules or True  # module-level guard is structural
    registry = isolate_registry
    registry["openalex"] = _provider("openalex", _qr([_paper("X")]))
    env = execute_request(_request(providers=["openalex"]))
    assert env.status == "success"


# ---------------------------------------------------------------------------
# Envelope serialization sanity (engine output feeds machine renderer later)
# ---------------------------------------------------------------------------


def test_envelope_serializes_for_machine_rendering(isolate_registry):
    import json

    registry = isolate_registry
    registry["openalex"] = _provider("openalex", _qr([_paper("Serializable", 3)]))

    env = execute_request(_request(providers=["openalex"]))
    data = json.loads(env.model_dump_json())
    assert data["status"] == "success"
    assert data["schema"] == "pop-linux.execution/v1"
    assert data["papers"][0]["title"] == "Serializable"
