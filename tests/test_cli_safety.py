from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import httpx
from typer.testing import CliRunner

from pop_linux.cli import _mask_secret, _CONTROL_SEQ_RE, app, safe_text
from pop_linux.models import Author, Paper, QueryResult

runner = CliRunner()


def test_safe_text_strips_ansi_and_control_sequences():
    raw = "Title\x1b[31mred\x1b[0m \x1b]8;;http://evil.example\x1b\\link\x1b]8;;\x1b\\ \x07noise"
    cleaned = safe_text(raw)
    assert "\x1b" not in cleaned
    assert "red" in cleaned
    assert "link" in cleaned
    assert "noise" in cleaned


def test_safe_text_escapes_rich_markup():
    assert safe_text("Bold [bold]not-formatting[/bold]") == "Bold \\[bold]not-formatting\\[/bold]"
    # Rich would render markup inside [] unless escaped; escaped output is inert text
    assert safe_text("[link](javascript:alert(1))") == "\\[link](javascript:alert(1))"
    assert "\\[" in safe_text("[link](javascript:alert(1))")


def test_safe_text_handles_none_and_types():
    assert safe_text(None) == ""
    assert safe_text(123) == "123"


def test_control_seq_regex_removes_osc8_hyperlink():
    raw = "visible text" + "\x1b]8;;https://evil\x07anchor\x1b]8;;\x1b\\" + " tail"
    stripped = _CONTROL_SEQ_RE.sub("", raw)
    assert "\x1b" not in stripped
    assert stripped == "visible textanchor tail"


def test_mask_secret():
    assert _mask_secret("abcdefghij") == "abc...hij"
    assert _mask_secret("secret") == "*" * 6
    assert _mask_secret("") == ""


def test_config_show_masks_api_keys(monkeypatch, tmp_path):
    import pop_linux.cli as cli
    from pop_linux import config as cfg_module

    cfg_module.CONFIG_DIR = tmp_path
    cfg_module.CONFIG_FILE = tmp_path / "config.toml"
    cfg = {
        "default_provider": "openalex",
        "default_limit": 50,
        "polite_email": "test@example.com",
        "api_keys": {"semanticscholar": "super-secret-key-value-123", "ncbi": "abc123"}
    }
    cfg_module.save_config(cfg)
    monkeypatch.setattr(cli, "CONFIG_FILE", cfg_module.CONFIG_FILE)

    res = runner.invoke(app, ["config", "--show"])
    assert res.exit_code == 0
    assert "super-secret-key-value-123" not in res.stdout
    assert "abc123" not in res.stdout
    assert "sup...123" in res.stdout  # masked api key
    assert "*" * 6 in res.stdout       # short key fully masked


def test_search_without_query_exits_nonzero():
    res = runner.invoke(app, ["search"])
    assert res.exit_code != 0
    assert "query" in res.stdout.lower() or "Usage" in res.stdout


def test_render_papers_table_escapes_ansi_in_titles():
    from pop_linux.cli import render_papers_table

    paper = Paper(
        title="Evil \x1b[31mred\x1b[0m [bold]title[/bold]",
        authors=[Author(name="Attack")],
        year=2024,
        citations=1,
        source_provider="openalex"
    )
    result = QueryResult(query="q", provider="openalex", total_found=1, papers=[paper])
    render_papers_table(result)  # Must not raise on control chars


def test_live_ansi_round_trip():
    payload = "Paper \x1b]8;;http://evil/x\x1b\\Click me\x1b]8;;\x1b\\ \x1b[32mgreen\x1b[0m"
    assert "\x1b" in payload  # Precondition: payload actually carries control sequences
    cleaned = safe_text(payload)
    assert "\x1b" not in cleaned
    assert "\x07" not in cleaned


async def test_retry_backs_off_then_succeeds():
    from pop_linux.providers import openalex as oa_module

    provider = oa_module.OpenAlexProvider()
    # Only transient responses then a good one
    transient = httpx.Response(status_code=429, request=httpx.Request("GET", provider.API_URL))
    ok = httpx.Response(status_code=200, json={"results": [], "meta": {"count": 0}}, request=httpx.Request("GET", provider.API_URL))

    client = MagicMock()
    client.get = AsyncMock(side_effect=[transient, transient, ok])

    with mock.patch("asyncio.sleep", new=AsyncMock()) as fake_sleep:
        resp = await provider._get_with_retry(client, provider.API_URL, {})

    assert resp.status_code == 200
    assert client.get.call_count == 3
    assert fake_sleep.call_count == 2  # backoff before each retry


async def test_retry_returns_last_transient_when_exhausted():
    from pop_linux.providers import openalex as oa_module

    provider = oa_module.OpenAlexProvider()
    transient = httpx.Response(status_code=503, request=httpx.Request("GET", provider.API_URL))

    client = MagicMock()
    client.get = AsyncMock(side_effect=[transient] * 3)

    with mock.patch("asyncio.sleep", new=AsyncMock()) as fake_sleep:
        resp = await provider._get_with_retry(client, provider.API_URL, {})

    assert resp.status_code == 503
    assert client.get.call_count == 3
    # No dead sleep after the final (exhausted) attempt
    assert fake_sleep.call_count == 2


async def test_retry_no_sleep_after_final_transport_error():
    from pop_linux.providers import openalex as oa_module

    provider = oa_module.OpenAlexProvider()

    client = MagicMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with mock.patch("asyncio.sleep", new=AsyncMock()) as fake_sleep:
        try:
            await provider._get_with_retry(client, provider.API_URL, {})
            raise AssertionError("expected ConnectError to propagate")
        except httpx.ConnectError:
            pass

    assert client.get.call_count == 3
    assert fake_sleep.call_count == 2  # backoff for attempts 0 and 1 only


