"""The memory domain: scope, tier, importance and confidence.

Spec sections 9 to 16 and 24 to 28. The distinction that matters most here is the one between
*importance* (how much this matters) and *confidence* (how sure we are it is true). Conflating them
is how a confidently-wrong inference gets promoted to global memory and then repeated forever.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


class MemoryScope(str, Enum):
    """Where a memory belongs. Workspace memory never leaks into an unrelated workspace."""

    FILE = "file"
    WORKSPACE = "workspace"
    CONVERSATION = "conversation"
    GLOBAL = "global"

    @property
    def retrieval_rank(self) -> int:
        """Spec section 32: current file, then workspace, then related, then global.

        Relevance always beats volume, so this is a tie-breaker applied after semantic scoring,
        never a substitute for it.
        """
        return {
            MemoryScope.FILE: 4,
            MemoryScope.CONVERSATION: 3,
            MemoryScope.WORKSPACE: 2,
            MemoryScope.GLOBAL: 1,
        }[self]


class MemoryTier(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"

    @property
    def retrieval_weight(self) -> float:
        return {MemoryTier.HOT: 1.0, MemoryTier.WARM: 0.8, MemoryTier.COLD: 0.6}[self]


class ConsolidationDecision(str, Enum):
    KEEP = "keep"
    DEMOTE = "demote"
    COMPRESS = "compress"
    PRUNE = "prune"


HOT_DAYS = 15
WARM_DAYS = 180


@dataclass(frozen=True, slots=True)
class ImportanceScore:
    """Spec section 13, decomposed so a user can be shown *why* something was kept.

    A single opaque number is impossible to argue with; a breakdown is reviewable, which matters
    because the user is allowed to disagree and pin or delete.
    """

    recency: float
    relevance: float
    frequency: float
    interaction: float
    explicit: float
    project: float

    WEIGHTS = {
        "recency": 0.20,
        "relevance": 0.25,
        "frequency": 0.15,
        "interaction": 0.15,
        "explicit": 0.15,
        "project": 0.10,
    }

    @property
    def total(self) -> float:
        return round(
            min(
                1.0,
                self.recency * self.WEIGHTS["recency"]
                + self.relevance * self.WEIGHTS["relevance"]
                + self.frequency * self.WEIGHTS["frequency"]
                + self.interaction * self.WEIGHTS["interaction"]
                + self.explicit * self.WEIGHTS["explicit"]
                + self.project * self.WEIGHTS["project"],
            ),
            4,
        )

    @property
    def percent(self) -> int:
        return round(self.total * 100)

    def as_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "percent": self.percent,
            "recency": self.recency,
            "relevance": self.relevance,
            "frequency": self.frequency,
            "interaction": self.interaction,
            "explicit": self.explicit,
            "project": self.project,
        }

    @staticmethod
    def decay(age_days: float, half_life_days: float = 30.0) -> float:
        """Exponential decay, so a memory fades rather than falling off a cliff on day 16."""
        return round(math.pow(0.5, max(0.0, age_days) / half_life_days), 4)


@dataclass(slots=True)
class Memory:
    """One durable thing HawkVance knows.

    `content` is already sanitised: a memory is derived from redacted text, so a memory can never
    reintroduce a value the privacy pipeline removed.
    """

    content: str
    scope: MemoryScope
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    workspace_id: str | None = None
    document_id: str | None = None
    source: str = ""
    confidence: float = 0.5
    observation_count: int = 1
    access_count: int = 0
    pinned: bool = False
    tier: MemoryTier = MemoryTier.HOT
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    retention_days: int | None = None
    embedding: tuple[float, ...] = ()
    explicit_importance: float = 0.0

    def __post_init__(self) -> None:
        if self.scope is MemoryScope.WORKSPACE and self.workspace_id is None:
            raise ValueError("A workspace memory must name the workspace it belongs to.")
        if self.scope is MemoryScope.FILE and self.document_id is None:
            raise ValueError("A file memory must name the document it came from.")

    def age_days(self, now: datetime | None = None) -> float:
        moment = now or datetime.now(timezone.utc)
        return max(0.0, (moment - self.created_at).total_seconds() / 86400.0)

    def idle_days(self, now: datetime | None = None) -> float:
        moment = now or datetime.now(timezone.utc)
        return max(0.0, (moment - self.last_accessed_at).total_seconds() / 86400.0)

    def importance(self, relevance: float = 0.0, now: datetime | None = None) -> ImportanceScore:
        moment = now or datetime.now(timezone.utc)
        return ImportanceScore(
            recency=ImportanceScore.decay(self.age_days(moment)),
            relevance=round(min(1.0, max(0.0, relevance)), 4),
            frequency=round(min(1.0, self.observation_count / 10.0), 4),
            interaction=round(min(1.0, self.access_count / 20.0), 4),
            explicit=1.0 if self.pinned else round(min(1.0, self.explicit_importance), 4),
            project=1.0 if self.scope is not MemoryScope.GLOBAL else 0.4,
        )

    def touch(self, now: datetime | None = None) -> None:
        self.access_count += 1
        self.last_accessed_at = now or datetime.now(timezone.utc)

    def reinforce(self, confidence: float, now: datetime | None = None) -> None:
        """A repeated observation raises confidence without ever reaching certainty.

        Capped below 1.0 deliberately: an inference is never a fact, and a memory that claims
        certainty is one a user cannot reasonably be asked to review.
        """
        self.observation_count += 1
        self.confidence = round(min(0.98, max(self.confidence, confidence) + 0.05), 4)
        self.last_updated_at = now or datetime.now(timezone.utc)

    def tier_for(self, now: datetime | None = None) -> MemoryTier:
        if self.pinned:
            return MemoryTier.HOT
        age = self.age_days(now)
        if age <= HOT_DAYS:
            return MemoryTier.HOT
        if age <= WARM_DAYS:
            return MemoryTier.WARM
        return MemoryTier.COLD

    def consolidation(self, now: datetime | None = None) -> ConsolidationDecision:
        """Spec section 15. Pinned memories are never automatically compressed or deleted."""
        if self.pinned:
            return ConsolidationDecision.KEEP

        moment = now or datetime.now(timezone.utc)
        if self.retention_days is not None and self.age_days(moment) > self.retention_days:
            return ConsolidationDecision.PRUNE

        target = self.tier_for(moment)
        score = self.importance(now=moment).total

        if target is MemoryTier.COLD:
            return (
                ConsolidationDecision.PRUNE if score < 0.15 else ConsolidationDecision.COMPRESS
            )
        if target is MemoryTier.WARM and self.tier is MemoryTier.HOT:
            return (
                ConsolidationDecision.PRUNE if score < 0.10 else ConsolidationDecision.DEMOTE
            )
        return ConsolidationDecision.KEEP

    def as_dict(self, include_embedding: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "content": self.content,
            "scope": self.scope.value,
            "workspaceId": self.workspace_id,
            "documentId": self.document_id,
            "source": self.source,
            "confidence": self.confidence,
            "observationCount": self.observation_count,
            "accessCount": self.access_count,
            "pinned": self.pinned,
            "tier": self.tier.value,
            "createdAt": self.created_at.isoformat(),
            "lastAccessedAt": self.last_accessed_at.isoformat(),
            "lastUpdatedAt": self.last_updated_at.isoformat(),
            "retentionDays": self.retention_days,
            "importance": self.importance().as_dict(),
        }
        if include_embedding:
            payload["embedding"] = list(self.embedding)
        return payload


@dataclass(slots=True)
class MemoryCandidate:
    """An observation that has not yet earned permanence.

    Spec section 71: nothing an AI says becomes memory automatically. A candidate carries its own
    confidence and only crosses into `Memory` when it clears the bar or the user confirms it.
    """

    content: str
    scope: MemoryScope
    confidence: float
    source: str
    workspace_id: str | None = None
    document_id: str | None = None

    AUTO_ACCEPT_ABOVE = 0.80
    NEEDS_CONFIRMATION_ABOVE = 0.50

    @property
    def is_automatic(self) -> bool:
        return self.confidence > self.AUTO_ACCEPT_ABOVE

    @property
    def needs_confirmation(self) -> bool:
        return self.NEEDS_CONFIRMATION_ABOVE <= self.confidence <= self.AUTO_ACCEPT_ABOVE

    @property
    def is_discarded(self) -> bool:
        return self.confidence < self.NEEDS_CONFIRMATION_ABOVE

    def promote(self, now: datetime | None = None) -> Memory:
        moment = now or datetime.now(timezone.utc)
        return Memory(
            content=self.content,
            scope=self.scope,
            workspace_id=self.workspace_id,
            document_id=self.document_id,
            source=self.source,
            confidence=self.confidence,
            created_at=moment,
            last_accessed_at=moment,
            last_updated_at=moment,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "content": self.content,
            "scope": self.scope.value,
            "confidence": self.confidence,
            "source": self.source,
            "workspaceId": self.workspace_id,
            "documentId": self.document_id,
            "isAutomatic": self.is_automatic,
            "needsConfirmation": self.needs_confirmation,
        }


def hot_cutoff(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)) - timedelta(days=HOT_DAYS)
