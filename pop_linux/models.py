
from pydantic import BaseModel, Field


class Author(BaseModel):
    """Author metadata for scholarly paper."""
    name: str
    affiliation: str | None = None
    author_id: str | None = None


class Paper(BaseModel):
    """Core Pydantic data model representing an academic publication."""
    title: str
    authors: list[Author] = Field(default_factory=list)
    year: int | None = None
    journal: str | None = None
    citations: int = 0
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    source_provider: str = ""
    paper_id: str | None = None

    @property
    def author_string(self) -> str:
        """Returns comma-separated string of author names."""
        if not self.authors:
            return "Unknown"
        return ", ".join(a.name for a in self.authors)

    @property
    def author_count(self) -> int:
        """Returns author count (defaults to 1 if empty)."""
        return max(len(self.authors), 1)


class Metrics(BaseModel):
    """Harzing Bibliometrics metrics summary."""
    total_papers: int = 0
    total_citations: int = 0
    avg_citations_per_paper: float = 0.0
    citations_per_author: float = 0.0
    h_index: int = 0
    g_index: int = 0
    e_index: float = 0.0
    hI_annual: float = 0.0
    hL_norm: float = 0.0
    awcr: float = 0.0
    aw_index: float = 0.0
    i10_index: int = 0


class QueryResult(BaseModel):
    """Aggregated search response containing papers, metrics, and search metadata."""
    query: str
    provider: str
    total_found: int = 0
    papers: list[Paper] = Field(default_factory=list)
    metrics: Metrics | None = None
    search_time_seconds: float = 0.0
