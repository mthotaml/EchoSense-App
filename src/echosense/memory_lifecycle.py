from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from echosense.cognitive_memory import MemoryRecord


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalized(value: str) -> str:
    return " ".join(value.lower().split())


@dataclass(frozen=True)
class ConsolidationCandidate:
    consolidation_key: str
    user_id: str
    subject: str
    predicate: str
    object: str
    context: str
    source_memory_ids: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class ForgettingCandidate:
    memory_id: str
    reason: str


@dataclass(frozen=True)
class LifecyclePlan:
    consolidations: tuple[ConsolidationCandidate, ...]
    forgetting: tuple[ForgettingCandidate, ...]
    protected_memory_ids: tuple[str, ...]


@dataclass(frozen=True)
class LifecyclePolicy:
    minimum_sources: int = 3
    minimum_average_confidence: float = 0.60
    forgetting_confidence: float = 0.35
    retention_days: int = 90

    def __post_init__(self) -> None:
        if self.minimum_sources < 2:
            raise ValueError("minimum_sources must be at least 2")
        if not 0.0 <= self.minimum_average_confidence <= 1.0:
            raise ValueError("minimum_average_confidence must be bounded")
        if not 0.0 <= self.forgetting_confidence <= 1.0:
            raise ValueError("forgetting_confidence must be bounded")
        if self.retention_days < 1:
            raise ValueError("retention_days must be positive")


class MemoryLifecyclePlanner:
    def __init__(self, policy: LifecyclePolicy | None = None) -> None:
        self.policy = policy or LifecyclePolicy()

    def plan(
        self,
        memories: Iterable[MemoryRecord],
        *,
        now: datetime | None = None,
        protected_memory_ids: Iterable[str] = (),
    ) -> LifecyclePlan:
        instant = now or utc_now()
        memory_list = sorted(memories, key=lambda item: item.memory_id)
        protected = set(protected_memory_ids)
        protected.update(
            memory.memory_id
            for memory in memory_list
            if memory.status == "active"
            and (
                memory.confidence >= self.policy.forgetting_confidence
                or instant - memory.created_at < timedelta(days=self.policy.retention_days)
            )
        )

        groups: dict[tuple[str, str, str, str, str], list[MemoryRecord]] = {}
        for memory in memory_list:
            if memory.memory_type != "episodic" or memory.status != "active":
                continue
            if memory.expires_at is not None and memory.expires_at <= instant:
                continue
            key = (
                memory.user_id,
                _normalized(memory.subject),
                _normalized(memory.predicate),
                _normalized(memory.object),
                _normalized(memory.context),
            )
            groups.setdefault(key, []).append(memory)

        consolidations: list[ConsolidationCandidate] = []
        for key, sources in sorted(groups.items()):
            provenance = {source.provenance_ref for source in sources}
            average = sum(source.confidence for source in sources) / len(sources)
            if len(sources) < self.policy.minimum_sources:
                continue
            if len(provenance) < self.policy.minimum_sources:
                continue
            if average < self.policy.minimum_average_confidence:
                continue
            source_ids = tuple(sorted(source.memory_id for source in sources))
            digest = hashlib.sha256("|".join(source_ids).encode()).hexdigest()[:24]
            confidence = round(min(0.95, average + 0.05 * math.log2(len(sources))), 6)
            sample = sources[0]
            consolidations.append(
                ConsolidationCandidate(
                    consolidation_key=f"con_{digest}",
                    user_id=key[0],
                    subject=sample.subject,
                    predicate=sample.predicate,
                    object=sample.object,
                    context=sample.context,
                    source_memory_ids=source_ids,
                    confidence=confidence,
                )
            )
            protected.update(source_ids)

        forgetting: list[ForgettingCandidate] = []
        cutoff = instant - timedelta(days=self.policy.retention_days)
        for memory in memory_list:
            if memory.memory_id in protected or memory.memory_type == "working":
                continue
            old = max(memory.observed_at, memory.created_at) <= cutoff
            weak_or_inactive = (
                memory.status != "active"
                or memory.confidence < self.policy.forgetting_confidence
            )
            if old and weak_or_inactive:
                reason = "inactive_and_stale" if memory.status != "active" else "weak_and_stale"
                forgetting.append(ForgettingCandidate(memory.memory_id, reason))

        return LifecyclePlan(
            consolidations=tuple(consolidations),
            forgetting=tuple(forgetting),
            protected_memory_ids=tuple(sorted(protected)),
        )
