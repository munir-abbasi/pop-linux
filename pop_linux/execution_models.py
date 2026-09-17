"""Execution-contract models for pop-linux.

This module defines the agent-facing execution contract described in
implementation_plan.md section 4: policies, requests, provider reports,
metrics context, persistence reports, and the execution envelope.

Design rules:
- String enums so serialized JSON stays legible and stable across releases.
- No credential/cookie/secret-bearing fields exist anywhere in these models.
- The resolved SearchRequest represents the request AFTER CLI defaults and
  configuration have been applied; it is what machine output returns and what
  history persists.
- These models are additive relative to the legacy scholarly domain models in
  pop_linux.models (Author, Paper, Metrics, QueryResult), which remain the
  normalized-data contract shared with providers and exporters.

Schema identity is explicit and independent of the package version:
    pop-linux.execution/v1
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pop_linux.models import Metrics, Paper

#: Versioned machine schema identifier. Additive evolution only within v1;
#: breaking changes require a new explicit schema version.
EXECUTION_SCHEMA = "pop-linux.execution/v1"

#: Status of the aggregate execution.
ExecutionStatus = Literal["success", "partial", "empty", "error"]

#: Status of one provider within an execution.
ProviderStatus = Literal["success", "empty", "error", "blocked", "skipped"]

#: How a requested filter was actually enforced by a provider.
FilterMode = Literal["native", "query_hint", "post_filter", "unsupported"]

#: Whether interactive behavior (e.g. a browser challenge) may be launched.
InteractionPolicy = Literal["allow", "never"]

#: Whether/when history persistence happens for an execution.
PersistencePolicy = Literal["auto", "off", "explicit"]

#: How the preferred citation count is chosen for merged records.
CitationSelectionPolicy = Literal["provider_native", "max_observed"]

#: Result completeness for metrics interpretation.
ResultCompleteness = Literal["complete", "partial", "bounded"]


class SearchFilters(BaseModel):
    """Serializable value object for query constraints.

    Validation belongs here (e.g. year bounds coherence) so both the CLI and
    any future API surface enforce the same rules.
    """

    model_config = ConfigDict(extra="forbid")

    author: str | None = None
    journal: str | None = None
    issn: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    min_citations: int | None = None

    @field_validator("year_from", "year_to", "min_citations")
    @classmethod
    def _sane_ints(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if v < 0:
            raise ValueError("filter bounds must be non-negative")
        return v

    @model_validator(mode="after")
    def _year_bounds_coherent(self) -> "SearchFilters":
        if self.year_from is not None and self.year_to is not None and self.year_from > self.year_to:
            raise ValueError("year_from must be <= year_to")
        return self


class SearchRequest(BaseModel):
    """The resolved request after CLI defaults/config have been applied.

    This object is returned in machine output and persisted to history. It must
    never contain credentials, cookies, or other secrets; no such fields exist.
    """

    model_config = ConfigDict(extra="forbid")

    query: str
    profile_id: str | None = None
    providers: list[str] = Field(min_length=1)
    limit: int = Field(gt=0)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    interaction_policy: InteractionPolicy = "allow"
    persistence_policy: PersistencePolicy = "auto"
    sort_policy: str | None = None

    @field_validator("providers")
    @classmethod
    def _providers_nonempty_names(cls, v: list[str]) -> list[str]:
        if not v or any(not isinstance(name, str) or not name.strip() for name in v):
            raise ValueError("providers must contain non-empty names")
        return v


class ExecutionMessage(BaseModel):
    """A structured warning or error carrying machine-branchable semantics.

    `code` carries meaning and is a compatibility contract; `message` is
    human-readable and may evolve. `metadata` must never carry secrets.
    """

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    provider: str | None = None
    retryable: bool | None = None
    metadata: dict[str, Any] | None = None


class ProviderCounts(BaseModel):
    """Distinct record-count concepts; callers must not conflate them.

    matched: upstream provider-reported total when available (None if unknown).
    fetched: records downloaded/parsed before common post-filtering.
    after_filter: records surviving local/common filtering.
    returned: records contributed to aggregation after provider-side truncation.
    """

    model_config = ConfigDict(extra="forbid")

    matched: int | None = None
    fetched: int = 0
    after_filter: int = 0
    returned: int = 0


class ProviderReport(BaseModel):
    """Per-provider execution evidence for one request execution.

    Contains enough information to decide whether the aggregate result is
    complete relative to the requested provider set.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str
    status: ProviderStatus
    elapsed_seconds: float = 0.0
    counts: ProviderCounts = Field(default_factory=ProviderCounts)
    pages_or_requests: int | None = None
    filter_modes: dict[str, FilterMode] | None = None
    warnings: list[ExecutionMessage] = Field(default_factory=list)
    errors: list[ExecutionMessage] = Field(default_factory=list)
    interaction_required: bool = False


