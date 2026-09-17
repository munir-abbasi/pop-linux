import asyncio
import json
import re
import time
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from pop_linux import __version__
from pop_linux.config import CONFIG_FILE, load_config, update_config_value
from pop_linux.execution import execute_request, redact_secrets as _redact_secrets
from pop_linux.execution_models import (
    EXECUTION_SCHEMA,
    ExecutionEnvelope,
    ExecutionMessage,
    PersistenceReport,
    SearchFilters,
    SearchRequest,
)
from pop_linux.models import Metrics, Paper, QueryResult
from pop_linux.providers import (
    get_provider,
)
from pop_linux.providers.capabilities import build_capabilities_document
from pop_linux.providers.base import BaseProvider
from pop_linux.providers.google_scholar import GoogleScholarProvider
from pop_linux.utils.deduplicator import deduplicate_papers
from pop_linux.utils.exporter import export_data
from pop_linux.utils.history import (
    compute_snapshot_diff,
    get_execution,
    list_snapshots,
    save_snapshot,
)
from pop_linux.utils.metrics import calculate_metrics

app = typer.Typer(
    name="pop-linux",
    help="Native Perish or Publish Linux — Academic paper harvesting and bibliometrics.",
    add_completion=False
)
console = Console()

#: Terminal control sequences (ANSI/OSC, e.g. SGR styling, cursor moves, OSC-8 hyperlinks)
_CONTROL_SEQ_RE = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC (hyperlink / title) sequences
    r"|\x1b\[[0-?]*[ -/]*[@-~]"          # CSI sequences (SGR, erase, cursor)
    r"|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"  # stray C0/C1 control characters
)


def safe_text(value: object | None) -> str:
    """Neutralizes Rich markup and terminal control sequences in untrusted strings."""
    if value is None:
        return ""
    text = str(value)
    text = _CONTROL_SEQ_RE.sub("", text)
    return escape(text)


def _mask_secret(value: str) -> str:
    """Masks a secret (e.g. API key) for display: 'abc…xyz'."""
    if not value:
        return ""
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}...{value[-3:]}"


def version_callback(value: bool):
    if value:
        console.print(f"[bold cyan]pop-linux[/bold cyan] version [green]{__version__}[/green]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None, "--version", "-v", help="Show pop-linux version and exit.", callback=version_callback, is_eager=True
    ),
    machine: bool = typer.Option(
        False, "--machine", help="Machine execution profile: one versioned JSON envelope on stdout, "
        "non-interactive, no implicit history persistence."
    ),
):
    """Global execution-profile options."""
    main.machine_mode = machine


main.machine_mode = False


def _machine_requested() -> bool:
    return bool(getattr(main, "machine_mode", False))


def render_metrics_panel(metrics: Metrics):
    """Renders Harzing bibliometrics summary in a Rich Panel."""
    table = Table(show_header=True, header_style="bold magenta", box=None)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold green", justify="right")

    table.add_row("Total Papers", str(metrics.total_papers))
    table.add_row("Total Citations", str(metrics.total_citations))
    table.add_row("Avg Citations / Paper", str(metrics.avg_citations_per_paper))
    table.add_row("Citations / Author", str(metrics.citations_per_author))
    table.add_row("h-index", str(metrics.h_index))
    table.add_row("g-index", str(metrics.g_index))
    table.add_row("e-index", str(metrics.e_index))
    table.add_row("hI,annual", str(metrics.hI_annual))
    table.add_row("hL,norm", str(metrics.hL_norm))
    table.add_row("AWCR", str(metrics.awcr))
    table.add_row("AW-index", str(metrics.aw_index))
    table.add_row("i10-index", str(metrics.i10_index))

    panel = Panel(table, title="[bold yellow]Harzing Bibliometric Summary[/bold yellow]", border_style="bright_blue")
    console.print(panel)


