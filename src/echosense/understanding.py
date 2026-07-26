from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from echosense.cognitive_memory import CognitiveMemoryStore, RetrievedMemory


def clamp(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 6)


@dataclass(frozen=True)
class ObservationEvidence:
    key: str
    value: str
    confidence: float


@dataclass(frozen=True)
class MemoryEvidence:
    memory_id: str
    memory_type: str
    subject: str
    predicate: str
    object: str
    context: str
    confidence: float
    relevance_score: float


@dataclass(frozen=True)
class InferenceEvidence:
    claim: str
    confidence: float
    observation_keys: tuple[str, ...]
    memory_ids: tuple[str, ...]


@dataclass(frozen=True)
class ActionEvidence:
    action_type: str
    target_ref: str
    confidence: float


@dataclass(frozen=True)
class UnderstandingResult:
    observations: tuple[ObservationEvidence, ...]
    memories: tuple[MemoryEvidence, ...]
    inferences: tuple[InferenceEvidence, ...]
    action: ActionEvidence

    def as_trace_factor(self) -> dict[str, object]:
        return {
            "observations": [asdict(item) for item in self.observations],
            "memories": [asdict(item) for item in self.memories],
            "inferences": [
                {
                    **asdict(item),
                    "observation_keys": list(item.observation_keys),
                    "memory_ids": list(item.memory_ids),
                }
                for item in self.inferences
            ],
            "action": asdict(self.action),
        }


class UnderstandingEngine:
    """Builds deterministic, provider-neutral evidence for a selected action."""

    def __init__(self, memory_store: CognitiveMemoryStore, retrieval_limit: int = 5) -> None:
        if not 1 <= retrieval_limit <= 20:
            raise ValueError("retrieval_limit must be between 1 and 20")
        self.memory_store = memory_store
        self.retrieval_limit = retrieval_limit

    def understand(
        self,
        *,
        user_id: str,
        context: str,
        context_confidence: float,
        observations: Iterable[ObservationEvidence],
        action_type: str,
        target_ref: str,
    ) -> UnderstandingResult:
        normalized = tuple(
            sorted(
                (
                    ObservationEvidence(item.key, item.value, clamp(item.confidence))
                    for item in observations
                ),
                key=lambda item: item.key,
            )
        )
        query = " ".join(
            [context]
            + [f"{item.key} {item.value}" for item in normalized]
        )
        retrieved = self.memory_store.retrieve(
            user_id=user_id,
            query=query,
            context=context,
            limit=self.retrieval_limit,
        )
        memories = tuple(self._memory_evidence(item) for item in retrieved)

        observation_confidence = (
            sum(item.confidence for item in normalized) / len(normalized) if normalized else 0.0
        )
        strongest_memory = max(memories, key=lambda item: item.relevance_score, default=None)
        memory_confidence = strongest_memory.confidence if strongest_memory else 0.0
        relevance = strongest_memory.relevance_score if strongest_memory else 0.0
        inference_confidence = clamp(
            0.60 * observation_confidence + 0.25 * memory_confidence + 0.15 * relevance
        )
        memory_ids = tuple(item.memory_id for item in memories)
        inference = InferenceEvidence(
            claim=f"context:{context}",
            confidence=inference_confidence,
            observation_keys=tuple(item.key for item in normalized),
            memory_ids=memory_ids,
        )
        action_confidence = clamp(min(clamp(context_confidence), inference_confidence))
        return UnderstandingResult(
            observations=normalized,
            memories=memories,
            inferences=(inference,),
            action=ActionEvidence(
                action_type=action_type,
                target_ref=target_ref,
                confidence=action_confidence,
            ),
        )

    @staticmethod
    def _memory_evidence(item: RetrievedMemory) -> MemoryEvidence:
        memory = item.memory
        return MemoryEvidence(
            memory_id=memory.memory_id,
            memory_type=memory.memory_type,
            subject=memory.subject,
            predicate=memory.predicate,
            object=memory.object,
            context=memory.context,
            confidence=clamp(memory.confidence),
            relevance_score=clamp(item.relevance_score),
        )
