"""Provenance tests (Packet 7): source observations, merge traceability,
and the explicitly named max_observed citation policy."""

import json
from unittest.mock import AsyncMock, MagicMock

from pop_linux.execution import execute_request
from pop_linux.execution_models import SearchRequest
from pop_linux.models import Metrics, Paper, QueryResult


def _request(providers: list[str]) -> SearchRequest:
    return SearchRequest(query="prov test", providers=providers, limit=10)


def _paper(title: str, citations: int = 1, provider: str = "openalex", doi: str | None = None, **kw) -> Paper:
    return Paper(title=title, citations=citations, source_provider=provider, doi=doi, **kw)


def _qr(papers: list[Paper], total_found: int | None = None) -> QueryResult:
    return QueryResult(
        query="prov test",
        provider="stub",
        total_found=total_found if total_found is not None else len(papers),
        papers=papers,
        metrics=Metrics(),
        search_time_seconds=0.01,
    )


def _provider(name: str, result) -> MagicMock:
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


def _registry(monkeypatch, registry: dict[str, MagicMock]):
    import pop_linux.execution as em

    monkeypatch.setattr(
        em,
        "resolve_providers",
        lambda request: [registry[k] for k in request.providers],
    )


def test_merged_citation_traces_to_observations(monkeypatch):
    _registry(
        monkeypatch,
        {
            "openalex": _provider("openalex", _qr([_paper("Same", 10, provider="openalex", doi="10.1000/1")])),
            "crossref": _provider("crossref", _qr([_paper("Same", 25, provider="crossref", doi="10.1000/1")])),
        },
    )
    env = execute_request(_request(["openalex", "crossref"]))
    assert env.counts.merged == 1
    prov = env.provenance[0]
    assert prov.canonical_id == "doi:10.1000/1"
    assert prov.citation_selection_policy == "max_observed"
    assert len(prov.observations) == 2
    obs_cites = sorted(o.citations for o in prov.observations)
    assert obs_cites == [10, 25]
    assert prov.preferred_citation_source == "crossref"  # the 25-citation observation won
    assert env.papers[0].citations == 25


def test_lower_citation_observations_are_retained(monkeypatch):
    """The losing observation must survive; not just the max."""
    _registry(
        monkeypatch,
        {
            "openalex": _provider("openalex", _qr([_paper("Loser Retained", 3, provider="openalex", doi="10.1000/2")])),
            "crossref": _provider("crossref", _qr([_paper("Loser Retained", 40, provider="crossref", doi="10.1000/2")])),
        },
    )
    env = execute_request(_request(["openalex", "crossref"]))
    prov = env.provenance[0]
    assert any(o.provider == "openalex" and o.citations == 3 for o in prov.observations)
    assert any(o.provider == "crossref" and o.citations == 40 for o in prov.observations)


def test_provider_ids_and_doi_survive_in_observations(monkeypatch):
    _registry(
        monkeypatch,
        {
            "openalex": _provider(
                "openalex",
                _qr([_paper("With IDs", 5, provider="openalex", doi="10.1000/3", paper_id="W123", url="https://x/y")]),
            ),
            "crossref": _provider("crossref", _qr([])),
        },
    )
    env = execute_request(_request(["openalex"]))
    obs = env.provenance[0].observations[0]
    assert obs.paper_id == "W123"
    assert obs.doi == "10.1000/3"
    assert obs.url == "https://x/y"
    assert obs.provider == "openalex"


def test_metadata_conflicts_remain_inspectable(monkeypatch):
    """Two providers disagree on journal/year; both observations are kept."""
    _registry(
        monkeypatch,
        {
            "openalex": _provider(
                "openalex",
                _qr([_paper("Conflicting Meta", 7, provider="openalex", doi="10.1000/4", journal="Journal A", year=2020)]),
            ),
            "crossref": _provider(
                "crossref",
                _qr([_paper("Conflicting Meta", 9, provider="crossref", doi="10.1000/4", journal="Journal B", year=2021)]),
            ),
        },
    )
    env = execute_request(_request(["openalex", "crossref"]))
    prov = env.provenance[0]
    journals = {o.journal for o in prov.observations}
    years = {o.year for o in prov.observations}
    assert journals == {"Journal A", "Journal B"}
    assert years == {2020, 2021}
    # Preferred display values remain deterministic
    assert env.papers[0].journal in ("Journal A", "Journal B")
    assert env.papers[0].year in (2020, 2021)


def test_provenance_absent_for_error_providers_but_record_kept(monkeypatch):
    """A failed provider contributes no observations; successful ones still work."""
    _registry(
        monkeypatch,
        {
            "openalex": _provider("openalex", ConnectionError("down")),
            "crossref": _provider("crossref", _qr([_paper("Survivor", 8, provider="crossref", doi="10.1000/5")])),
        },
    )
    env = execute_request(_request(["openalex", "crossref"]))
    assert env.status == "partial"
    assert len(env.provenance) == 1
    assert [o.provider for o in env.provenance[0].observations] == ["crossref"]


def test_provenance_serializes_in_machine_envelope(monkeypatch):
    _registry(
        monkeypatch,
        {
            "openalex": _provider("openalex", _qr([_paper("Serial Prov", 4, provider="openalex", doi="10.1000/6")])),
        },
    )
    env = execute_request(_request(["openalex"]))
    data = json.loads(env.model_dump_json())
    entry = data["provenance"][0]
    assert entry["canonical_id"] == "doi:10.1000/6"
    assert entry["citation_selection_policy"] == "max_observed"
    assert entry["observations"][0]["citations"] == 4


def test_metrics_context_still_names_max_observed(monkeypatch):
    _registry(
        monkeypatch,
        {
            "openalex": _provider("openalex", _qr([_paper("Ctx", 1, provider="openalex", doi="10.1000/7")])),
        },
    )
    env = execute_request(_request(["openalex"]))
    assert env.metrics_context.citation_selection_policy == "max_observed"
    assert env.provenance[0].citation_selection_policy == "max_observed"


def test_fingerprint_records_get_stable_provenance_keys(monkeypatch):
    """DOI-less records use the fp: fingerprint as canonical id."""
    _registry(
        monkeypatch,
        {
            "openalex": _provider("openalex", _qr([_paper("No DOI Record", 2, provider="openalex", doi=None, year=2022)])),
        },
    )
    env = execute_request(_request(["openalex"]))
    assert env.provenance[0].canonical_id.startswith("fp:")
