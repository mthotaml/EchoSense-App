from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from echosense.grounded_explanation import GroundedExplanation, GroundedExplanationBuilder
from echosense.storage import Storage
from echosense.understanding import ObservationEvidence, UnderstandingEngine, UnderstandingResult


@dataclass(frozen=True)
class SelectedAction:
    provider: str
    item_id: str
    rationale: str
    action_type: str = "recommend"

    @property
    def target_ref(self) -> str:
        return f"{self.provider}:{self.item_id}"


@dataclass(frozen=True)
class GroundedDecision:
    understanding: UnderstandingResult
    explanation: GroundedExplanation


class GroundedDecisionService:
    """Finalizes a selected action with evidence, explanation, and durable trace data."""

    def __init__(
        self,
        storage: Storage,
        understanding: UnderstandingEngine,
        explanations: GroundedExplanationBuilder | None = None,
    ) -> None:
        self.storage = storage
        self.understanding = understanding
        self.explanations = explanations or GroundedExplanationBuilder()

    def finalize(
        self,
        *,
        decision_id: str,
        user_id: str,
        context: str,
        context_confidence: float,
        observations: Iterable[ObservationEvidence],
        action: SelectedAction,
        factors: dict[str, object] | None = None,
        explored: bool = False,
        preference_applied: bool = False,
    ) -> GroundedDecision:
        understanding = self.understanding.understand(
            user_id=user_id,
            context=context,
            context_confidence=context_confidence,
            observations=observations,
            action_type=action.action_type,
            target_ref=action.target_ref,
        )
        explanation = self.explanations.build(
            rationale=action.rationale,
            context=context,
            understanding=understanding,
            explored=explored,
            preference_applied=preference_applied,
        )
        trace_factors = dict(factors or {})
        trace_factors["understanding"] = understanding.as_trace_factor()
        trace_factors["grounded_explanation"] = {
            "text": explanation.text,
            "confidence": explanation.confidence,
            "memory_ids": list(explanation.memory_ids),
            "observation_keys": list(explanation.observation_keys),
        }
        self.storage.save_decision_trace(
            decision_id=decision_id,
            user_id=user_id,
            context=context,
            context_confidence=context_confidence,
            provider=action.provider,
            item_id=action.item_id,
            factors=trace_factors,
        )
        return GroundedDecision(understanding=understanding, explanation=explanation)
