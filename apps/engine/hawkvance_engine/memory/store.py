"""The memory bucket: storage, hybrid retrieval, consolidation and the user's controls.

Spec sections 14, 15, 16, 29 and 32. Two rules shape everything here:

  1. Workspace memory must not contaminate an unrelated workspace. That is enforced by the query,
     not by hoping the ranking sorts it out.
  2. Relevance beats volume. Global preferences are only injected when they actually score.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from .embeddings import EmbeddingProvider, cosine, tokenise
from .model import (
    ConsolidationDecision,
    Memory,
    MemoryCandidate,
    MemoryScope,
    MemoryTier,
)


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    memory: Memory
    semantic: float
    keyword: float
    importance: float
    score: float

    def as_dict(self) -> dict[str, object]:
        return {
            "memory": self.memory.as_dict(),
            "semantic": round(self.semantic, 4),
            "keyword": round(self.keyword, 4),
            "importance": round(self.importance, 4),
            "score": round(self.score, 4),
        }


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    """What the user is asking, and from where.

    `workspace_id` and `document_id` are not hints. They are the isolation boundary: a memory from
    another workspace is never a candidate, whatever it scores.
    """

    query: str
    workspace_id: str | None = None
    document_id: str | None = None
    limit: int = 12
    include_global: bool = True


class MemoryStore:
    """In-process memory bucket.

    The desktop persists these into the encrypted vault; this class owns the domain behaviour so
    ranking, consolidation and deduplication are testable without a database.
    """

    # Weights for hybrid retrieval, spec section 16.
    SEMANTIC_WEIGHT = 0.45
    KEYWORD_WEIGHT = 0.20
    IMPORTANCE_WEIGHT = 0.25
    SCOPE_WEIGHT = 0.10

    DUPLICATE_SIMILARITY = 0.92

    def __init__(self, embeddings: EmbeddingProvider | None = None) -> None:
        self._embeddings = embeddings or EmbeddingProvider()
        self._memories: dict[str, Memory] = {}
        self._encoder_name = self._embeddings.name

    # ------------------------------------------------------------------ writing

    def remember(self, candidate: MemoryCandidate, now: datetime | None = None) -> Memory | None:
        """Promotes a candidate, merging it into an existing memory when it says the same thing.

        Returns None when the candidate was too weak to keep, which is spec section 71's
        "not every observation becomes memory".
        """
        if candidate.is_discarded:
            return None

        memory = candidate.promote(now)
        memory.embedding = self._embeddings.encode(memory.content)

        existing = self._duplicate_of(memory)
        if existing is not None:
            existing.reinforce(candidate.confidence, now)
            return existing

        self._memories[memory.id] = memory
        return memory

    def add(self, memory: Memory) -> Memory:
        if not memory.embedding:
            memory.embedding = self._embeddings.encode(memory.content)
        self._memories[memory.id] = memory
        return memory

    def _duplicate_of(self, memory: Memory) -> Memory | None:
        """Deduplication is scoped: the same sentence in two workspaces is two memories."""
        for existing in self._memories.values():
            if existing.scope is not memory.scope:
                continue
            if existing.workspace_id != memory.workspace_id:
                continue
            if cosine(existing.embedding, memory.embedding) >= self.DUPLICATE_SIMILARITY:
                return existing
        return None

    # ------------------------------------------------------------------ reading

    def get(self, memory_id: str) -> Memory | None:
        return self._memories.get(memory_id)

    def all(self) -> tuple[Memory, ...]:
        return tuple(self._memories.values())

    def count(self) -> int:
        return len(self._memories)

    def in_scope(self, request: RetrievalRequest) -> list[Memory]:
        """The isolation boundary, applied before any scoring happens."""
        eligible: list[Memory] = []
        for memory in self._memories.values():
            if memory.scope is MemoryScope.GLOBAL:
                if request.include_global:
                    eligible.append(memory)
                continue
            if memory.scope is MemoryScope.FILE:
                if request.document_id is not None and memory.document_id == request.document_id:
                    eligible.append(memory)
                elif request.workspace_id is not None and memory.workspace_id == request.workspace_id:
                    eligible.append(memory)
                continue
            if memory.workspace_id is not None and memory.workspace_id == request.workspace_id:
                eligible.append(memory)
        return eligible

    def retrieve(self, request: RetrievalRequest, now: datetime | None = None) -> list[RetrievalHit]:
        """Hybrid: semantic similarity, keyword overlap, importance, then scope as a tie-breaker."""
        moment = now or datetime.now(timezone.utc)
        candidates = self.in_scope(request)
        if not candidates:
            return []

        self._embeddings.prepare()
        self._reencode_if_encoder_changed()

        query_vector = self._embeddings.encode(request.query)
        query_terms = set(tokenise(request.query))

        hits: list[RetrievalHit] = []
        for memory in candidates:
            semantic = max(0.0, cosine(query_vector, memory.embedding))
            keyword = self._keyword_overlap(query_terms, memory.content)
            relevance = max(semantic, keyword)
            importance = memory.importance(relevance=relevance, now=moment).total
            scope = memory.scope.retrieval_rank / 4.0

            score = (
                semantic * self.SEMANTIC_WEIGHT
                + keyword * self.KEYWORD_WEIGHT
                + importance * self.IMPORTANCE_WEIGHT
                + scope * self.SCOPE_WEIGHT
            ) * memory.tier.retrieval_weight

            hits.append(
                RetrievalHit(
                    memory=memory,
                    semantic=semantic,
                    keyword=keyword,
                    importance=importance,
                    score=score,
                )
            )

        hits.sort(key=lambda hit: hit.score, reverse=True)
        selected = hits[: max(1, request.limit)]
        for hit in selected:
            hit.memory.touch(moment)
        return selected

    @staticmethod
    def _keyword_overlap(query_terms: set[str], content: str) -> float:
        if not query_terms:
            return 0.0
        content_terms = set(tokenise(content))
        if not content_terms:
            return 0.0
        return round(len(query_terms & content_terms) / len(query_terms), 4)

    def _reencode_if_encoder_changed(self) -> None:
        """Vectors from two different encoders are not comparable.

        When the semantic encoder becomes available mid-session, everything encoded by the fallback
        is re-encoded rather than silently compared against incompatible vectors.
        """
        if self._embeddings.name == self._encoder_name:
            return
        for memory in self._memories.values():
            memory.embedding = self._embeddings.encode(memory.content)
        self._encoder_name = self._embeddings.name

    def search(self, text: str, limit: int = 50) -> list[Memory]:
        """The Memory browser's search. Lexical and scope-blind on purpose: the user is looking
        through their own memory, not asking a question."""
        terms = set(tokenise(text))
        if not terms:
            return sorted(
                self._memories.values(), key=lambda memory: memory.created_at, reverse=True
            )[:limit]

        scored = [
            (self._keyword_overlap(terms, memory.content), memory)
            for memory in self._memories.values()
        ]
        matching = [(score, memory) for score, memory in scored if score > 0]
        matching.sort(key=lambda pair: (pair[0], pair[1].created_at), reverse=True)
        return [memory for _, memory in matching[:limit]]

    # ------------------------------------------------------------------ user controls

    def pin(self, memory_id: str, pinned: bool = True) -> bool:
        memory = self._memories.get(memory_id)
        if memory is None:
            return False
        memory.pinned = pinned
        if pinned:
            memory.tier = MemoryTier.HOT
        return True

    def edit(self, memory_id: str, content: str, now: datetime | None = None) -> bool:
        memory = self._memories.get(memory_id)
        if memory is None:
            return False
        memory.content = content
        memory.embedding = self._embeddings.encode(content)
        memory.last_updated_at = now or datetime.now(timezone.utc)
        # A user-edited memory is a stated fact, not an inference.
        memory.confidence = max(memory.confidence, 0.95)
        return True

    def forget(self, memory_id: str) -> bool:
        return self._memories.pop(memory_id, None) is not None

    def forget_workspace(self, workspace_id: str) -> int:
        """Pinned memories are removed too: an explicit "forget this workspace" is the user
        overriding their own earlier pin, not the automatic consolidation pinning protects against.
        """
        doomed = [
            memory.id
            for memory in self._memories.values()
            if memory.workspace_id == workspace_id and memory.scope is not MemoryScope.GLOBAL
        ]
        for memory_id in doomed:
            del self._memories[memory_id]
        return len(doomed)

    def forget_everything(self) -> int:
        removed = len(self._memories)
        self._memories.clear()
        return removed

    def export(self) -> list[dict[str, object]]:
        """Spec section 14: the user can take their memory with them."""
        return [memory.as_dict(include_embedding=False) for memory in self._memories.values()]

    # ------------------------------------------------------------------ consolidation

    def consolidate(self, now: datetime | None = None) -> dict[str, int]:
        """Ages memories between tiers and prunes what stopped earning its place.

        Runs on a schedule, never during retrieval: a user waiting on an answer should not pay for
        housekeeping.
        """
        moment = now or datetime.now(timezone.utc)
        outcome = Counter()

        for memory in list(self._memories.values()):
            decision = memory.consolidation(moment)
            outcome[decision.value] += 1

            if decision is ConsolidationDecision.PRUNE:
                del self._memories[memory.id]
            elif decision in (ConsolidationDecision.DEMOTE, ConsolidationDecision.COMPRESS):
                memory.tier = memory.tier_for(moment)

        return dict(outcome)

    def tier_counts(self) -> dict[str, int]:
        counts = Counter(memory.tier.value for memory in self._memories.values())
        return {tier.value: counts.get(tier.value, 0) for tier in MemoryTier}

    def scope_counts(self) -> dict[str, int]:
        counts = Counter(memory.scope.value for memory in self._memories.values())
        return {scope.value: counts.get(scope.value, 0) for scope in MemoryScope}

    def snapshot(self) -> dict[str, object]:
        return {
            "total": self.count(),
            "byTier": self.tier_counts(),
            "byScope": self.scope_counts(),
            "pinned": sum(1 for memory in self._memories.values() if memory.pinned),
            "embeddings": self._embeddings.snapshot(),
        }
