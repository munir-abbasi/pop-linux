import csv
import io
import re
from pathlib import Path

from pop_linux.models import Paper, QueryResult

#: First characters that trigger formula interpretation in spreadsheet apps
_FORMULA_PREFIX_CHARS = ("=", "+", "-", "@")


def _safe_csv_cell(value: object) -> object:
    """Neutralizes CSV formula injection: cells beginning with = + - @ (after leading whitespace)
    are prefixed with ' to prevent spreadsheet formula execution."""
    if not isinstance(value, str) or not value:
        return value
    stripped = value.lstrip("\t\r\n \x00")
    if stripped and stripped[0] in _FORMULA_PREFIX_CHARS:
        return "'" + value
    return value


def export_to_json(result: QueryResult) -> str:
    """Exports QueryResult to indented JSON string."""
    return result.model_dump_json(indent=2)


def export_to_csv(result: QueryResult) -> str:
    """Exports papers in QueryResult to CSV string."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "Title", "Authors", "Year", "Journal", "Citations", "DOI", "URL", "SourceProvider", "Abstract"
    ])
    writer.writeheader()
    for p in result.papers:
        writer.writerow({
            "Title": _safe_csv_cell(p.title),
            "Authors": _safe_csv_cell(p.author_string),
            "Year": p.year or "",
            "Journal": _safe_csv_cell(p.journal or ""),
            "Citations": p.citations,
            "DOI": _safe_csv_cell(p.doi or ""),
            "URL": _safe_csv_cell(p.url or ""),
            "SourceProvider": p.source_provider,
            "Abstract": _safe_csv_cell(p.abstract or "")
        })
    return output.getvalue()


def _sanitize_bib_key(paper: Paper, index: int) -> str:
    """Generates a clean BibTeX key like AuthorYearTitle."""
    first_author = paper.authors[0].name.split()[-1] if paper.authors else "Anon"
    first_author = re.sub(r'\W+', '', first_author)
    year = str(paper.year) if paper.year else "0000"
    return f"{first_author}{year}_{index}"


def _escape_bibtex(text: str) -> str:
    """Escapes special LaTeX/BibTeX characters in field text (single-pass, char-by-char)."""
    if not text:
        return ""
    escapes = {
        "\\": r"\textbackslash{}",
        "%": r"\%",
        "#": r"\#",
        "&": r"\&",
        "_": r"\_",
        "$": r"\$",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(escapes.get(ch, ch) for ch in text)


def export_to_bibtex(result: QueryResult) -> str:
    """Exports papers in QueryResult to standard BibTeX string."""
    entries = []
    for idx, p in enumerate(result.papers, start=1):
        key = _sanitize_bib_key(p, idx)
        author_str = " and ".join(_escape_bibtex(a.name) for a in p.authors) if p.authors else "Unknown"
        lines = [f"@article{{{key},"]
        lines.append(f"  title = {{{_escape_bibtex(p.title)}}},")
        lines.append(f"  author = {{{author_str}}},")
        if p.year:
            lines.append(f"  year = {{{p.year}}},")
        if p.journal:
            lines.append(f"  journal = {{{_escape_bibtex(p.journal)}}},")
        if p.doi:
            lines.append(f"  doi = {{{_escape_bibtex(p.doi)}}},")
        if p.url:
            lines.append(f"  url = {{{_escape_bibtex(p.url)}}},")
        lines.append("}")
        entries.append("\n".join(lines))
    return "\n\n".join(entries)


def _sanitize_ris_field(text: str) -> str:
    """Strips control characters and collapses newlines in RIS field values."""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def export_to_ris(result: QueryResult) -> str:
    """Exports papers in QueryResult to RIS reference manager format."""
    entries = []
    for p in result.papers:
        lines = ["TY  - JOUR"]
        lines.append(f"TI  - {_sanitize_ris_field(p.title)}")
        for a in p.authors:
            lines.append(f"AU  - {_sanitize_ris_field(a.name)}")
        if p.year:
            lines.append(f"PY  - {p.year}")
        if p.journal:
            lines.append(f"JO  - {_sanitize_ris_field(p.journal)}")
        if p.doi:
            lines.append(f"DO  - {_sanitize_ris_field(p.doi)}")
        if p.url:
            lines.append(f"UR  - {_sanitize_ris_field(p.url)}")
        if p.abstract:
            clean_ab = _sanitize_ris_field(p.abstract)
            lines.append(f"AB  - {clean_ab}")
        lines.append("ER  - ")
        entries.append("\n".join(lines))
    return "\n\n".join(entries)


def export_data(result: QueryResult, format_type: str, output_path: str | None = None) -> str:
    """
    Exports QueryResult into the requested format (json, csv, bib, ris).
    If output_path is provided, writes content to file.
    """
    fmt = format_type.lower().strip(".")
    if fmt in ["json"]:
        content = export_to_json(result)
    elif fmt in ["csv"]:
        content = export_to_csv(result)
    elif fmt in ["bib", "bibtex"]:
        content = export_to_bibtex(result)
    elif fmt in ["ris"]:
        content = export_to_ris(result)
    else:
        raise ValueError(f"Unsupported export format: {format_type}. Supported: json, csv, bib, ris")

    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(content)

    return content