class MetricsContext(BaseModel):
    """Interpretation context for the metrics block of an execution.

    Makes dataset scope and citation selection explicit without changing any
    numeric formula.
    """

    model_config = ConfigDict(extra="forbid")

    paper_count: int = 0
    bounded_by_limit: bool = False
    providers_contributing: list[str] = Field(default_factory=list)
    citation_selection_policy: CitationSelectionPolicy = "max_observed"
    completeness: ResultCompleteness = "complete"
    calculation_year: int | None = None
    calculation_timestamp: str | None = None


class PersistenceReport(BaseModel):
    """Explicit representation of side effects for one execution."""

    model_config = ConfigDict(extra="forbid")

    history_policy: PersistencePolicy = "auto"
    snapshot_written: bool = False
    snapshot_id: int | None = None
    exported: list[dict[str, str]] = Field(default_factory=list)
    errors: list[ExecutionMessage] = Field(default_factory=list)


class SourceObservation(BaseModel):
    """Material provider evidence retained before merge (Packet 7).

    One observation is one provider's view of one publication. Merged
    normalized values must remain traceable back to these observations.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str
    paper_id: str | None = None
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    journal: str | None = None
    citations: int | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None


class ProvenanceEntry(BaseModel):
    """Provenance for one normalized publication.

    Carries the identity token plus the observations that were merged into the
    record, and names the policy that selected the preferred citation count.
    """

    model_config = ConfigDict(extra="forbid")

    canonical_id: str
    citation_selection_policy: CitationSelectionPolicy = "max_observed"
    observations: list[SourceObservation] = Field(default_factory=list)
    preferred_citation_source: str | None = None


class AggregateCounts(BaseModel):
    """Aggregate record counts across the whole execution.

    matched/fetched concepts are provider-level; at aggregate level the
    meaningful numbers are the distinct records surviving each stage.
    """

    model_config = ConfigDict(extra="forbid")

    returned_raw: int = 0
    merged: int = 0


class ExecutionEnvelope(BaseModel):
    """The machine-facing root object of one execution.

    The envelope, not the exit code alone, is the authoritative machine
    execution result. Exit codes remain coarse (0 = usable envelope, nonzero =
    execution failed to produce a valid result).

    The wire key for the schema identifier is "schema" (see EXECUTION_SCHEMA).
    The Python attribute is `schema_` with a serialization alias so the model
    avoids shadowing the deprecated Pydantic BaseModel.schema() API.
    """

    model_config = ConfigDict(extra="forbid", serialize_by_alias=True)

    schema_: Literal["pop-linux.execution/v1"] = Field(default=EXECUTION_SCHEMA, alias="schema")
    app_version: str
    status: ExecutionStatus
    request: SearchRequest
    provider_reports: list[ProviderReport] = Field(default_factory=list)
    counts: AggregateCounts = Field(default_factory=AggregateCounts)
    papers: list[Paper] = Field(default_factory=list)
    provenance: list[ProvenanceEntry] = Field(default_factory=list)
    metrics: Metrics | None = None
    metrics_context: MetricsContext | None = None
    persistence: PersistenceReport = Field(default_factory=PersistenceReport)
    warnings: list[ExecutionMessage] = Field(default_factory=list)
    errors: list[ExecutionMessage] = Field(default_factory=list)
    elapsed_seconds: float = 0.0


__all__ = [
    "EXECUTION_SCHEMA",
    "AggregateCounts",
    "CitationSelectionPolicy",
    "ExecutionEnvelope",
    "ExecutionMessage",
    "ExecutionStatus",
    "FilterMode",
    "InteractionPolicy",
    "MetricsContext",
    "PersistencePolicy",
    "PersistenceReport",
    "ProviderCounts",
    "ProviderReport",
    "ProviderStatus",
    "ProvenanceEntry",
    "ResultCompleteness",
    "SearchFilters",
    "SearchRequest",
    "SourceObservation",
]
