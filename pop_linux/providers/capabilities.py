"""Canonical provider capability registry and readiness model (Packet 5).

One registry backs provider construction, capability discovery, and the
`capabilities` command. Capability declarations here replace scattered
hard-coded provider tables in CLI code and documentation: provider construction
and capability lookup consume the same entries.

Readiness checks inspect LOCAL state only (config key presence, Playwright
import availability, default Chromium cache locations, path writability). They
never perform a live provider call and never expose secret VALUES — only
configured/not-configured state.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pop_linux import __version__
from pop_linux.execution_models import EXECUTION_SCHEMA, FilterMode
from pop_linux.providers.base import BaseProvider

#: Schema identifier for the capabilities document (independent of app version).
CAPABILITIES_SCHEMA = "pop-linux.capabilities/v1"

RetrievalType = Literal["rest", "html"]
CredentialType = Literal["none", "api_key_optional", "cookies"]


class ProviderCapabilities(BaseModel):
    """Static capability facts about one provider.

    These are implementation facts about the installed provider adapter, not
    guarantees about remote service quotas.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    display_name: str
    retrieval_type: RetrievalType
    included_in_all: bool
    #: Effective enforcement mode per supported filter. Filters absent from
    #: this map are unsupported for the provider.
    filter_modes: dict[str, FilterMode] = Field(default_factory=dict)
    #: Maximum records retrievable in one request/page under current code.
    one_request_cap: int
    #: Whether the adapter paginates beyond one request today.
    pagination: bool
    interactive_risk: bool
    credential_type: CredentialType = "none"
    citation_counts_available: bool
    profile_search: bool
    description: str = ""