def render_papers_table(result: QueryResult):
    """Renders paper search results in a Rich Table."""
    table = Table(title=f"Search Results: '{safe_text(result.query)}' ({result.provider}) — {len(result.papers)} papers found in {result.search_time_seconds}s", show_header=True, header_style="bold blue")
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="bold white", max_width=45, overflow="fold")
    table.add_column("Authors", style="cyan", max_width=25, overflow="ellipsis")
    table.add_column("Year", style="yellow", width=6)
    table.add_column("Journal/Venue", style="magenta", max_width=25, overflow="ellipsis")
    table.add_column("Cites", style="bold green", justify="right", width=7)

    for idx, paper in enumerate(result.papers, start=1):
        table.add_row(
            str(idx),
            safe_text(paper.title),
            safe_text(paper.author_string),
            str(paper.year) if paper.year else "-",
            safe_text(paper.journal or "-"),
            str(paper.citations)
        )

    console.print(table)


def _resolve_search_options(
    provider: str | None,
    limit: int | None,
    author: str | None,
    journal: str | None,
    issn: str | None,
    year_from: int | None,
    year_to: int | None,
    min_citations: int | None,
    non_interactive: bool,
    save_history: bool | None,
    no_history: bool,
) -> tuple[str, int, SearchFilters, str, str]:
    """Applies config defaults and machine-profile policies to raw CLI options.

    Returns (provider_key, limit, filters, interaction_policy, persistence_policy).
    Raises typer.Exit on invalid input.
    """
    cfg = load_config()
    selected_provider = (provider or cfg.get("default_provider", "openalex")).lower()
    selected_limit = limit or cfg.get("default_limit", 50)
    if isinstance(selected_limit, bool) or not isinstance(selected_limit, int) or selected_limit < 1:
        selected_limit = 50

    if year_from is not None and year_to is not None and year_from > year_to:
        if _machine_requested():
            _emit_machine_error("INVALID_REQUEST", "--year-from must be less than or equal to --year-to")
        console.print("[bold red]Error:[/bold red] --year-from must be less than or equal to --year-to.")
        raise typer.Exit(code=1)

    filters = SearchFilters(
        author=author,
        journal=journal,
        issn=issn,
        year_from=year_from,
        year_to=year_to,
        min_citations=min_citations,
    )

    interaction_policy = "never" if (machine_requested := _machine_requested() or non_interactive) else "allow"

    # Persistence policy: machine defaults off; explicit flags override in both profiles.
    if save_history:
        persistence_policy = "explicit"
    elif no_history:
        persistence_policy = "off"
    else:
        persistence_policy = "off" if machine_requested else "auto"

    return selected_provider, selected_limit, filters, interaction_policy, persistence_policy


def _emit_machine_envelope(envelope: ExecutionEnvelope) -> None:
    """Writes exactly one versioned JSON envelope to stdout."""
    console.file = None  # ensure no Rich state bleeds into the machine channel
    payload = envelope.model_dump_json(indent=2)
    typer.echo(payload)


def _emit_machine_error(code: str, message: str) -> None:
    """Emits a minimal fatal-error envelope on stdout and exits nonzero.

    Used only for failures that prevent a full execution envelope from being
    constructed (e.g. request validation before execution starts).
    """
    fatal = {
        "schema": EXECUTION_SCHEMA,
        "app_version": __version__,
        "status": "error",
        "request": None,
        "errors": [{"code": code, "message": _redact_secrets(message), "provider": None, "retryable": None, "metadata": None}],
    }
    typer.echo(json.dumps(fatal, indent=2))
    raise typer.Exit(code=1)


def _machine_persistence_report(envelope: ExecutionEnvelope, export: str | None, save_history: bool | None) -> ExecutionEnvelope:
    """Applies explicitly requested side effects in machine mode, reporting outcomes."""
    persistence = PersistenceReport(history_policy=envelope.request.persistence_policy)

    if save_history and envelope.status in ("success", "partial"):
        try:
            snapshot_id = save_snapshot(envelope_to_query_result(envelope))
            persistence.snapshot_written = True
            persistence.snapshot_id = snapshot_id
        except Exception as exc:  # noqa: BLE001 - side-effect failure must not mask retrieval result
            persistence.errors.append(
                ExecutionMessage(code="HISTORY_WRITE_FAILED", message=_redact_secrets(str(exc)))
            )

    if export and envelope.status in ("success", "partial", "empty"):
        ext = Path(export).suffix.strip(".")
        fmt = ext if ext in ["json", "csv", "bib", "ris"] else "json"
        try:
            export_data(envelope_to_query_result(envelope), fmt, output_path=export)
            persistence.exported.append({"format": fmt, "path": str(export)})
        except Exception as exc:  # noqa: BLE001 - side-effect failure must not mask retrieval result
            persistence.errors.append(
                ExecutionMessage(code="EXPORT_FAILED", message=_redact_secrets(str(exc)))
            )

    envelope.persistence = persistence
    return envelope


