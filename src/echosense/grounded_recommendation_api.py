from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from echosense.app import (
    get_exposure_store,
    get_music_provider,
    get_storage,
    infer_context,
    rank_candidates,
)
from echosense.cognitive_memory import CognitiveMemoryStore
from echosense.grounded_decision import GroundedDecisionService, SelectedAction
from echosense.understanding import ObservationEvidence, UnderstandingEngine

app = FastAPI(title="EchoSense Grounded Recommendations", version="0.22.0")
MEMORY_PURPOSE = "cognitive_memory"


class Signal(BaseModel):
    type: Literal["time", "weather", "activity", "location"]
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    purpose_id: str


class RecommendationRequest(BaseModel):
    user_id: str
    signals: list[Signal]


class RecommendationResponse(BaseModel):
    decision_id: str
    context: str
    context_confidence: float
    decision_confidence: float
    provider: str
    item_id: str
    explanation: str
    cited_memory_ids: list[str]
    generated_at: datetime


class _ObservationOnlyMemory:
    def retrieve(self, **_: object) -> list[object]:
        return []


def _decision_service(user_id: str) -> GroundedDecisionService:
    store = get_storage()
    memory = (
        CognitiveMemoryStore(store)
        if store.has_active_consent(user_id, MEMORY_PURPOSE)
        else _ObservationOnlyMemory()
    )
    return GroundedDecisionService(store, UnderstandingEngine(memory))  # type: ignore[arg-type]


@app.post("/v1/recommendations", response_model=RecommendationResponse)
def recommend(request: RecommendationRequest) -> RecommendationResponse:
    store = get_storage()
    missing = sorted(
        {
            signal.purpose_id
            for signal in request.signals
            if not store.has_active_consent(request.user_id, signal.purpose_id)
        }
    )
    if missing:
        raise HTTPException(
            status_code=403,
            detail={"code": "consent_required", "missing_purposes": missing},
        )

    context, context_confidence, signal_factors = infer_context(request.signals)  # type: ignore[arg-type]
    decision_id = f"dec_{uuid4().hex}"
    try:
        candidates = get_music_provider().candidates_for_context(context, request.user_id, limit=5)
        candidate, preference_weight, ranking_score, candidate_slate, policy = rank_candidates(
            user_id=request.user_id,
            context=context,
            decision_id=decision_id,
            candidates=candidates,
        )
    except (httpx.HTTPError, LookupError, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "recommendation_unavailable", "message": str(exc)},
        ) from exc

    factors: dict[str, object] = {
        **signal_factors,
        "candidate_count": len(candidates),
        "provider_base_score": candidate.base_score,
        "preference_weight": preference_weight,
        "ranking_score": ranking_score,
        "ranking_policy": policy,
        "candidate_slate": candidate_slate,
        "memory_consent": store.has_active_consent(request.user_id, MEMORY_PURPOSE),
    }
    grounded = _decision_service(request.user_id).finalize(
        decision_id=decision_id,
        user_id=request.user_id,
        context=context,
        context_confidence=context_confidence,
        observations=(
            ObservationEvidence(signal.type, signal.value.lower(), signal.confidence)
            for signal in request.signals
        ),
        action=SelectedAction(candidate.provider, candidate.item_id, candidate.rationale),
        factors=factors,
        explored=bool(policy["explored"]),
        preference_applied=abs(preference_weight) >= 0.001,
    )
    get_exposure_store().record_selection(request.user_id, candidate.provider, candidate.item_id)
    store.append_event(
        event_id=f"evt_{uuid4().hex}",
        event_type="recommendation.grounded",
        user_id=request.user_id,
        trace_id=f"trc_{uuid4().hex}",
        payload={
            "decision_id": decision_id,
            "context": context,
            "provider": candidate.provider,
            "item_id": candidate.item_id,
            "decision_confidence": grounded.explanation.confidence,
            "memory_ids": list(grounded.explanation.memory_ids),
        },
    )
    return RecommendationResponse(
        decision_id=decision_id,
        context=context,
        context_confidence=context_confidence,
        decision_confidence=grounded.explanation.confidence,
        provider=candidate.provider,
        item_id=candidate.item_id,
        explanation=grounded.explanation.text,
        cited_memory_ids=list(grounded.explanation.memory_ids),
        generated_at=datetime.now(timezone.utc),
    )
