"""Search execution engine for pop-linux.

This module owns orchestration: resolving the requested providers, running
them (concurrently for `all`), collecting per-provider outcomes, aggregating
and deduplicating papers, computing metrics, and constructing the
ExecutionEnvelope. Terminal rendering, config parsing, and Typer concerns
belong to the CLI; provider-specific retrieval belongs to providers.

The engine intentionally consumes the legacy provider `.search()` contract
during the migration window (implementation_plan.md Phase 2): provider
QueryResult responses are adapted into ProviderReport objects here. Once
providers migrate to the engine-facing fetch contract (Phase 7), this module
stops calling `.search()` while the legacy wrappers remain for library users.

Status model (Phase 2 status rules):

- success: all requested providers completed and none failed/blocked;
  at least one paper survived.
- partial: at least one provider contributed a valid execution while at
  least one requested provider failed/blocked/skipped for an execution
  reason; useful data exists.
- empty: all requested providers completed validly and no papers survived.
- error: no requested provider completed successfully enough to establish
  a valid result.
"""

import asyncio
import re
import time
from datetime import datetime, timezone

import httpx

from pop_linux import __version__
from pop_linux.execution_models import (
    AggregateCounts,
    ExecutionEnvelope,
    ExecutionMessage,
    MetricsContext,
    PersistenceReport,
    ProviderCounts,
    ProviderReport,
    ProvenanceEntry,
    SearchRequest,
    SourceObservation,
)
from pop_linux.models import Paper
from pop_linux.providers import PROVIDERS
from pop_linux.providers.base import BaseProvider
from pop_linux.providers.google_scholar import GoogleScholarProvider
from pop_linux.providers.capabilities import get_capabilities
from pop_linux.utils.deduplicator import deduplicate_papers
from pop_linux.utils.identity import identity_token
from pop_linux.utils.metrics import calculate_metrics

#: Providers included in the `all` aggregation path. Google Scholar is
#: intentionally excluded because it may require interactive browser handling.
ALL_PROVIDER_KEYS = ("openalex", "semanticscholar", "crossref", "pubmed")

#: HTTP status codes classified as rate limiting for provider messages.
_RATE_LIMIT_STATUSES = {429}

#: Secret-like material that must never pass into envelope messages.
#: Matches credential assignments (key=value / key: value), bearer/authorization
#: headers, and URLs embedding apikey/key/token query parameters.
_SECRET_LIKE_RE = re.compile(
    r"(?i)("  # group 1 wrapper
    r"(?:api[_-]?key|x-api-key|authorization|password|secret|token|api[_-]?token)\s*[:=]\s*\S+"  # key=value / key: value
    r"|bearer\s+\S+"                                       # bearer tokens
    r"|[?&](?:api[_-]?key|key|token|api[_-]?token)=[^&\s]+"  # URL query creds
    r")"
)


def redact_secrets(text: str) -> str:
    """Masks credential-shaped substrings before they enter envelope output.

    This is the single redaction point for provider-derived text: the engine
    applies it when classifying exceptions, and machine rendering inherits it.
    """
    if not text:
        return text
    return _SECRET_LIKE_RE.sub("[REDACTED]", text)


def resolve_providers(request: SearchRequest) -> list[BaseProvider]:
    """Builds provider instances for the resolved request's provider list.

    `all` expands to the non-interactive aggregation set. Unknown provider
    names raise ValueError so callers can surface a usage error before any
    network activity.
    """
    expanded: list[str] = []
    for name in request.providers:
        key = name.lower()
        if key == "all":
            expanded.extend(ALL_PROVIDER_KEYS)
        else:
            expanded.append(key)

    unique: list[str] = []
    for key in expanded:
        if key not in unique:
            unique.append(key)

    providers: list[BaseProvider] = []
    for key in unique:
        if key == "google_scholar":
            providers.append(GoogleScholarProvider())
            continue
        if key not in PROVIDERS:
            raise ValueError(f"Unknown provider '{key}'")
        providers.append(PROVIDERS[key]())
    return providers