async def test_pubmed_keyless_fallback_paces_request(monkeypatch):
    from pop_linux.providers import pubmed as pm_module

    monkeypatch.setattr(pm_module, "load_config", lambda: {"api_keys": {"ncbi": "badkey"}})

    provider = pm_module.PubMedProvider()

    esearch_calls: list = []
    esummary_calls: list = []

    async def fake_retry(client, url, params, headers=None):
        if "esearch" in url:
            esearch_calls.append(dict(params))
            if params.get("api_key") == "badkey":
                return httpx.Response(status_code=401, request=httpx.Request("GET", url))
            return httpx.Response(
                status_code=200,
                json={"esearchresult": {"count": 1, "idlist": ["1"]}},
                request=httpx.Request("GET", url),
            )
        esummary_calls.append(dict(params))
        if params.get("api_key") == "badkey":
            return httpx.Response(status_code=401, request=httpx.Request("GET", url))
        return httpx.Response(
            status_code=200,
            json={"result": {"1": {"title": "T", "pubdate": "2020", "articleids": []}}},
            request=httpx.Request("GET", url),
        )

    provider._get_with_retry = fake_retry  # type: ignore[method-assign]

    sleep_calls: list = []

    async def _fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(pm_module.asyncio, "sleep", _fake_sleep)

    result = await provider.search("test", limit=5)

    assert result is not None
    assert len(esearch_calls) == 2
    assert len(esummary_calls) == 2
    # The last attempt on each endpoint must not carry the rejected key
    assert "api_key" not in esearch_calls[-1]
    assert "api_key" not in esummary_calls[-1]
    assert 0.34 in sleep_calls


async def test_semanticscholar_keyless_fallback_uses_clean_client(monkeypatch):
    from pop_linux.providers import semanticscholar as ss_module

    # Config provides a key, but server rejects with 403
    monkeypatch.setattr(ss_module, "load_config", lambda: {"api_keys": {"semanticscholar": "testkey"}})

    provider = ss_module.SemanticScholarProvider()

    seen: list = []

    async def fake_retry(client, url, params, headers=None):
        seen.append(client)
        if client.headers.get("x-api-key"):
            return httpx.Response(status_code=403, request=httpx.Request("GET", url))
        return httpx.Response(
            status_code=200, json={"total": 0, "data": []},
            request=httpx.Request("GET", url),
        )

    provider._get_with_retry = fake_retry  # type: ignore[method-assign]

    result = await provider.search("test")

    assert result is not None
    assert len(seen) == 2
    # The retry client must not carry the API key
    assert "x-api-key" not in seen[1].headers


def _provider_that_raises(exc):
    class _Prov:
        def __init__(self):
            self.search = AsyncMock(side_effect=exc)
            self.search_profile = AsyncMock(side_effect=exc)
    return _Prov()


def test_search_escapes_rich_markup_in_http_status_error_body(monkeypatch):
    req = httpx.Request("GET", "https://api.example.org")
    resp = httpx.Response(status_code=500, text="[green]PWNED[/green] \x1b[31mred\x1b[0m", request=req)
    exc = httpx.HTTPStatusError("boom", request=req, response=resp)
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _provider_that_raises(exc))

    res = runner.invoke(app, ["search", "query", "--provider", "openalex"])

    assert res.exit_code == 1
    # Markup must NOT be consumed as Rich markup: the literal bracket text must
    # appear (escaped) rather than being turned into styled/styled content, and
    # the payload's ANSI control chars must be stripped entirely.
    assert "[green]PWNED[/green]" in res.stdout
    assert res.stdout.count("PWNED") == 1
    assert "\x1b[31m" not in res.stdout


def test_search_escapes_generic_exception_message(monkeypatch):
    exc = RuntimeError("boom [bold]injection[/bold] \x1b[36mcyan\x1b[0m")
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _provider_that_raises(exc))

    res = runner.invoke(app, ["search", "query", "--provider", "openalex"])

    assert res.exit_code == 1
    assert "[bold]injection[/bold]" in res.stdout
    assert res.stdout.count("injection") == 1
    assert "\x1b[36m" not in res.stdout


def test_search_validates_year_range_order(monkeypatch):
    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: _provider_that_raises(RuntimeError("should not run")))

    res = runner.invoke(app, ["search", "query", "--provider", "openalex", "--year-from", "2024", "--year-to", "2020"])

    assert res.exit_code == 1
    assert "year-from must be less than or equal to --year-to" in res.stdout
    # The provider must not even be called
    assert "should not run" not in res.stdout


def test_search_uses_default_limit_when_config_value_is_invalid(monkeypatch):
    good_result = QueryResult(query="q", provider="openalex", total_found=0, papers=[])
    mock_provider = MagicMock()
    mock_provider.search = AsyncMock(side_effect=lambda query, limit, **kwargs: good_result)

    monkeypatch.setattr("pop_linux.cli.get_provider", lambda name: mock_provider)
    monkeypatch.setattr(
        "pop_linux.cli.load_config",
        lambda: {"default_limit": "not-an-int", "default_provider": "openalex"},
    )
    monkeypatch.setattr("pop_linux.cli.save_snapshot", lambda *a, **k: None)

    res = runner.invoke(app, ["search", "query"])

    assert res.exit_code == 0
    assert (mock_provider.search.call_args.kwargs or {}).get("limit") == 50
