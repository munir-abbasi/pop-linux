from unittest.mock import AsyncMock, MagicMock
from typer.testing import CliRunner
from pop_linux.cli import app
from pop_linux.models import QueryResult, Paper, Author, Metrics

runner = CliRunner()


def test_cli_version():
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert "pop-linux version" in res.stdout


def test_cli_providers():
    res = runner.invoke(app, ["providers"])
    assert res.exit_code == 0
    assert "openalex" in res.stdout
    assert "google_scholar" in res.stdout


def test_cli_config_show():
    res = runner.invoke(app, ["config", "--show"])
    assert res.exit_code == 0
    assert "Configuration File:" in res.stdout
    assert "default_provider:" in res.stdout


def test_cli_search_mock(monkeypatch):
    papers = [
        Paper(
            title="CLI Test Paper",
            authors=[Author(name="Test Author")],
            year=2024,
            journal="Test CLI Journal",
            citations=10,
            source_provider="openalex"
        )
    ]
    mock_result = QueryResult(
        query="cli test",
        provider="openalex",
        total_found=1,
        papers=papers,
        metrics=Metrics(total_papers=1, total_citations=10, h_index=1, g_index=1)
    )

    mock_provider_inst = MagicMock()
    mock_provider_inst.search = AsyncMock(return_value=mock_result)

    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: mock_provider_inst)

    res = runner.invoke(app, ["search", "cli test", "--provider", "openalex"])
    assert res.exit_code == 0
    assert "CLI Test Paper" in res.stdout
    assert "Harzing Bibliometric Summary" in res.stdout
