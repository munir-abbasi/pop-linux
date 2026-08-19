import json
import pytest
from pop_linux.models import QueryResult, Paper, Author
from pop_linux.utils.exporter import export_data, export_to_bibtex, export_to_csv, export_to_ris


@pytest.fixture
def sample_result():
    papers = [
        Paper(
            title="A Breakthrough in AI",
            authors=[Author(name="Alice Smith"), Author(name="Bob Jones")],
            year=2023,
            journal="Journal of Machine Learning",
            citations=50,
            doi="10.1000/ml.2023.1",
            url="https://example.com/paper1",
            abstract="This is an abstract about AI.",
            source_provider="openalex"
        )
    ]
    return QueryResult(query="AI breakthrough", provider="openalex", total_found=1, papers=papers)


def test_export_json(sample_result):
    content = export_data(sample_result, "json")
    data = json.loads(content)
    assert data["query"] == "AI breakthrough"
    assert data["papers"][0]["title"] == "A Breakthrough in AI"


def test_export_csv(sample_result):
    content = export_data(sample_result, "csv")
    assert "Title,Authors,Year,Journal,Citations" in content
    assert "A Breakthrough in AI" in content
    assert "Alice Smith, Bob Jones" in content


def test_export_bibtex(sample_result):
    content = export_data(sample_result, "bib")
    assert "@article{" in content
    assert "title = {A Breakthrough in AI}" in content
    assert "author = {Alice Smith and Bob Jones}" in content
    assert "doi = {10.1000/ml.2023.1}" in content


def test_export_ris(sample_result):
    content = export_data(sample_result, "ris")
    assert "TY  - JOUR" in content
    assert "TI  - A Breakthrough in AI" in content
    assert "AU  - Alice Smith" in content
    assert "AU  - Bob Jones" in content
    assert "ER  - " in content


def test_export_to_file(sample_result, tmp_path):
    out_file = tmp_path / "output.bib"
    export_data(sample_result, "bib", output_path=str(out_file))
    assert out_file.exists()
    assert "A Breakthrough in AI" in out_file.read_text()


def test_export_bibtex_escaping():
    paper = Paper(
        title="100% Accuracy & Performance in C# & C++",
        authors=[Author(name="Jane & Co_Author")],
        year=2024,
        source_provider="openalex"
    )
    res = QueryResult(query="test", provider="openalex", total_found=1, papers=[paper])
    content = export_to_bibtex(res)
    assert r"100\% Accuracy \& Performance in C\# \& C++" in content
    assert r"Jane \& Co\_Author" in content


def test_export_bibtex_escapes_braces_and_specials():
    paper = Paper(
        title="Curly {braces} and \\backslash~tilde^caret",
        authors=[Author(name="Author, {Nested} & \\Escaped~Name^X")],
        year=2024,
        source_provider="openalex"
    )
    res = QueryResult(query="test", provider="openalex", total_found=1, papers=[paper])
    content = export_to_bibtex(res)
    assert r"Curly \{braces\} and \textbackslash{}backslash\textasciitilde{}tilde\textasciicircum{}caret" in content
    assert r"Author, \{Nested\} \& \textbackslash{}Escaped\textasciitilde{}Name\textasciicircum{}X" in content
    # No unescaped closing brace may occur inside a field value
    title_line = [line for line in content.splitlines() if line.strip().startswith("title")]
    assert title_line[0].count("{") == title_line[0].count("}")


def test_export_csv_neutralizes_formula_injection():
    paper = Paper(
        title="=HYPERLINK(\"http://evil.example\")",
        abstract="@SUM(A1:B2)",
        journal="-malicious",
        doi="+44",
        url="=cmd|'/C calc'!A0",
        authors=[Author(name="=1+2")],
        source_provider="openalex"
    )
    res = QueryResult(query="test", provider="openalex", total_found=1, papers=[paper])
    content = export_to_csv(res)
    assert "'=HYPERLINK" in content
    assert "'@SUM" in content
    assert "'-malicious" in content
    assert "'+44" in content
    assert "'=cmd" in content
    assert "'=1+2" in content


def test_export_csv_normal_cells_unchanged():
    paper = Paper(title="Normal Title", journal="Normal Journal", doi="10.1000/1", source_provider="openalex")
    res = QueryResult(query="test", provider="openalex", total_found=1, papers=[paper])
    content = export_to_csv(res)
    assert '"Normal Title"' in content or "Normal Title" in content
    assert "10.1000/1" in content
    assert "'=1+2" not in content


def test_export_csv_neutralizes_formula_prefix_after_leading_whitespace():
    paper = Paper(
        title=" \t=WHITESPACE_BYPASS",
        journal="\r-cmd",
        source_provider="openalex"
    )
    res = QueryResult(query="test", provider="openalex", total_found=1, papers=[paper])
    content = export_to_csv(res)
    assert "' \t=WHITESPACE_BYPASS" in content
    assert "'\r-cmd" in content


def test_export_ris_strips_control_chars_and_collapses_whitespace():
    paper = Paper(
        title="Line\nbreak\x00title",
        authors=[Author(name="A\x01X")],
        abstract="Multi\n\nline\tabstract",
        source_provider="openalex"
    )
    res = QueryResult(query="test", provider="openalex", total_found=1, papers=[paper])
    content = export_to_ris(res)
    assert "\x00" not in content
    assert "\x01" not in content
    assert "TI  - Line breaktitle" in content
    assert "AU  - AX" in content
    assert "AB  - Multi line abstract" in content