def _filters_to_kwargs(request: SearchRequest) -> dict:
    f = request.filters
    return {
        "author": f.author,
        "journal": f.journal,
        "issn": f.issn,
        "year_from": f.year_from,
        "year_to": f.year_to,
        "min_citations": f.min_citations,
    }


def _classify_http_error(exc: httpx.HTTPStatusError) -> ExecutionMessage:
    status = exc.response.status_code
    retryable = status in _RATE_LIMIT_STATUSES or status >= 500
    code = "PROVIDER_RATE_LIMITED" if status in _RATE_LIMIT_STATUSES else "PROVIDER_HTTP_ERROR"
    return ExecutionMessage(
        code=code,
        message=f"provider returned HTTP {status}",
        retryable=retryable,
        metadata={"http_status": status},
    )


def _classify_exception(exc: Exception) -> ExecutionMessage:
    if isinstance(exc, httpx.HTTPStatusError):
        return _classify_http_error(exc)
    if isinstance(exc, httpx.TransportError):
        return ExecutionMessage(code="PROVIDER_NETWORK_ERROR", message=redact_secrets(str(exc)), retryable=True)
    # Builtins leaked from non-httpx code paths (raw sockets, adapters):
    if isinstance(exc, TimeoutError):
        return ExecutionMessage(code="PROVIDER_NETWORK_ERROR", message=redact_secrets(str(exc)), retryable=True)
    if isinstance(exc, ConnectionError):
        return ExecutionMessage(code="PROVIDER_NETWORK_ERROR", message=redact_secrets(str(exc)), retryable=True)
    return ExecutionMessage(
        code="PROVIDER_EXECUTION_ERROR", message=redact_secrets(f"{type(exc).__name__}: {exc}"), retryable=None
    )


async def _run_one_provider(provider: BaseProvider, request: SearchRequest) -> tuple[ProviderReport, list[Paper]]:
    """Executes one provider via the native fetch contract, classifying failures."""
    start = time.time()
    try:
        result = await provider.fetch(request)
    except Exception as exc:  # noqa: BLE001 - classified into a structured provider error
        report = ProviderReport(
            provider=provider.name,
            status="error",
            elapsed_seconds=round(time.time() - start, 2),
            errors=[_classify_exception(exc)],
        )
        return report, []

    returned = result.returned_count
    if returned > 0:
        status = "success"
    elif any(w.code == "PROVIDER_BLOCKED_INTERACTION_REQUIRED" for w in result.warnings):
        status = "blocked"
    else:
        status = "empty"

    filter_modes, filter_warnings = _resolve_filter_modes(provider.name, request)
    report = ProviderReport(
        provider=provider.name,
        status=status,  # type: ignore[arg-type]
        elapsed_seconds=result.elapsed_seconds or round(time.time() - start, 2),
        counts=ProviderCounts(
            matched=result.matched_count,
            fetched=result.fetched_count,
            after_filter=returned,
            returned=returned,
        ),
        pages_or_requests=result.pages_or_requests,
        filter_modes=filter_modes,
        warnings=list(result.warnings) + filter_warnings,
    )
    return report, list(result.papers)


