"""
Scholarly search providers package for pop-linux.
"""

from pop_linux.providers.base import BaseProvider
from pop_linux.providers.crossref import CrossRefProvider
from pop_linux.providers.openalex import OpenAlexProvider
from pop_linux.providers.pubmed import PubMedProvider
from pop_linux.providers.semanticscholar import SemanticScholarProvider

PROVIDERS: dict[str, type[BaseProvider]] = {
    "openalex": OpenAlexProvider,
    "semanticscholar": SemanticScholarProvider,
    "crossref": CrossRefProvider,
    "pubmed": PubMedProvider,
}

def get_provider(name: str) -> BaseProvider:
    name_lower = name.lower()
    if name_lower not in PROVIDERS:
        raise ValueError(f"Unknown provider '{name}'. Available providers: {list(PROVIDERS.keys()) + ['google_scholar']}")
    return PROVIDERS[name_lower]()