def envelope_to_query_result(envelope: ExecutionEnvelope) -> QueryResult:
    """Projects an ExecutionEnvelope onto the legacy QueryResult shape.

    Used for history snapshots and exports so both profiles share one data path.
    The projection carries query/provider/papers/metrics/timing but not the
    provider reports (those are envelope-level concepts).
    """
    provider_label = "all (deduplicated)" if len(envelope.request.providers) > 1 else envelope.request.providers[0]
    if envelope.request.profile_id:
        provider_label = "google_scholar_profile"
    return QueryResult(
        query=envelope.request.query,
        provider=provider_label,
        total_found=envelope.counts.merged,
        papers=envelope.papers,
        metrics=envelope.metrics,
        search_time_seconds=envelope.elapsed_seconds,
    )


def _run_machine_search(
    request: SearchRequest,
    export: str | None,
    save_history: bool | None,
) -> None:
    """Executes one machine-profile search and emits the envelope."""
    try:
        envelope = execute_request(request)
    except ValueError as exc:
        _emit_machine_error("INVALID_REQUEST", str(exc))
        return  # unreachable; keeps type checkers happy

    envelope = _machine_persistence_report(envelope, export, save_history)

    _emit_machine_envelope(envelope)
    if envelope.status == "error":
        raise typer.Exit(code=1)
    # success/partial/empty exit 0


