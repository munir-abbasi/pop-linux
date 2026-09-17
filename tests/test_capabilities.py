"""Capability registry and readiness tests (Packet 5)."""

import json

from typer.testing import CliRunner

from pop_linux.cli import app
from pop_linux.providers import PROVIDERS
from pop_linux.providers.capabilities import (
    CAPABILITIES,
    CapabilitiesDocument,
    build_capabilities_document,
    get_capabilities,
    validate_registry,
)

runner = CliRunner()


def test_every_registered_provider_has_capabilities():
    validate_registry(PROVIDERS)
    assert set(CAPABILITIES) >= set(PROVIDERS)
    assert "google_scholar" in CAPABILITIES


def test_capability_keys_match_provider_names():
    for key, caps in CAPABILITIES.items():
        assert caps.key == key


def test_all_membership_is_explicit():
    included = [k for k, c in CAPABILITIES.items() if c.included_in_all]
    assert set(included) == {"openalex", "semanticscholar", "crossref", "pubmed"}
    assert CAPABILITIES["google_scholar"].included_in_all is False


def test_filter_modes_present_and_min_citations_is_post_filter():
    for _key, caps in CAPABILITIES.items():
        assert set(caps.filter_modes) == {"author", "journal", "issn", "year_from", "year_to", "min_citations"}
        assert caps.filter_modes["min_citations"] == "post_filter"
    # Provider-specific semantics preserved from implementation facts:
    assert CAPABILITIES["crossref"].filter_modes["issn"] == "native"
    assert CAPABILITIES["semanticscholar"].filter_modes["issn"] == "query_hint"
    assert CAPABILITIES["google_scholar"].filter_modes["issn"] == "unsupported"


def test_document_schema_identifier_stable():
    assert CAPABILITIES.__class__ is not None
    from pop_linux.providers.capabilities import CAPABILITIES_SCHEMA

    assert CAPABILITIES_SCHEMA == "pop-linux.capabilities/v1"


def test_document_never_contains_secret_values(monkeypatch, tmp_path):
    import pop_linux.config as cfg_module

    cfg_module.CONFIG_DIR = tmp_path
    cfg_module.CONFIG_FILE = tmp_path / "config.toml"
    cfg_module.save_config(
        {**cfg_module.DEFAULT_CONFIG, "api_keys": {"semanticscholar": "SUPERSECRET-VALUE", "ncbi": ""}}
    )

    doc = build_capabilities_document(cfg_module.load_config())
    serialized = doc.model_dump_json()
    assert "SUPERSECRET-VALUE" not in serialized
    # State is reported, value is not:
    assert doc.provider_readiness["semanticscholar"].credential_configured is True
    assert doc.provider_readiness["pubmed"].credential_configured is False


def test_readiness_makes_no_network_calls(monkeypatch):
    """Readiness must not construct HTTP clients or perform provider calls."""
    import httpx

    def _no_client(*args, **kwargs):
        raise AssertionError("readiness must not create network clients")

    monkeypatch.setattr(httpx, "AsyncClient", _no_client)
    monkeypatch.setattr(httpx, "Client", _no_client)

    doc = build_capabilities_document({})
    assert doc.app_version


def test_playwright_readiness_without_side_effects():
    doc = build_capabilities_document({})
    assert isinstance(doc.environment.playwright_importable, bool)
    assert doc.environment.chromium_detected in (True, False, None)


def test_machine_capabilities_output_is_stable_json(monkeypatch, tmp_path):
    import pop_linux.config as cfg_module

    cfg_module.CONFIG_DIR = tmp_path
    cfg_module.CONFIG_FILE = tmp_path / "config.toml"

    res = runner.invoke(app, ["--machine", "capabilities"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)  # stdout purity applies to capabilities too
    assert data["schema"] == "pop-linux.capabilities/v1"
    assert data["execution_schema"] == "pop-linux.execution/v1"
    assert set(data["providers"]) == {
        "openalex",
        "semanticscholar",
        "crossref",
        "pubmed",
        "google_scholar",
    }
    assert "\x1b" not in res.stdout


def test_human_capabilities_renders_table():
    res = runner.invoke(app, ["capabilities"])
    assert res.exit_code == 0
    assert "Provider Capabilities" in res.stdout
    assert "openalex" in res.stdout
    assert "post" in res.stdout


def test_machine_providers_aliases_capabilities():
    res = runner.invoke(app, ["--machine", "providers"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["schema"] == "pop-linux.capabilities/v1"


def test_human_providers_still_works():
    res = runner.invoke(app, ["providers"])
    assert res.exit_code == 0
    assert "openalex" in res.stdout
    assert "google_scholar" in res.stdout


def test_get_capabilities_unknown_provider_raises():
    import pytest

    with pytest.raises(KeyError):
        get_capabilities("does_not_exist")


def test_document_round_trips():
    doc = build_capabilities_document({})
    restored = CapabilitiesDocument.model_validate(json.loads(doc.model_dump_json()))
    assert restored == doc