def _resolve_filter_modes(provider_name: str, request: SearchRequest):
    """Reports how each requested filter was enforced by this provider.

    Modes come from the canonical capability registry (single source of truth).
    Filters the provider does not support at all produce FILTER_UNSUPPORTED
    warnings so silent filter dropping is impossible.
    """
    try:
        caps = get_capabilities(provider_name)
    except KeyError:
        return None, []

    modes: dict[str, str] = {}
    warnings: list[ExecutionMessage] = []
    requested: dict[str, object] = {
        "author": request.filters.author,
        "journal": request.filters.journal,
        "issn": request.filters.issn,
        "year_from": request.filters.year_from,
        "year_to": request.filters.year_to,
        "min_citations": request.filters.min_citations,
    }
    for filter_name, value in requested.items():
        if value is None:
            continue
        mode = caps.filter_modes.get(filter_name, "unsupported")
        modes[filter_name] = mode
        if mode == "unsupported":
            warnings.append(
                ExecutionMessage(
                    code="FILTER_UNSUPPORTED",
                    message=f"filter '{filter_name}' is not supported by provider '{provider_name}' and was not applied",
                    provider=provider_name,
                    retryable=None,
                    metadata={"filter": filter_name},
                )
            )
    return (modes or None), warnings


async def _execute_providers(
    providers: list[BaseProvider], request: SearchRequest
) -> tuple[list[ProviderReport], list[Paper], dict[str, list[Paper]]]:
    """Runs providers; concurrent gather when more than one is requested.

    Returns (reports, papers, papers_by_provider). Provider completion order
    never affects aggregate ordering: papers are merged deterministically later
    and reports are returned in requested-provider order.
    """
    if len(providers) == 1:
        report, papers = await _run_one_provider(providers[0], request)
        return [report], papers, {report.provider: papers}

    outcomes = await asyncio.gather(*[_run_one_provider(p, request) for p in providers])
    reports = [outcome[0] for outcome in outcomes]
    papers = [p for outcome in outcomes for p in outcome[1]]
    papers_by_provider: dict[str, list[Paper]] = {}
    for report, provider_papers in ((o[0], o[1]) for o in outcomes):
        papers_by_provider.setdefault(report.provider, []).extend(provider_papers)
    return reports, papers, papers_by_provider


def _observation_from_paper(provider: str, paper: Paper) -> SourceObservation:
    """Synthesizes a source observation from a provider-returned Paper.

    Until providers migrate to the fetch contract (Packets 8-12), observations
    are derived from the normalized records providers already return.
    """
    return SourceObservation(
        provider=provider,
        paper_id=paper.paper_id,
        title=paper.title,
        authors=[a.name for a in paper.authors if a.name],
        year=paper.year,
        journal=paper.journal,
        citations=paper.citations if paper.citations else None,
        doi=paper.doi,
        url=paper.url,
        abstract=paper.abstract,
    )


def _build_provenance(
    reports: list[ProviderReport],
    papers_by_provider: dict[str, list[Paper]],
    merged: list[Paper],
) -> list[ProvenanceEntry]:
    """Retains per-provider observations and traces merged citation values.

    Every aggregate citation value must trace to one or more observations:
    each entry records the observations that merged into the normalized record
    and the provider whose count won under the max_observed policy.
    """
    provenance: list[ProvenanceEntry] = []
    for record in merged:
        token = identity_token(record)
        observations: list[SourceObservation] = []
        for report in reports:
            provider_papers = papers_by_provider.get(report.provider, [])
            for paper in provider_papers:
                if identity_token(paper) == token:
                    observations.append(_observation_from_paper(report.provider, paper))
        if not observations:
            # Record came through without a matching provider report (e.g.
            # profile paths); still record the observation from the record itself.
            observations.append(_observation_from_paper(record.source_provider or "unknown", record))

        winning_source: str | None = None
        if observations:
            best = max(observations, key=lambda o: o.citations if o.citations is not None else -1)
            winning_source = best.provider if best.citations is not None else None

        provenance.append(
            ProvenanceEntry(
                canonical_id=token,
                citation_selection_policy="max_observed",
                observations=observations,
                preferred_citation_source=winning_source,
            )
        )
    return provenance


def _deterministic_sort(papers: list[Paper]) -> list[Paper]:
    """Deterministic aggregate ordering, independent of provider completion order.

    Initial policy: citations descending, with normalized-title then paper-id
    tie-breakers so equal-citation records keep a stable relative order.
    (Formal sort-policy selection continues in the pagination/ordering packet.)
    """
    return sorted(
        papers,
        key=lambda p: (-p.citations, (p.title or "").lower(), p.paper_id or ""),
    )


