"""Publication identity service (Packet 6).

The single owner of publication-equivalence decisions for pop-linux. Live
deduplication (utils/deduplicator.py) and history comparison (utils/history.py
from Packet 15) must both use this module; no other module may invent its own
publication-equivalence rule.

Fixed rules (implementation_plan.md section 5):

1. DOIs are normalized by stripping URL prefixes, trimming, lowercasing.
2. Same normalized DOI -> same publication.
3. Different non-empty normalized DOIs -> NOT the same publication, regardless
   of title similarity. This is a hard block on the previously documented
   over-merge risk.
4. Neither record has a DOI -> fuzzy title matching with year constraints.
5. Only one record has a DOI -> fuzzy fallback may associate the DOI-missing
   observation on strong title/year evidence (explicit fallback rule).
6. Conflicting known years block fuzzy equivalence.
7. Unicode/punctuation normalization is deterministic and tested.
8. The 0.92 title threshold is retained pending a representative fixture
   corpus (deferred question; do not retune casually).
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from pop_linux.models import Paper

#: Fuzzy title similarity threshold. Retained from the reconciled baseline.
FUZZY_TITLE_THRESHOLD = 0.92

MatchReason = Literal["doi_exact", "fuzzy_title", "fuzzy_title_doi_fallback", "no_match"]


@dataclass(frozen=True)
class IdentityDecision:
    """Explains an equivalence decision (used by tests and diagnostics)."""

    same: bool
    reason: MatchReason
    similarity: float | None = None
    detail: str | None = None


def normalize_doi(doi: str | None) -> str | None:
    """Normalizes DOI by removing HTTP/HTTPS URL prefixes and lowercasing."""
    if not doi:
        return None
    import re

    cleaned = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE)
    return cleaned.lower() if cleaned else None


def normalize_title(title: str) -> str:
    """Deterministically normalizes a title for fuzzy comparison.

    Unicode NFKC folding, lowercasing, punctuation removal, whitespace
    collapse. Deterministic across runs and platforms.
    """
    import re
    import unicodedata

    folded = unicodedata.normalize("NFKC", title or "").lower()
    no_punct = re.sub(r"[^\w\s]", " ", folded, flags=re.UNICODE)
    return re.sub(r"\s+", " ", no_punct).strip()


def identity_token(paper: Paper) -> str:
    """Deterministic identity token suitable for history storage.

    DOI-backed records use `doi:<normalized-doi>`; DOI-missing records use a
    stable fingerprint over normalized title plus year state. The token is an
    implementation identity, not a claim that bibliographic ambiguity is gone.
    """
    import hashlib

    doi = normalize_doi(paper.doi)
    if doi:
        return f"doi:{doi}"
    year_state = str(paper.year) if paper.year else "unknown"
    basis = f"{normalize_title(paper.title)}|{year_state}"
    return "fp:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def compare_papers(p1: Paper, p2: Paper) -> IdentityDecision:
    """Decides whether two records represent the same publication.

    Ordered rules (first match wins):
      1. both DOIs present and equal -> same (doi_exact)
      2. both DOIs present and different -> NOT same (hard block)
      3. fuzzy title with year constraints; when exactly one DOI is present,
         a successful fuzzy match is labeled fuzzy_title_doi_fallback
    """
    doi1 = normalize_doi(p1.doi)
    doi2 = normalize_doi(p2.doi)

    if doi1 and doi2:
        if doi1 == doi2:
            return IdentityDecision(same=True, reason="doi_exact")
        return IdentityDecision(
            same=False,
            reason="no_match",
            detail="different non-empty DOIs block fuzzy merge",
        )

    t1 = normalize_title(p1.title)
    t2 = normalize_title(p2.title)
    if not t1 or not t2:
        return IdentityDecision(same=False, reason="no_match", detail="empty normalized title")

    if p1.year and p2.year and p1.year != p2.year:
        return IdentityDecision(same=False, reason="no_match", detail="conflicting known years")

    similarity = SequenceMatcher(None, t1, t2).ratio()
    if similarity >= FUZZY_TITLE_THRESHOLD:
        reason: MatchReason = "fuzzy_title" if (doi1 is None and doi2 is None) else "fuzzy_title_doi_fallback"
        return IdentityDecision(same=True, reason=reason, similarity=round(similarity, 4))

    return IdentityDecision(same=False, reason="no_match", similarity=round(similarity, 4))


def is_same_paper(p1: Paper, p2: Paper) -> bool:
    """Boolean convenience over compare_papers."""
    return compare_papers(p1, p2).same
