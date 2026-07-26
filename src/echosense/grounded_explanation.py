from __future__ import annotations

from dataclasses import dataclass

from echosense.understanding import UnderstandingResult


@dataclass(frozen=True)
class GroundedExplanation:
    text: str
    confidence: float
    memory_ids: tuple[str, ...]
    observation_keys: tuple[str, ...]


class GroundedExplanationBuilder:
    """Produces concise explanations derived only from persisted decision evidence."""

    def build(
        self,
        *,
        rationale: str,
        context: str,
        understanding: UnderstandingResult,
        explored: bool = False,
        preference_applied: bool = False,
    ) -> GroundedExplanation:
        inference = understanding.inferences[0] if understanding.inferences else None
        memory_ids = inference.memory_ids if inference else ()
        observation_keys = inference.observation_keys if inference else ()
        confidence = understanding.action.confidence

        evidence_parts: list[str] = []
        if observation_keys:
            evidence_parts.append(
                "current " + ", ".join(key.replace("_", " ") for key in observation_keys)
            )
        if memory_ids:
            evidence_parts.append(
                f"{len(memory_ids)} relevant remembered fact"
                + ("s" if len(memory_ids) != 1 else "")
            )
        if preference_applied:
            evidence_parts.append("learned preference")
        if explored:
            evidence_parts.append("controlled exploration")

        evidence = ", ".join(evidence_parts) if evidence_parts else "the available evidence"
        text = (
            f"We selected {rationale} for {context.replace('_', ' ')} based on {evidence}. "
            f"Decision confidence is {confidence:.2f}."
        )
        return GroundedExplanation(
            text=text,
            confidence=confidence,
            memory_ids=memory_ids,
            observation_keys=observation_keys,
        )
