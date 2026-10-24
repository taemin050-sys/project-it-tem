"""Provider-neutral search-result normalization. No network/search is performed here."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
from urllib.parse import urlsplit
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .provisional_contracts import Evidence, ProductFacts


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_id: str = Field(min_length=1, max_length=80)
    source_type: Literal["web", "paper", "regulator", "browser"]
    title: str = Field(min_length=1, max_length=300)
    url_or_doi: str = Field(min_length=1, max_length=1000)
    claim_ids: list[str] = Field(default_factory=list, max_length=30)


class SearchProvider(Protocol):
    def search(self, facts: ProductFacts) -> list[SearchHit]: ...


@dataclass(frozen=True)
class ResearchBundle:
    evidence: tuple[Evidence, ...]
    mode: Literal["fixture", "live"]
    completed: bool
    # completed means the tool returned; NOT independent verification of claims

    @property
    def research_performed(self) -> bool:
        return self.mode == "live" and self.completed and bool(self.evidence)


def _safe_reference(url: str) -> bool:
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme != "https" or not host or parts.username or parts.password:
            return False
        if host.lower() in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
            return False
        if any(ord(c) < 32 for c in url):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return "." in host and not host.endswith(".")
    except ValueError:
        return False


def normalize_hits(hits: list[SearchHit], *, mode: Literal["fixture", "live"],
                   retrieved_at: datetime | None = None) -> ResearchBundle:
    if len(hits) > 30:
        raise ValueError("Too many search hits")
    now = retrieved_at or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Retrieval time must be timezone-aware")
    seen: set[str] = set()
    collected: list[Evidence] = []
    for hit in hits:
        if not isinstance(hit, SearchHit) or hit.source_id in seen or not _safe_reference(hit.url_or_doi):
            raise ValueError("Invalid or duplicate search hit")
        seen.add(hit.source_id)
        collected.append(Evidence(source_id=hit.source_id, source_type=hit.source_type,
                                  title=hit.title, url_or_doi=hit.url_or_doi,
                                  retrieved_at=now, claim_ids=hit.claim_ids,
                                  verification_status="unverified"))
    return ResearchBundle(evidence=tuple(collected), mode=mode, completed=True)
