from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RankingPolicy:
    novelty_weight: float = 0.05
    exploration_rate: float = 0.05
    exploration_pool: int = 3

    def __post_init__(self) -> None:
        if not 0.0 <= self.novelty_weight <= 0.25:
            raise ValueError("novelty_weight must be between 0 and 0.25")
        if not 0.0 <= self.exploration_rate <= 0.2:
            raise ValueError("exploration_rate must be between 0 and 0.2")
        if self.exploration_pool < 1:
            raise ValueError("exploration_pool must be positive")


@dataclass(frozen=True)
class PolicyCandidate:
    provider: str
    item_id: str
    base_score: float
    preference_weight: float
    exposure_count: int = 0
    group: str | None = None


@dataclass(frozen=True)
class RankedCandidate:
    provider: str
    item_id: str
    base_score: float
    preference_weight: float
    novelty_score: float
    policy_score: float
    rank: int
    selected: bool
    explored: bool
    group: str


def _novelty(exposure_count: int) -> float:
    if exposure_count < 0:
        raise ValueError("exposure_count cannot be negative")
    return round(1.0 / (1.0 + exposure_count), 6)


def rank_with_policy(
    candidates: Iterable[PolicyCandidate],
    *,
    preference_influence: float,
    policy: RankingPolicy,
    seed_material: str,
) -> list[RankedCandidate]:
    if not 0.0 <= preference_influence <= 0.5:
        raise ValueError("preference_influence must be between 0 and 0.5")
    source = list(candidates)
    if not source:
        raise ValueError("candidate slate cannot be empty")

    scored = []
    for candidate in source:
        novelty = _novelty(candidate.exposure_count)
        score = candidate.base_score + preference_influence * candidate.preference_weight
        score += policy.novelty_weight * novelty
        scored.append((candidate, novelty, round(score, 6)))
    scored.sort(key=lambda item: (item[2], item[0].base_score, item[0].item_id), reverse=True)

    digest = hashlib.sha256(seed_material.encode()).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    explored = rng.random() < policy.exploration_rate and len(scored) > 1
    selected_index = 0
    if explored:
        selected_index = rng.randrange(min(policy.exploration_pool, len(scored)))
        scored[0], scored[selected_index] = scored[selected_index], scored[0]

    result = []
    for rank, (candidate, novelty, score) in enumerate(scored, start=1):
        group = candidate.group or candidate.provider
        result.append(
            RankedCandidate(
                provider=candidate.provider,
                item_id=candidate.item_id,
                base_score=candidate.base_score,
                preference_weight=candidate.preference_weight,
                novelty_score=novelty,
                policy_score=score,
                rank=rank,
                selected=rank == 1,
                explored=explored and rank == 1,
                group=group,
            )
        )
    return result


def diversify(ranked: Iterable[RankedCandidate], *, limit: int, max_per_group: int = 1) -> list[RankedCandidate]:
    if limit < 1 or max_per_group < 1:
        raise ValueError("limit and max_per_group must be positive")
    result: list[RankedCandidate] = []
    counts: dict[str, int] = {}
    deferred: list[RankedCandidate] = []
    for candidate in ranked:
        if counts.get(candidate.group, 0) < max_per_group:
            result.append(candidate)
            counts[candidate.group] = counts.get(candidate.group, 0) + 1
        else:
            deferred.append(candidate)
        if len(result) == limit:
            return result
    for candidate in deferred:
        result.append(candidate)
        if len(result) == limit:
            break
    return result