class ProviderReadiness(BaseModel):
    """Local-state readiness for one provider. Never contains secret values."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    credential_configured: bool | None = None
    notes: list[str] = Field(default_factory=list)


class EnvironmentReadiness(BaseModel):
    """Local environment facts relevant to interactive/HTML providers."""

    model_config = ConfigDict(extra="forbid")

    playwright_importable: bool
    chromium_detected: bool | None = None  # None = could not determine cheaply


class PathsReadiness(BaseModel):
    """Application-owned state paths (never their contents)."""

    model_config = ConfigDict(extra="forbid")

    config_file: str
    cookies_file: str
    history_db: str
    history_dir_writable: bool


class CapabilitiesDocument(BaseModel):
    """Machine-facing capabilities/readiness root object."""

    model_config = ConfigDict(extra="forbid", serialize_by_alias=True)

    schema_: Literal["pop-linux.capabilities/v1"] = Field(
        default=CAPABILITIES_SCHEMA, alias="schema"
    )
    app_version: str
    execution_schema: str
    providers: dict[str, ProviderCapabilities]
    provider_readiness: dict[str, ProviderReadiness]
    environment: EnvironmentReadiness
    paths: PathsReadiness


def _filter_modes(
    author: FilterMode,
    journal: FilterMode,
    issn: FilterMode,
    year: FilterMode,
) -> dict[str, FilterMode]:
    """Builds the per-filter mode map shared by all providers.

    min_citations is always a local post-filter in current code; year bounds
    share one mode per provider because they compile into the same parameter.
    """
    return {
        "author": author,
        "journal": journal,
        "issn": issn,
        "year_from": year,
        "year_to": year,
        "min_citations": "post_filter",
    }


#: THE capability registry. Provider construction and capability lookup must
#: consume these entries (see providers/__init__.py) instead of maintaining
#: parallel hard-coded maps.
CAPABILITIES: dict[str, ProviderCapabilities] = {
    "openalex": ProviderCapabilities(
        key="openalex",
        display_name="OpenAlex",
        retrieval_type="rest",
        included_in_all=True,
        filter_modes=_filter_modes(
            author="query_hint", journal="query_hint", issn="native", year="native"
        ),
        one_request_cap=200,
        pagination=False,
        interactive_risk=False,
        credential_type="none",
        citation_counts_available=True,
        profile_search=False,
        description="Fast structured scholarly works metadata; keyless by default.",
    ),
    "semanticscholar": ProviderCapabilities(
        key="semanticscholar",
        display_name="Semantic Scholar",
        retrieval_type="rest",
        included_in_all=True,
        filter_modes=_filter_modes(
            author="query_hint", journal="query_hint", issn="query_hint", year="native"
        ),
        one_request_cap=100,
        pagination=False,
        interactive_risk=False,
        credential_type="api_key_optional",
        citation_counts_available=True,
        profile_search=False,
        description="Semantic Scholar Graph API with citations, venues, abstracts.",
    ),
    "crossref": ProviderCapabilities(
        key="crossref",
        display_name="CrossRef",
        retrieval_type="rest",
        included_in_all=True,
        filter_modes=_filter_modes(
            author="native", journal="native", issn="native", year="native"
        ),
        one_request_cap=100,
        pagination=False,
        interactive_risk=False,
        credential_type="none",
        citation_counts_available=True,
        profile_search=False,
        description="Publisher metadata, DOI lookups, citation counts.",
    ),
    "pubmed": ProviderCapabilities(
        key="pubmed",
        display_name="PubMed",
        retrieval_type="rest",
        included_in_all=True,
        filter_modes=_filter_modes(
            author="native", journal="native", issn="native", year="native"
        ),
        one_request_cap=100,
        pagination=False,
        interactive_risk=False,
        credential_type="api_key_optional",
        citation_counts_available=False,
        profile_search=False,
        description="NCBI Entrez biomedical and life sciences literature.",
    ),
    "google_scholar": ProviderCapabilities(
        key="google_scholar",
        display_name="Google Scholar",
        retrieval_type="html",
        included_in_all=False,
        filter_modes=_filter_modes(
            author="query_hint", journal="query_hint", issn="unsupported", year="native"
        ),
        one_request_cap=20,
        pagination=True,
        interactive_risk=True,
        credential_type="cookies",
        citation_counts_available=True,
        profile_search=True,
        description="HTML integration with interactive challenge handling; "
        "excluded from `all` and forbidden in machine mode.",
    ),
}


def get_capabilities(name: str) -> ProviderCapabilities:
    """Returns capability facts for a provider key."""
    key = name.lower()
    if key not in CAPABILITIES:
        raise KeyError(f"Unknown provider '{name}'. Known: {sorted(CAPABILITIES)}")
    return CAPABILITIES[key]


def validate_registry(provider_map: dict[str, type[BaseProvider]]) -> None:
    """Fails fast if provider construction and capability tables drift apart."""
    missing = set(provider_map) - set(CAPABILITIES)
    if missing:
        raise RuntimeError(f"Providers missing capability entries: {sorted(missing)}")


def _playwright_importable() -> bool:
    return importlib.util.find_spec("playwright") is not None


def _chromium_detected() -> bool | None:
    """Cheap deterministic check of the default Playwright browser cache.

    Scans standard ms-playwright cache locations for a chromium-* directory.
    Returns None when no cache location exists (cannot determine).
    """
    candidates = [
        Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ms-playwright",
        Path.home() / "AppData" / "Local" / "ms-playwright",  # best-effort cross-platform
        Path.home() / "Library" / "Caches" / "ms-playwright",
    ]
    for base in candidates:
        if base.is_dir():
            for child in base.iterdir():
                if child.name.startswith("chromium"):
                    return True
            return False
    return None


def _api_key_configured(provider_key: str, cfg: dict) -> bool | None:
    """Reports configured/not-configured state only; never the value."""
    mapping = {"semanticscholar": "semanticscholar", "pubmed": "ncbi"}
    config_key = mapping.get(provider_key)
    if config_key is None:
        return None
    return bool((cfg.get("api_keys", {}).get(config_key) or "").strip())


def _history_dir_writable() -> bool:
    from pop_linux.config import CONFIG_DIR

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return os.access(CONFIG_DIR, os.W_OK)
    except OSError:
        return False


def _cookies_configured(cfg: dict) -> bool:
    cookies_path = Path(cfg.get("cookies_file") or "")
    return cookies_path.is_file() and cookies_path.stat().st_size > 0


def build_readiness(cfg: dict) -> tuple[dict[str, ProviderReadiness], EnvironmentReadiness, PathsReadiness]:
    """Builds readiness facts from local state only (no network calls)."""
    from pop_linux.config import COOKIES_FILE, CONFIG_FILE, HISTORY_DB_FILE

    readiness: dict[str, ProviderReadiness] = {}
    for key, caps in CAPABILITIES.items():
        notes: list[str] = []
        cred = _api_key_configured(key, cfg)
        if caps.credential_type == "api_key_optional":
            notes.append("api key configured" if cred else "running keyless")
        if caps.credential_type == "cookies":
            notes.append("scholar cookies present" if _cookies_configured(cfg) else "no stored scholar cookies")
        readiness[key] = ProviderReadiness(provider=key, credential_configured=cred, notes=notes)

    env = EnvironmentReadiness(
        playwright_importable=_playwright_importable(),
        chromium_detected=_chromium_detected(),
    )

    paths = PathsReadiness(
        config_file=str(CONFIG_FILE),
        cookies_file=str(COOKIES_FILE),
        history_db=str(HISTORY_DB_FILE),
        history_dir_writable=_history_dir_writable(),
    )
    return readiness, env, paths


def build_capabilities_document(cfg: dict) -> CapabilitiesDocument:
    """Assembles the full capabilities/readiness document."""
    readiness, env, paths = build_readiness(cfg)
    return CapabilitiesDocument(
        app_version=__version__,
        execution_schema=EXECUTION_SCHEMA,
        providers=dict(CAPABILITIES),
        provider_readiness=readiness,
        environment=env,
        paths=paths,
    )