def _merge_and_deduplicate(papers: list[Paper]) -> tuple[list[Paper], int]:
    """Deduplicates records and applies deterministic ordering.

    Returns (merged papers, raw returned count)."""
    merged = deduplicate_papers(papers)
    return _deterministic_sort(merged), len(papers)


def _aggregate_status(reports: list[ProviderReport], merged_count: int) -> str:
    """Deterministic status from provider outcomes plus merged paper count.

    Plan status rules (implementation_plan.md Phase 2):
    - error: no provider completed successfully enough to establish a valid result;
    - partial: at least one provider contributed a valid execution while at
      least one failed/blocked/skipped (even when zero papers survived);
    - empty: ALL providers completed validly and no papers survived;
    - success: otherwise.
    """
    statuses = [r.status for r in reports]
    if all(s == "error" for s in statuses):
        return "error"
    if any(s in ("error", "blocked", "skipped") for s in statuses):
        return "partial"
    if merged_count == 0:
        return "empty"
    return "success"


def _metrics_context(
    request: SearchRequest,
    merged: list[Paper],
    reports: list[ProviderReport],
    status: str,
    now: datetime | None = None,
) -> MetricsContext:
    """Builds the interpretation context for the metrics block.

    Records the effective calculation year and timestamp so age-derived
    metrics (hI_annual, awcr, aw_index) are reproducible later. The numeric
    formulas themselves remain unchanged (implementation_plan.md Phase 11).
    """
    now = now or datetime.now(timezone.utc)
    contributing = sorted({r.provider for r in reports if r.status in ("success", "empty") and r.counts.returned > 0})
    completeness: str = "complete" if status == "success" else ("partial" if status == "partial" else "bounded")
    return MetricsContext(
        paper_count=len(merged),
        bounded_by_limit=len(merged) >= request.limit,
        providers_contributing=contributing,
        citation_selection_policy="max_observed",
        completeness=completeness,  # type: ignore[arg-type]
        calculation_year=now.year,
        calculation_timestamp=now.isoformat(),
    )


def _warnings_from_reports(reports: list[ProviderReport]) -> list[ExecutionMessage]:
    warnings: list[ExecutionMessage] = []
    for report in reports:
        for warning in report.warnings:
            warnings.append(warning)
    return warnings


def execute_request(request: SearchRequest) -> ExecutionEnvelope:
    """Executes a resolved SearchRequest and returns a complete ExecutionEnvelope.

    Synchronous facade over the async provider execution. Constructing the
    envelope here keeps renderers and persistence from reconstructing execution
    state independently.
    """
    started = time.time()
    try:
        providers = resolve_providers(request)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    reports, raw_papers, papers_by_provider = asyncio.run(_execute_providers(providers, request))

    merged, returned_raw = _merge_and_deduplicate(raw_papers)
    now = datetime.now(timezone.utc)
    metrics = calculate_metrics(merged)  # default UTC year; formula stability per plan
    status = _aggregate_status(reports, len(merged))
    provenance = _build_provenance(reports, papers_by_provider, merged)

    envelope = ExecutionEnvelope(
        app_version=__version__,
        status=status,  # type: ignore[arg-type]
        request=request,
        provider_reports=reports,
        counts=AggregateCounts(returned_raw=returned_raw, merged=len(merged)),
        papers=merged,
        provenance=provenance,
        metrics=metrics,
        metrics_context=_metrics_context(request, merged, reports, status, now),
        persistence=PersistenceReport(history_policy=request.persistence_policy),
        warnings=_warnings_from_reports(reports),
        errors=[msg for r in reports for msg in r.errors],
        elapsed_seconds=round(time.time() - started, 2),
    )
    return envelope
