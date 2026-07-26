from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

OUTCOME_REWARDS: dict[str, float] = {
    "completed": 0.7,
    "liked": 1.0,
    "skipped": -0.3,
    "disliked": -1.0,
}


@dataclass(frozen=True)
class AttributedOutcome:
    outcome_id: str
    decision_id: str
    outcome: str
    reward: float
    observed_at: datetime
    playback_seconds: float | None = None
    completion_ratio: float | None = None
    attribution_window_seconds: int = 3600


@dataclass(frozen=True)
class CandidateSnapshot:
    provider: str
    item_id: str
    rank: int
    provider_base_score: float
    preference_weight: float
    ranking_score: float
    selected: bool


@dataclass(frozen=True)
class CounterfactualCandidate:
    provider: str
    item_id: str
    rank: int
    estimated_reward: float
    estimated_lift: float


@dataclass(frozen=True)
class CounterfactualReport:
    decision_id: str
    outcome_id: str
    observed_reward: float
    selected_item_id: str
    best_alternative: CounterfactualCandidate | None
    estimated_regret: float
    confidence: str
    evaluated_at: datetime


def normalize_reward(
    outcome: str,
    *,
    playback_seconds: float | None = None,
    completion_ratio: float | None = None,
) -> float:
    if outcome not in OUTCOME_REWARDS:
        raise ValueError(f"Unsupported outcome: {outcome}")
    reward = OUTCOME_REWARDS[outcome]
    if completion_ratio is not None:
        if not 0.0 <= completion_ratio <= 1.0:
            raise ValueError("completion_ratio must be between 0 and 1")
        if outcome == "completed":
            reward = max(reward, completion_ratio)
        elif outcome == "skipped":
            reward = min(0.0, reward + 0.3 * completion_ratio)
    if playback_seconds is not None and playback_seconds < 0:
        raise ValueError("playback_seconds cannot be negative")
    return round(max(-1.0, min(1.0, reward)), 6)


def snapshot_candidates(
    candidates: Iterable[dict[str, Any]], selected_item_id: str
) -> list[CandidateSnapshot]:
    snapshots: list[CandidateSnapshot] = []
    for index, candidate in enumerate(candidates, start=1):
        snapshots.append(
            CandidateSnapshot(
                provider=str(candidate["provider"]),
                item_id=str(candidate["item_id"]),
                rank=int(candidate.get("rank", index)),
                provider_base_score=float(candidate["provider_base_score"]),
                preference_weight=float(candidate.get("preference_weight", 0.0)),
                ranking_score=float(candidate["ranking_score"]),
                selected=str(candidate["item_id"]) == selected_item_id,
            )
        )
    if not snapshots:
        raise ValueError("candidate slate cannot be empty")
    if sum(snapshot.selected for snapshot in snapshots) != 1:
        raise ValueError("candidate slate must contain exactly one selected item")
    return snapshots


def evaluate_counterfactual(
    *,
    decision_id: str,
    outcome: AttributedOutcome,
    candidates: Iterable[CandidateSnapshot],
) -> CounterfactualReport:
    slate = list(candidates)
    selected = next((candidate for candidate in slate if candidate.selected), None)
    if selected is None:
        raise ValueError("selected candidate missing from slate")

    alternatives = [candidate for candidate in slate if not candidate.selected]
    best: CounterfactualCandidate | None = None
    if alternatives:
        strongest = max(
            alternatives, key=lambda candidate: (candidate.ranking_score, -candidate.rank)
        )
        score_gap = strongest.ranking_score - selected.ranking_score
        estimated_reward = max(-1.0, min(1.0, outcome.reward + score_gap))
        best = CounterfactualCandidate(
            provider=strongest.provider,
            item_id=strongest.item_id,
            rank=strongest.rank,
            estimated_reward=round(estimated_reward, 6),
            estimated_lift=round(estimated_reward - outcome.reward, 6),
        )

    regret = max(0.0, best.estimated_lift) if best else 0.0
    confidence = "low"
    if len(slate) >= 3 and outcome.completion_ratio is not None:
        confidence = "medium"
    if (
        len(slate) >= 5
        and outcome.completion_ratio is not None
        and outcome.playback_seconds is not None
    ):
        confidence = "high"

    return CounterfactualReport(
        decision_id=decision_id,
        outcome_id=outcome.outcome_id,
        observed_reward=outcome.reward,
        selected_item_id=selected.item_id,
        best_alternative=best,
        estimated_regret=round(regret, 6),
        confidence=confidence,
        evaluated_at=datetime.now(timezone.utc),
    )
