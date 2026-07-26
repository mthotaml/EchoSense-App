from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from echosense.app import get_music_provider, get_storage, rank_candidates
from echosense.taste_profile import TasteProfileBuilder

router = APIRouter(prefix="/v1/users/{user_id}", tags=["profile-recommendations"])


class ProfileRecommendationResponse(BaseModel):
    decision_id: str
    context: str
    provider: str
    item_id: str
    taste_confidence: float
    discovery_ratio: float
    top_artist: str | None
    explanation: str
    generated_at: datetime


@router.get("/recommendations/profile-aware", response_model=ProfileRecommendationResponse)
def profile_aware_recommendation(
    user_id: str,
    context: str = Query(default="general_listening", min_length=1, max_length=80),
) -> ProfileRecommendationResponse:
    profile = TasteProfileBuilder(get_storage()).build(user_id)
    if profile.status != "ready":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "taste_profile_required",
                "message": "Sync a music provider before requesting a profile-aware recommendation.",
            },
        )

    decision_id = f"dec_{uuid4().hex}"
    top_artist = profile.top_artists[0].name if profile.top_artists else None
    try:
        candidates = get_music_provider().candidates_for_context(context, user_id, limit=5)
        candidate, preference_weight, ranking_score, candidate_slate, policy_factors = (
            rank_candidates(
                user_id=user_id,
                context=context,
                decision_id=decision_id,
                candidates=candidates,
            )
        )
    except (httpx.HTTPError, LookupError, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "provider_unavailable", "message": str(exc)},
        ) from exc

    profile_phrase = (
        f" your current affinity for {top_artist}" if top_artist else " your current taste profile"
    )
    discovery_phrase = (
        "with more room for discovery"
        if profile.discovery_ratio >= 0.5
        else "while staying close to familiar listening patterns"
    )
    explanation = (
        f"Selected {candidate.rationale} using{profile_phrase}, {discovery_phrase}, "
        f"and the {context.replace('_', ' ')} context."
    )

    factors: dict[str, object] = {
        "taste_profile": {
            "confidence": profile.confidence,
            "evidence_count": profile.evidence_count,
            "discovery_ratio": profile.discovery_ratio,
            "top_artist": top_artist,
            "top_artists": [item.model_dump() for item in profile.top_artists],
            "top_albums": [item.model_dump() for item in profile.top_albums],
        },
        "candidate_count": len(candidates),
        "provider_base_score": candidate.base_score,
        "preference_weight": preference_weight,
        "ranking_score": ranking_score,
        "ranking_policy": policy_factors,
        "candidate_slate": candidate_slate,
    }
    store = get_storage()
    store.save_decision_trace(
        decision_id=decision_id,
        user_id=user_id,
        context=context,
        context_confidence=profile.confidence,
        provider=candidate.provider,
        item_id=candidate.item_id,
        factors=factors,
    )
    store.append_event(
        event_id=f"evt_{uuid4().hex}",
        event_type="recommendation.profile_aware.ranked",
        user_id=user_id,
        trace_id=f"trc_{uuid4().hex}",
        payload={
            "decision_id": decision_id,
            "context": context,
            "provider": candidate.provider,
            "item_id": candidate.item_id,
            "taste_confidence": profile.confidence,
            "discovery_ratio": profile.discovery_ratio,
            "top_artist": top_artist,
        },
    )

    return ProfileRecommendationResponse(
        decision_id=decision_id,
        context=context,
        provider=candidate.provider,
        item_id=candidate.item_id,
        taste_confidence=profile.confidence,
        discovery_ratio=profile.discovery_ratio,
        top_artist=top_artist,
        explanation=explanation,
        generated_at=datetime.now(timezone.utc),
    )
