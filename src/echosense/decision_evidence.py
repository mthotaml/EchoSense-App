from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from echosense.storage import Storage
from echosense.understanding import ObservationEvidence, UnderstandingEngine, UnderstandingResult


@dataclass(frozen=True)
class DecisionAction:
    provider: str
    item_id: str
    action_type: str = "recommend"

    @property
    def target_ref(self) -> str:
        return f"{self.provider}:{self.item_id}"


class DecisionEvidenceService:
    """Builds and persists auditable understanding evidence in a decision trace."""

    def __init__(self, storage: Storage, understanding: UnderstandingEngine) -> None:
        self.storage = storage
        self.understanding = understanding

    def record(
        self,
        *,
        decision_id: str,
        user_id: str,
        context: str,
        context_confidence: float,
        observations: Iterable[ObservationEvidence],
        action: DecisionAction,
        factors: dict[str, object] | None = None,
    ) -> UnderstandingResult:
        result = self.understanding.understand(
            user_id=user_id,
            context=context,
            context_confidence=context_confidence,
            observations=observations,
            action_type=action.action_type,
            target_ref=action.target_ref,
        )
        trace_factors = dict(factors or {})
        trace_factors["understanding"] = result.as_trace_factor()
        self.storage.save_decision_trace(
            decision_id=decision_id,
            user_id=user_id,
            context=context,
            context_confidence=context_confidence,
            provider=action.provider,
            item_id=action.item_id,
            factors=trace_factors,
        )
        return result