async def search_all_providers(query: str, limit: int, **kwargs) -> QueryResult:
    """Executes search across OpenAlex, Semantic Scholar, CrossRef, and PubMed concurrently and merges deduplicated results."""
    start_time = time.time()
    providers: list[BaseProvider] = [
        get_provider("openalex"),
        get_provider("semanticscholar"),
        get_provider("crossref"),
        get_provider("pubmed")
    ]
    tasks = [
        p.search(
            query=query,
            limit=limit,
            author=kwargs.get("author"),
            journal=kwargs.get("journal"),
            issn=kwargs.get("issn"),
            year_from=kwargs.get("year_from"),
            year_to=kwargs.get("year_to"),
            min_citations=kwargs.get("min_citations")
        )
        for p in providers
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_papers: list[Paper] = []
    total_found = 0
    for prov, res in zip(providers, results, strict=False):
        if isinstance(res, Exception):
            console.print(
                f"[yellow]WARNING: provider '{prov.name}' failed and was skipped: "
                f"{type(res).__name__}: {safe_text(res)}[/yellow]"
            )
        elif isinstance(res, QueryResult):
            all_papers.extend(res.papers)
            total_found += res.total_found

    unique_papers = deduplicate_papers(all_papers)
    # total_found reflects the number of unique records actually returned,
    # since per-provider raw counts overlap and cannot be meaningfully summed.
    total_found = len(unique_papers)
    metrics = calculate_metrics(unique_papers)
    elapsed = round(time.time() - start_time, 2)
    return QueryResult(
        query=query,
        provider="all (deduplicated)",
        total_found=total_found,
        papers=unique_papers,
        metrics=metrics,
        search_time_seconds=elapsed
    )


@app.command("search")
def search_cmd(
    query: str = typer.Argument("", help="Academic search query or topic."),
    provider: str | None = typer.Option(None, "--provider", "-p", help="Search provider (openalex, semanticscholar, crossref, pubmed, google_scholar, all)."),
    limit: int | None = typer.Option(None, "--limit", "-l", help="Maximum number of papers to harvest."),
    export: str | None = typer.Option(None, "--export", "-e", help="Output filepath to export results (.bib, .csv, .json, .ris)."),
    author: str | None = typer.Option(None, "--author", "-a", help="Filter by target author name."),
    journal: str | None = typer.Option(None, "--journal", "-j", help="Filter by publication venue or journal name."),
    issn: str | None = typer.Option(None, "--issn", help="Filter by journal ISSN."),
    year_from: int | None = typer.Option(None, "--year-from", help="Publication year starting range."),
    year_to: int | None = typer.Option(None, "--year-to", help="Publication year ending range."),
    min_citations: int | None = typer.Option(None, "--min-citations", help="Minimum citation threshold before metric computation."),
    show_h_core: bool = typer.Option(False, "--show-h-core", help="Display only the h-core subset of papers."),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Human-profile headless execution: no interactive browser handling."),
    save_history: bool | None = typer.Option(None, "--save-history", help="Force a history snapshot for this search (overrides profile default)."),
    no_history: bool = typer.Option(False, "--no-history", help="Suppress the history snapshot for this search (overrides profile default)."),
    profile: str | None = typer.Option(None, "--profile", help="Harvest directly from a Google Scholar user profile ID.")
):
    """Harvest papers across academic providers and compute bibliometrics."""
    selected_provider, selected_limit, filters, interaction_policy, persistence_policy = _resolve_search_options(
        provider, limit, author, journal, issn, year_from, year_to, min_citations,
        non_interactive, save_history, no_history,
    )

    if not query.strip() and not profile:
        if _machine_requested():
            _emit_machine_error("INVALID_REQUEST", "A search query is required unless --profile is provided.")
        console.print("[bold red]Error:[/bold red] A search query is required unless --profile is provided.")
        raise typer.Exit(code=1)

    request = SearchRequest(
        query=query,
        profile_id=profile,
        providers=[selected_provider],
        limit=selected_limit,
        filters=filters,
        interaction_policy=interaction_policy,  # type: ignore[arg-type]
        persistence_policy=persistence_policy,  # type: ignore[arg-type]
    )

    if _machine_requested():
        if profile:
            # Machine profile is strictly non-interactive; profile harvesting
            # requires the Scholar HTML path and may open Chromium.
            _emit_machine_error(
                "INTERACTION_FORBIDDEN",
                "profile harvesting requires interactive Google Scholar access; "
                "machine mode forbids browser interaction",
            )
        if "google_scholar" in request.providers:
            _emit_machine_error(
                "INTERACTION_FORBIDDEN",
                "google_scholar may require interactive browser handling; "
                "machine mode forbids browser interaction",
            )
        _run_machine_search(request, export, save_history)
        return

    # ------------------------- human profile -------------------------
    if profile:
        console.print(f"[dim]Harvesting Google Scholar profile: [bold cyan]{safe_text(profile)}[/bold cyan]...[/dim]")
        try:
            g_provider = GoogleScholarProvider()
            result = asyncio.run(
                g_provider.search_profile(
                    user_id=profile,
                    limit=selected_limit,
                    year_from=filters.year_from,
                    year_to=filters.year_to,
                    min_citations=filters.min_citations
                )
            )
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]Provider API returned HTTP {e.response.status_code}:[/bold red] {safe_text(e.response.text[:200])}")
            raise typer.Exit(code=1)
        except httpx.RequestError as e:
            console.print(f"[bold red]Network/Connection error:[/bold red] {safe_text(e)}")
            raise typer.Exit(code=1)
        except Exception as e:
            console.print(f"[bold red]Search failed:[/bold red] {safe_text(e)}")
            raise typer.Exit(code=1)
    else:
        console.print(f"[dim]Initiating academic harvest with [bold cyan]{safe_text(selected_provider)}[/bold cyan]...[/dim]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(description=f"Searching '{safe_text(query)}' via {safe_text(selected_provider)}...", total=None)
            try:
                if selected_provider == "all":
                    result = asyncio.run(
                        search_all_providers(
                            query=query,
                            limit=selected_limit,
                            author=filters.author,
                            journal=filters.journal,
                            issn=filters.issn,
                            year_from=filters.year_from,
                            year_to=filters.year_to,
                            min_citations=filters.min_citations
                        )
                    )
                else:
                    prov_instance: BaseProvider
                    if selected_provider == "google_scholar":
                        prov_instance = GoogleScholarProvider()
                    else:
                        prov_instance = get_provider(selected_provider)

                    result = asyncio.run(
                        prov_instance.search(
                            query=query,
                            limit=selected_limit,
                            author=filters.author,
                            journal=filters.journal,
                            issn=filters.issn,
                            year_from=filters.year_from,
                            year_to=filters.year_to,
                            min_citations=filters.min_citations
                        )
                    )
            except httpx.HTTPStatusError as e:
                console.print(f"[bold red]Provider API returned HTTP {e.response.status_code}:[/bold red] {safe_text(e.response.text[:200])}")
                raise typer.Exit(code=1)
            except httpx.RequestError as e:
                console.print(f"[bold red]Network/Connection error:[/bold red] {safe_text(e)}")
                raise typer.Exit(code=1)
            except Exception as e:
                console.print(f"[bold red]Search failed:[/bold red] {safe_text(e)}")
                raise typer.Exit(code=1)

    if not result.papers:
        console.print("[yellow]No papers found matching the query.[/yellow]")
        return

    # Auto-save snapshot to SQLite history (human default; explicit overrides honored)
    if persistence_policy != "off":
        try:
            snapshot_id = save_snapshot(result)
        except Exception as exc:  # noqa: BLE001 - side-effect failure must not mask retrieval result
            console.print(f"[yellow]Warning:[/yellow] could not save search history: {_mask_secret(str(exc))}")
            console.print("[dim]Search results were retrieved successfully; only the history write failed.[/dim]")
        else:
            console.print(f"[dim]Saved search snapshot #[bold cyan]{snapshot_id}[/bold cyan] to history.[/dim]")
    elif no_history:
        console.print("[dim]History write suppressed (--no-history).[/dim]")

    if show_h_core and result.metrics and result.metrics.h_index > 0:
        sorted_h_papers = sorted(result.papers, key=lambda p: p.citations, reverse=True)[:result.metrics.h_index]
        result = QueryResult(
            query=f"{result.query} (h-core)",
            provider=result.provider,
            total_found=result.total_found,
            papers=sorted_h_papers,
            metrics=result.metrics,
            search_time_seconds=result.search_time_seconds
        )

    render_papers_table(result)
    if result.metrics:
        render_metrics_panel(result.metrics)

    if export:
        ext = Path(export).suffix.strip(".")
        fmt = ext if ext in ["json", "csv", "bib", "ris"] else "json"
        try:
            export_data(result, fmt, output_path=export)
            console.print(f"[bold green]Results successfully exported to:[/bold green] {safe_text(export)}")
        except Exception as e:
            console.print(f"[bold red]Export failed:[/bold red] {e}")
            raise typer.Exit(code=1)


@app.command("metrics")
def metrics_cmd(
    filepath: str = typer.Argument(..., help="Path to exported JSON QueryResult file.")
):
    """Calculates and displays Harzing bibliometrics for a saved JSON query result."""
    path = Path(filepath)
    if not path.exists():
        console.print(f"[bold red]Error:[/bold red] File '{safe_text(filepath)}' does not exist.")
        raise typer.Exit(code=1)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        result = QueryResult.model_validate(data)
        metrics = calculate_metrics(result.papers)
        render_metrics_panel(metrics)
    except Exception as e:
        console.print(f"[bold red]Failed to parse query result:[/bold red] {safe_text(e)}")
        raise typer.Exit(code=1)


@app.command("config")
def config_cmd(
    show: bool = typer.Option(False, "--show", "-s", help="Display active configuration settings."),
    set_key: str | None = typer.Option(None, "--set", help="Set configuration key (e.g. default_provider)."),
    value: str | None = typer.Option(None, "--value", help="New value for configuration key.")
):
    """View or update pop-linux configuration settings."""
    if set_key and value is not None:
        update_config_value(set_key, value)
        display_value = _mask_secret(value) if re.search(r"key|token|secret", set_key, re.IGNORECASE) else value
        console.print(f"[bold green]Updated {set_key} = {display_value}[/bold green]")
        return

    cfg = load_config()
    console.print(f"[bold cyan]Configuration File:[/bold cyan] {safe_text(CONFIG_FILE)}")
    for k, v in cfg.items():
        if isinstance(v, dict):
            v = {kk: _mask_secret(vv) if isinstance(vv, str) else vv for kk, vv in v.items()}
        console.print(f"  [bold yellow]{k}:[/bold yellow] {safe_text(v)}")


@app.command("providers")
def providers_cmd():
    """Lists supported academic search providers."""
    if _machine_requested():
        _emit_machine_capabilities()
        return
    table = Table(title="Supported Academic Search Providers", show_header=True, header_style="bold green")
    table.add_column("Provider Key", style="bold cyan")
    table.add_column("Type", style="yellow")
    table.add_column("Description", style="white")

    from pop_linux.providers.capabilities import CAPABILITIES

    for key in CAPABILITIES:
        caps = CAPABILITIES[key]
        rtype = "REST API" if caps.retrieval_type == "rest" else "HTML + Playwright"
        default_note = " (Default)" if key == "openalex" else ""
        table.add_row(key, rtype + default_note, caps.description)

    console.print(table)


def _emit_machine_capabilities() -> None:
    """Emits the capabilities/readiness document as machine JSON on stdout."""
    doc = build_capabilities_document(load_config())
    typer.echo(doc.model_dump_json(indent=2))


@app.command("capabilities")
def capabilities_cmd():
    """Discover provider capabilities and local readiness (no network calls)."""
    if _machine_requested():
        _emit_machine_capabilities()
        return

    doc = build_capabilities_document(load_config())

    table = Table(title="Provider Capabilities", show_header=True, header_style="bold green")
    table.add_column("Provider", style="bold cyan")
    table.add_column("Type", style="yellow")
    table.add_column("In `all`", justify="center")
    table.add_column("Filters (mode)", max_width=40, overflow="fold")
    table.add_column("Cites", justify="center")
    table.add_column("Profile", justify="center")
    table.add_column("Readiness", max_width=30, overflow="fold")

    for key, caps in doc.providers.items():
        short = {"post_filter": "post", "query_hint": "hint", "native": "native", "unsupported": "unsupported"}
        modes = ", ".join(f"{f}:{short[m]}" for f, m in sorted(caps.filter_modes.items()))
        ready = doc.provider_readiness.get(key)
        ready_note = "; ".join(ready.notes) if ready and ready.notes else "ready"
        table.add_row(
            key,
            caps.retrieval_type,
            "yes" if caps.included_in_all else "no",
            modes,
            "yes" if caps.citation_counts_available else "no",
            "yes" if caps.profile_search else "no",
            safe_text(ready_note),
        )
    console.print(table)

    env = doc.environment
    console.print(
        f"[dim]Environment: playwright={'available' if env.playwright_importable else 'not installed'}; "
        f"chromium={'detected' if env.chromium_detected else ('not detected' if env.chromium_detected is False else 'unknown')}; "
        f"history dir writable={'yes' if doc.paths.history_dir_writable else 'NO'}[/dim]"
    )


@app.command("merge")
def merge_cmd(
    files: list[Path] = typer.Argument(..., help="Path to JSON result files to merge."),
    export: str | None = typer.Option(None, "--export", "-e", help="Output filepath to export merged results (.bib, .csv, .json, .ris).")
):
    """Merge multiple QueryResult JSON files into a single deduplicated dataset."""
    all_papers: list[Paper] = []
    for file_path in files:
        if not file_path.exists():
            console.print(f"[bold red]File not found:[/bold red] {safe_text(str(file_path))}")
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            res = QueryResult.model_validate(data)
            all_papers.extend(res.papers)
        except Exception as err:
            console.print(f"[bold yellow]Warning:[/bold yellow] Failed to load {safe_text(str(file_path))}: {safe_text(err)}")

    if not all_papers:
        console.print("[red]No valid paper records found to merge.[/red]")
        raise typer.Exit(code=1)

    merged_papers = deduplicate_papers(all_papers)
    metrics = calculate_metrics(merged_papers)
    merged_result = QueryResult(
        query="Merged Dataset",
        provider="merged",
        total_found=len(merged_papers),
        papers=merged_papers,
        metrics=metrics,
        search_time_seconds=0.0
    )

    render_papers_table(merged_result)
    render_metrics_panel(metrics)

    if export:
        ext = Path(export).suffix.strip(".")
        fmt = ext if ext in ["json", "csv", "bib", "ris"] else "json"
        try:
            export_data(merged_result, fmt, output_path=export)
            console.print(f"[bold green]Merged results successfully exported to:[/bold green] {safe_text(export)}")
        except Exception as err:
            console.print(f"[bold red]Export failed:[/bold red] {err}")
            raise typer.Exit(code=1)


@app.command("rerun")
def rerun_cmd(
    snapshot_id: int = typer.Argument(..., help="Snapshot ID to re-execute (must be a persisted v2 execution)."),
    export: str | None = typer.Option(None, "--export", "-e", help="Output filepath to export rerun results (.bib, .csv, .json, .ris)."),
):
    """Re-execute a persisted search by reconstructing its resolved request."""
    if _machine_requested():
        _run_machine_rerun(snapshot_id, export)
        return

    try:
        envelope, lineage_id = _execute_rerun(snapshot_id)
    except ValueError as err:
        console.print(f"[bold red]Error:[/bold red] {safe_text(str(err))}")
        raise typer.Exit(code=1)

    console.print(
        f"[dim]Re-executed snapshot #[bold cyan]{snapshot_id}[/bold cyan] "
        f"as #[bold cyan]{lineage_id}[/bold cyan] "
        f"(status: {envelope.status}, {envelope.counts.merged} papers).[/dim]"
    )

    # Reproducibility metadata: original vs current execution conditions
    original = get_execution(snapshot_id)
    if original:
        if original.app_version != envelope.app_version:
            console.print(f"[yellow]Note: original ran on app {original.app_version}; this run: {envelope.app_version}.[/yellow]")

    result = envelope_to_query_result(envelope)
    render_papers_table(result)
    if result.metrics:
        render_metrics_panel(result.metrics)

    if export:
        ext = Path(export).suffix.strip(".")
        fmt = ext if ext in ["json", "csv", "bib", "ris"] else "json"
        try:
            export_data(result, fmt, output_path=export)
            console.print(f"[bold green]Rerun results successfully exported to:[/bold green] {safe_text(export)}")
        except Exception as err:
            console.print(f"[bold red]Export failed:[/bold red] {safe_text(str(err))}")
            raise typer.Exit(code=1)


def _execute_rerun(snapshot_id: int) -> tuple[ExecutionEnvelope, int]:
    """Reconstructs the persisted request, re-executes it, records lineage.

    Rerun IS a persistence action: the new execution is saved with
    parent_snapshot_id pointing at the original, in both profiles.
    """
    original = get_execution(snapshot_id)
    if original is None:
        from pop_linux.utils.history import get_snapshot

        if get_snapshot(snapshot_id) is not None:
            raise ValueError(
                f"snapshot #{snapshot_id} predates execution persistence and cannot be reconstructed"
            )
        raise ValueError(f"snapshot #{snapshot_id} does not exist")

    # Re-execute the ORIGINAL resolved request under current credentials and
    # provider implementation. Capability changes since the original run
    # appear in the new provider reports, not hidden. Module-level reference
    # so the dependency is patchable in tests.
    import copy as _copy

    fresh_request = _copy.deepcopy(original.request)
    fresh_request.persistence_policy = "explicit"
    new_envelope = execute_request(fresh_request)

    from pop_linux.utils.history import save_execution

    lineage_id = save_execution(new_envelope, parent_snapshot_id=snapshot_id)
    return new_envelope, lineage_id


def _run_machine_rerun(snapshot_id: int, export: str | None) -> None:
    """Machine-profile rerun: one envelope on stdout, lineage persisted."""
    try:
        envelope, lineage_id = _execute_rerun(snapshot_id)
    except ValueError as err:
        _emit_machine_error("RERUN_UNAVAILABLE", str(err))
        return

    # Report lineage inside the envelope's persistence section
    persistence = envelope.persistence
    persistence.snapshot_written = True
    persistence.snapshot_id = lineage_id
    persistence.history_policy = "explicit"
    envelope.persistence = persistence

    if export and envelope.status in ("success", "partial", "empty"):
        ext = Path(export).suffix.strip(".")
        fmt = ext if ext in ["json", "csv", "bib", "ris"] else "json"
        try:
            export_data(envelope_to_query_result(envelope), fmt, output_path=export)
            envelope.persistence.exported.append({"format": fmt, "path": str(export)})
        except Exception as exc:  # noqa: BLE001 - side-effect failure must not mask result
            envelope.persistence.errors.append(
                ExecutionMessage(code="EXPORT_FAILED", message=_redact_secrets(str(exc)))
            )

    _emit_machine_envelope(envelope)
    if envelope.status == "error":
        raise typer.Exit(code=1)


@app.command("history")
def history_cmd(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of past search snapshots to list.")
):
    """List historical search snapshots stored in SQLite database."""
    snapshots = list_snapshots(limit=limit)
    if not snapshots:
        console.print("[yellow]No historical search snapshots found.[/yellow]")
        return

    table = Table(title="Search History Snapshots", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="bold green", width=5)
    table.add_column("Timestamp", style="dim", width=22)
    table.add_column("Query", style="bold white", max_width=35, overflow="fold")
    table.add_column("Provider", style="magenta", width=15)
    table.add_column("Papers", style="yellow", justify="right", width=7)
    table.add_column("h-index", style="cyan", justify="right", width=8)

    for s in snapshots:
        table.add_row(
            str(s["id"]),
            s["timestamp"][:19].replace("T", " "),
            safe_text(s["query"]),
            s["provider"],
            str(s["total_found"]),
            str(s["h_index"])
        )

    console.print(table)


@app.command("diff")
def diff_cmd(
    snap1: int = typer.Argument(..., help="Baseline snapshot ID."),
    snap2: int = typer.Argument(..., help="Target comparison snapshot ID.")
):
    """Compare citation growth and metric trajectory between two search snapshots."""
    if _machine_requested():
        try:
            diff_data = compute_snapshot_diff(snap1, snap2)
        except ValueError as err:
            _emit_machine_error("DIFF_UNAVAILABLE", str(err))
            return
        typer.echo(json.dumps(diff_data, indent=2))
        return

    try:
        diff_data = compute_snapshot_diff(snap1, snap2)
    except ValueError as err:
        console.print(f"[bold red]Error:[/bold red] {err}")
        raise typer.Exit(code=1)

    console.print(Panel(
        f"[bold yellow]Citation & Metric Trajectory Diff[/bold yellow]\n"
        f"Baseline Snapshot #[bold cyan]{snap1}[/bold cyan] ➔ Target Snapshot #[bold cyan]{snap2}[/bold cyan]\n"
        f"Query: [bold white]{safe_text(diff_data['query'])}[/bold white]",
        border_style="bright_blue"
    ))

    # Metric changes table
    m_diff = diff_data["metrics_diff"]
    table_m = Table(title="Metric Trajectory", show_header=True, header_style="bold green")
    table_m.add_column("Metric", style="cyan")
    table_m.add_column("Delta Change", style="bold yellow", justify="right")

    for k, v in m_diff.items():
        color = "green" if v > 0 else ("red" if v < 0 else "dim")
        table_m.add_row(k.replace("_", " ").title(), f"[{color}]{'+' if v > 0 else ''}{v}[/{color}]")

    console.print(table_m)

    # Citation deltas table
    deltas = diff_data["citation_deltas"]
    if deltas:
        table_c = Table(title="Paper Citation Deltas", show_header=True, header_style="bold blue")
        table_c.add_column("Paper Title", style="white", max_width=45, overflow="fold")
        table_c.add_column("Old Cites", style="dim", justify="right")
        table_c.add_column("New Cites", style="bold green", justify="right")
        table_c.add_column("Growth", style="bold yellow", justify="right")

        for d in deltas:
            table_c.add_row(
                safe_text(d["title"]),
                str(d["old_citations"]),
                str(d["new_citations"]),
                f"+{d['delta']}" if d["delta"] > 0 else str(d["delta"])
            )
        console.print(table_c)

    # New papers
    if diff_data["new_papers"]:
        console.print(f"\n[bold green]Newly Discovered Papers ({len(diff_data['new_papers'])}):[/bold green]")
        for np_title in diff_data["new_papers"]:
            console.print(f" • [white]{safe_text(np_title)}[/white]")

    # Ambiguous identity matches (shared identity service could not decide)
    if diff_data.get("ambiguous_matches"):
        console.print(f"\n[bold yellow]Ambiguous Identity Matches ({len(diff_data['ambiguous_matches'])}):[/bold yellow]")
        for amb in diff_data["ambiguous_matches"]:
            baselines = ", ".join(safe_text(t) for t in amb["matched_baselines"])
            console.print(f" • [white]{safe_text(amb['title'])}[/white] [dim](matched baselines: {baselines})[/dim]")


if __name__ == "__main__":
    app()
