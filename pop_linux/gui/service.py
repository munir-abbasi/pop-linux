"""Qt-independent adapters; business operations stay in existing modules."""
from pathlib import Path

from pop_linux.execution_models import ExecutionEnvelope, SearchFilters, SearchRequest
from pop_linux.models import Paper, QueryResult
from pop_linux.providers.capabilities import CAPABILITIES
from pop_linux.utils.exporter import export_data
from pop_linux.utils.metrics import calculate_metrics


def make_request(query: str, provider: str, limit: int, filters: dict, profile_id: str = "") -> SearchRequest:
    query = query.strip()
    profile_id = profile_id.strip()
    if not query and not profile_id:
        raise ValueError("Enter a research query or a Google Scholar profile ID.")
    providers = [key for key, capability in CAPABILITIES.items() if capability.included_in_all] if provider == "all" else [provider]
    if any(key not in CAPABILITIES for key in providers):
        raise ValueError("Choose an available search provider.")
    if profile_id and not (len(providers) == 1 and CAPABILITIES[providers[0]].profile_search):
        raise ValueError("Profile search requires a provider with profile support.")
    return SearchRequest(
        query=query, providers=providers, limit=limit, filters=SearchFilters(**filters),
        profile_id=profile_id or None, interaction_policy="allow", persistence_policy="explicit",
    )


def result_from_envelope(envelope: ExecutionEnvelope) -> QueryResult:
    return QueryResult(
        query=envelope.request.query, provider=",".join(envelope.request.providers),
        total_found=len(envelope.papers), papers=envelope.papers, metrics=envelope.metrics,
        search_time_seconds=envelope.elapsed_seconds,
    )


def export_result(result: QueryResult, path: Path, papers: list[Paper]) -> None:
    """Export an explicit scope in the unchanged legacy export schema."""
    selected = result.model_copy(update={
        "papers": papers, "total_found": len(papers),
        "metrics": result.metrics if papers == result.papers and result.metrics is not None else calculate_metrics(papers),
    })
    export_data(selected, path.suffix.lower().lstrip("."), str(path))


def safe_external_url(paper: Paper) -> str | None:
    """Open only explicit web URLs, never file or custom application schemes."""
    from urllib.parse import quote, urlsplit

    if paper.doi:
        from pop_linux.utils.identity import normalize_doi
        doi = normalize_doi(paper.doi)
        if doi:
            return "https://doi.org/" + quote(doi, safe="/")
    if paper.url:
        try:
            parsed = urlsplit(paper.url)
        except ValueError:
            return None
        if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username:
            return paper.url
    return None
