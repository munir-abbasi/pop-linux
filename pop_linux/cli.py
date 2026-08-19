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
from pop_linux.models import Metrics, Paper, QueryResult
from pop_linux.providers import (
    get_provider,
)
from pop_linux.providers.base import BaseProvider
from pop_linux.providers.google_scholar import GoogleScholarProvider
from pop_linux.utils.deduplicator import deduplicate_papers
from pop_linux.utils.exporter import export_data
from pop_linux.utils.history import compute_snapshot_diff, list_snapshots, save_snapshot
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
    )
):
    pass


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
    profile: str | None = typer.Option(None, "--profile", help="Harvest directly from a Google Scholar user profile ID.")
):
    """Harvest papers across academic providers and compute bibliometrics."""
    cfg = load_config()
    selected_provider = (provider or cfg.get("default_provider", "openalex")).lower()
    selected_limit = limit or cfg.get("default_limit", 50)
    if isinstance(selected_limit, bool) or not isinstance(selected_limit, int) or selected_limit < 1:
        selected_limit = 50

    if not query.strip() and not profile:
        console.print("[bold red]Error:[/bold red] A search query is required unless --profile is provided.")
        raise typer.Exit(code=1)

    if year_from is not None and year_to is not None and year_from > year_to:
        console.print("[bold red]Error:[/bold red] --year-from must be less than or equal to --year-to.")
        raise typer.Exit(code=1)

    if profile:
        console.print(f"[dim]Harvesting Google Scholar profile: [bold cyan]{safe_text(profile)}[/bold cyan]...[/dim]")
        try:
            g_provider = GoogleScholarProvider()
            result = asyncio.run(
                g_provider.search_profile(
                    user_id=profile,
                    limit=selected_limit,
                    year_from=year_from,
                    year_to=year_to,
                    min_citations=min_citations
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
                            author=author,
                            journal=journal,
                            issn=issn,
                            year_from=year_from,
                            year_to=year_to,
                            min_citations=min_citations
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
                            author=author,
                            journal=journal,
                            issn=issn,
                            year_from=year_from,
                            year_to=year_to,
                            min_citations=min_citations
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

    # Auto-save snapshot to SQLite history
    snapshot_id = save_snapshot(result)
    console.print(f"[dim]Saved search snapshot #[bold cyan]{snapshot_id}[/bold cyan] to history.[/dim]")

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
    table = Table(title="Supported Academic Search Providers", show_header=True, header_style="bold green")
    table.add_column("Provider Key", style="bold cyan")
    table.add_column("Type", style="yellow")
    table.add_column("Description", style="white")

    table.add_row("openalex", "REST API (Default)", "Fast, structured, 250M+ scholarly works metadata (No API key needed)")
    table.add_row("semanticscholar", "REST API", "Semantic Scholar Graph API with citations & abstracts")
    table.add_row("crossref", "REST API", "Publisher metadata, DOI lookups, and citation counts")
    table.add_row("pubmed", "REST API", "NCBI Entrez biomedical and life sciences literature")
    table.add_row("google_scholar", "HTML + Playwright", "Scrapes Google Scholar with native Chromium CAPTCHA solver")

    console.print(table)


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


if __name__ == "__main__":
    app()
