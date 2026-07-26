from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from echosense.apple_auth import AppleUserTokenVault
from echosense.deletion import DeletionCoordinator
from echosense.evaluation import CounterfactualReport
from echosense.evaluation_service import EvaluationService
from echosense.exposure_store import ExposureStore
from echosense.memory import PreferenceMemory, memory_from_environment
from echosense.providers import MusicProvider, RecommendationCandidate, provider_from_environment
from echosense.ranking_policy import PolicyCandidate, RankingPolicy, rank_with_policy
from echosense.storage import Storage

# Core routes are collected independently from any deployable FastAPI
# application. Deployment entry points compose this router through
# ``create_app`` instead of mutating a shared global application.
_core_router = APIRouter()
storage: Storage | None = None
music_provider: MusicProvider | None = None
preference_memory: PreferenceMemory | None = None
deletion_coordinator: DeletionCoordinator | None = None
evaluation_service: EvaluationService | None = None
exposure_store: ExposureStore | None = None

OUTCOME_DELTAS: dict[str, float] = {
    "completed": 0.04,
    "liked": 0.12,
    "skipped": -0.04,
    "disliked": -0.15,
}


def get_storage() -> Storage:
    global storage
    if storage is None:
        storage = Storage()
    return storage


def get_music_provider() -> MusicProvider:
    global music_provider
    if music_provider is None:
        music_provider = provider_from_environment(get_storage())
    return music_provider


def get_preference_memory() -> PreferenceMemory:
    global preference_memory
    if preference_memory is None:
        preference_memory = memory_from_environment()
    return preference_memory


def get_deletion_coordinator() -> DeletionCoordinator:
    global deletion_coordinator
    if deletion_coordinator is None:
        deletion_coordinator = DeletionCoordinator(get_storage(), get_preference_memory())
    return deletion_coordinator


def get_evaluation_service() -> EvaluationService:
    global evaluation_service
    if evaluation_service is None:
        evaluation_service = EvaluationService(get_storage())
    return evaluation_service


def get_exposure_store() -> ExposureStore:
    global exposure_store
    if exposure_store is None:
        exposure_store = ExposureStore(get_storage())
    return exposure_store


class ConsentGrant(BaseModel):
    user_id: str
    purpose_id: str
    policy_version: str


class AppleMusicUserTokenRequest(BaseModel):
    music_user_token: str = Field(min_length=1)


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
    provider: str
    item_id: str
    explanation: str
    generated_at: datetime


class DecisionTraceResponse(BaseModel):
    decision_id: str
    user_id: str
    context: str
    context_confidence: float
    provider: str
    item_id: str
    factors: dict[str, object]
    created_at: datetime


class OutcomeRequest(BaseModel):
    outcome_id: str = Field(min_length=1)
    user_id: str
    decision_id: str
    outcome: Literal["completed", "liked", "skipped", "disliked"]


class PreferenceResponse(BaseModel):
    user_id: str
    provider: str
    item_id: str
    context: str
    weight: float
    evidence_count: int
    updated_at: datetime
    decay_anchor: datetime


class EvaluationOutcomeRequest(BaseModel):
    outcome_id: str = Field(min_length=1)
    user_id: str
    decision_id: str
    outcome: Literal["completed", "liked", "skipped", "disliked"]
    observed_at: datetime | None = None
    playback_seconds: float | None = Field(default=None, ge=0.0)
    completion_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    attribution_window_seconds: int = Field(default=3600, ge=1, le=86400)


class CounterfactualCandidateResponse(BaseModel):
    provider: str
    item_id: str
    rank: int
    estimated_reward: float
    estimated_lift: float


class CounterfactualReportResponse(BaseModel):
    decision_id: str
    outcome_id: str
    observed_reward: float
    selected_item_id: str
    best_alternative: CounterfactualCandidateResponse | None
    estimated_regret: float
    confidence: str
    evaluated_at: datetime


class DeletionRequest(BaseModel):
    purpose_id: str = "contextual_recommendation"
    confirmation: Literal["delete"]


class DeletionResponse(BaseModel):
    deletion_id: str
    status: str
    counts: dict[str, int]
    subject_hash: str


class DeletionStatusResponse(BaseModel):
    deletion_id: str
    subject_hash: str
    purpose_id: str
    status: str
    counts: dict[str, int]
    requested_at: datetime
    completed_at: datetime | None


def infer_context(signals: list[Signal]) -> tuple[str, float, dict[str, str]]:
    values = {signal.type: signal.value.lower() for signal in signals}
    confidences = [signal.confidence for signal in signals]
    confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.25
    if values.get("activity") == "driving" and values.get("weather") == "rain":
        return "rainy_commute", confidence, values
    if values.get("activity") == "driving":
        return "commute", confidence, values
    if values.get("time") in {"evening", "night"}:
        return "evening_wind_down", confidence, values
    return "general_listening", confidence, values


def ranking_policy_from_environment() -> RankingPolicy:
    return RankingPolicy(
        novelty_weight=float(os.getenv("ECHOSENSE_NOVELTY_WEIGHT", "0.05")),
        exploration_rate=float(os.getenv("ECHOSENSE_EXPLORATION_RATE", "0.05")),
        exploration_pool=int(os.getenv("ECHOSENSE_EXPLORATION_POOL", "3")),
    )


def rank_candidates(
    *, user_id: str, context: str, decision_id: str, candidates: list[RecommendationCandidate]
) -> tuple[RecommendationCandidate, float, float, list[dict[str, object]], dict[str, object]]:
    if not candidates:
        raise LookupError("Provider returned no recommendation candidates")
    half_life_days = float(os.getenv("ECHOSENSE_PREFERENCE_HALF_LIFE_DAYS", "30"))
    influence = min(0.5, max(0.0, float(os.getenv("ECHOSENSE_PREFERENCE_INFLUENCE", "0.25"))))
    weights = get_preference_memory().rank_weights(
        user_id=user_id,
        context=context,
        candidates=[(candidate.provider, candidate.item_id) for candidate in candidates],
        half_life_days=half_life_days,
    )
    exposures = get_exposure_store().counts_for(
        user_id, [(candidate.provider, candidate.item_id) for candidate in candidates]
    )
    policy = ranking_policy_from_environment()
    ranked = rank_with_policy(
        [
            PolicyCandidate(
                provider=candidate.provider,
                item_id=candidate.item_id,
                base_score=candidate.base_score,
                preference_weight=weights[(candidate.provider, candidate.item_id)],
                exposure_count=exposures[(candidate.provider, candidate.item_id)],
                group=candidate.provider,
            )
            for candidate in candidates
        ],
        preference_influence=influence,
        policy=policy,
        seed_material=f"{user_id}:{context}:{decision_id}",
    )
    selected_ranked = ranked[0]
    selected = next(
        candidate
        for candidate in candidates
        if candidate.provider == selected_ranked.provider
        and candidate.item_id == selected_ranked.item_id
    )
    slate = [
        {
            "provider": item.provider,
            "item_id": item.item_id,
            "rank": item.rank,
            "provider_base_score": item.base_score,
            "preference_weight": round(item.preference_weight, 6),
            "exposure_count": exposures[(item.provider, item.item_id)],
            "novelty_score": item.novelty_score,
            "ranking_score": item.policy_score,
            "policy_score": item.policy_score,
            "group": item.group,
            "explored": item.explored,
            "selected": item.selected,
        }
        for item in ranked
    ]
    policy_factors: dict[str, object] = {
        "preference_influence": influence,
        "novelty_weight": policy.novelty_weight,
        "exploration_rate": policy.exploration_rate,
        "exploration_pool": policy.exploration_pool,
        "explored": selected_ranked.explored,
    }
    return (
        selected,
        round(selected_ranked.preference_weight, 6),
        selected_ranked.policy_score,
        slate,
        policy_factors,
    )


def require_consent(user_id: str, purpose_id: str = "contextual_recommendation") -> None:
    if not get_storage().has_active_consent(user_id, purpose_id):
        raise HTTPException(
            status_code=403,
            detail={"code": "consent_required", "missing_purposes": [purpose_id]},
        )


def report_response(report: CounterfactualReport) -> CounterfactualReportResponse:
    return CounterfactualReportResponse.model_validate(report, from_attributes=True)


@_core_router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@_core_router.put("/v1/consents", status_code=status.HTTP_204_NO_CONTENT)
def grant_consent(grant: ConsentGrant) -> None:
    store = get_storage()
    store.upsert_consent(grant.user_id, grant.purpose_id, grant.policy_version)
    store.append_event(
        event_id=f"evt_{uuid4().hex}",
        event_type="consent.granted",
        user_id=grant.user_id,
        trace_id=f"trc_{uuid4().hex}",
        payload={"purpose_id": grant.purpose_id, "policy_version": grant.policy_version},
    )


@_core_router.delete(
    "/v1/users/{user_id}/consents/{purpose_id}", status_code=status.HTTP_204_NO_CONTENT
)
def revoke_consent(user_id: str, purpose_id: str) -> None:
    store = get_storage()
    if not store.revoke_consent(user_id, purpose_id):
        raise HTTPException(status_code=404, detail="Active consent grant not found")
    store.append_event(
        event_id=f"evt_{uuid4().hex}",
        event_type="consent.revoked",
        user_id=user_id,
        trace_id=f"trc_{uuid4().hex}",
        payload={"purpose_id": purpose_id},
    )


@_core_router.post("/v1/users/{user_id}/deletions", response_model=DeletionResponse)
def delete_consent_derived_data(user_id: str, request: DeletionRequest) -> DeletionResponse:
    try:
        result = get_deletion_coordinator().delete_user(user_id, request.purpose_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "deletion_retry_required", "message": str(exc)},
        ) from exc
    return DeletionResponse.model_validate(result, from_attributes=True)


@_core_router.get("/v1/deletions/{deletion_id}", response_model=DeletionStatusResponse)
def get_deletion_status(deletion_id: str) -> DeletionStatusResponse:
    deletion = get_deletion_coordinator().get_request(deletion_id)
    if deletion is None:
        raise HTTPException(status_code=404, detail="Deletion request not found")
    return DeletionStatusResponse.model_validate(deletion)


@_core_router.put(
    "/v1/users/{user_id}/providers/apple-music/token",
    status_code=status.HTTP_204_NO_CONTENT,
)
def store_apple_music_user_token(user_id: str, request: AppleMusicUserTokenRequest) -> None:
    try:
        vault = AppleUserTokenVault.from_environment(get_storage())
        vault.store(user_id, request.music_user_token)
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "token_vault_unavailable", "message": str(exc)},
        ) from exc
    get_storage().append_event(
        event_id=f"evt_{uuid4().hex}",
        event_type="provider.user_token.stored",
        user_id=user_id,
        trace_id=f"trc_{uuid4().hex}",
        payload={"provider": "apple_music"},
    )


@_core_router.delete(
    "/v1/users/{user_id}/providers/apple-music/token",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_apple_music_user_token(user_id: str) -> None:
    try:
        vault = AppleUserTokenVault.from_environment(get_storage())
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "token_vault_unavailable", "message": str(exc)},
        ) from exc
    if not vault.revoke(user_id):
        raise HTTPException(status_code=404, detail="Active Apple Music user token not found")
    get_storage().append_event(
        event_id=f"evt_{uuid4().hex}",
        event_type="provider.user_token.revoked",
        user_id=user_id,
        trace_id=f"trc_{uuid4().hex}",
        payload={"provider": "apple_music"},
    )


@_core_router.post("/v1/recommendations", response_model=RecommendationResponse)
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
    context, confidence, factors = infer_context(request.signals)
    decision_id = f"dec_{uuid4().hex}"
    try:
        candidates = get_music_provider().candidates_for_context(context, request.user_id, limit=5)
        candidate, preference_weight, ranking_score, candidate_slate, policy_factors = (
            rank_candidates(
                user_id=request.user_id,
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
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "memory_unavailable", "message": str(exc)},
        ) from exc
    decision_factors: dict[str, object] = {
        **factors,
        "candidate_count": len(candidates),
        "provider_base_score": candidate.base_score,
        "preference_weight": preference_weight,
        "ranking_score": ranking_score,
        "ranking_policy": policy_factors,
        "candidate_slate": candidate_slate,
    }
    trace_id = f"trc_{uuid4().hex}"
    store.save_decision_trace(
        decision_id=decision_id,
        user_id=request.user_id,
        context=context,
        context_confidence=confidence,
        provider=candidate.provider,
        item_id=candidate.item_id,
        factors=decision_factors,
    )
    exposure_count = get_exposure_store().record_selection(
        request.user_id, candidate.provider, candidate.item_id
    )
    decision_factors["selected_exposure_count_after"] = exposure_count
    store.append_event(
        event_id=f"evt_{uuid4().hex}",
        event_type="recommendation.ranked",
        user_id=request.user_id,
        trace_id=trace_id,
        payload={
            "decision_id": decision_id,
            "context": context,
            "context_confidence": confidence,
            "selected_item_id": candidate.item_id,
            "provider": candidate.provider,
            "factors": decision_factors,
        },
    )
    preference_phrase = " and your learned preference" if abs(preference_weight) >= 0.001 else ""
    policy_phrase = " with controlled exploration" if policy_factors["explored"] else ""
    return RecommendationResponse(
        decision_id=decision_id,
        context=context,
        context_confidence=confidence,
        provider=candidate.provider,
        item_id=candidate.item_id,
        explanation=(
            f"We selected {candidate.rationale} based on the current context"
            f"{preference_phrase}{policy_phrase}."
        ),
        generated_at=datetime.now(timezone.utc),
    )


@_core_router.post("/v1/outcomes", response_model=PreferenceResponse)
def submit_outcome(request: OutcomeRequest) -> PreferenceResponse:
    store = get_storage()
    require_consent(request.user_id)
    trace = store.get_decision_trace(request.decision_id)
    if trace is None or trace["user_id"] != request.user_id:
        raise HTTPException(status_code=404, detail="Decision trace not found")
    delta = OUTCOME_DELTAS[request.outcome]
    try:
        preference = get_preference_memory().apply_outcome(
            user_id=request.user_id,
            provider=trace["provider"],
            item_id=trace["item_id"],
            context=trace["context"],
            delta=delta,
            outcome_id=request.outcome_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "memory_unavailable", "message": str(exc)},
        ) from exc
    store.append_event(
        event_id=f"evt_{uuid4().hex}",
        event_type="preference.updated",
        user_id=request.user_id,
        trace_id=f"trc_{uuid4().hex}",
        payload={
            "outcome_id": request.outcome_id,
            "decision_id": request.decision_id,
            "outcome": request.outcome,
            "provider": preference.provider,
            "item_id": preference.item_id,
            "context": preference.context,
            "delta": delta,
            "weight": preference.weight,
            "evidence_count": preference.evidence_count,
        },
    )
    return PreferenceResponse.model_validate(preference, from_attributes=True)


@_core_router.post("/v1/evaluations/outcomes", response_model=CounterfactualReportResponse)
def evaluate_outcome(request: EvaluationOutcomeRequest) -> CounterfactualReportResponse:
    require_consent(request.user_id)
    trace = get_storage().get_decision_trace(request.decision_id)
    if trace is None or trace["user_id"] != request.user_id:
        raise HTTPException(status_code=404, detail="Decision trace not found")
    try:
        report = get_evaluation_service().attribute_and_evaluate(
            outcome_id=request.outcome_id,
            decision_id=request.decision_id,
            outcome=request.outcome,
            observed_at=request.observed_at,
            playback_seconds=request.playback_seconds,
            completion_ratio=request.completion_ratio,
            attribution_window_seconds=request.attribution_window_seconds,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "evaluation_rejected", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "evaluation_unavailable", "message": str(exc)},
        ) from exc
    get_storage().append_event(
        event_id=f"evt_{uuid4().hex}",
        event_type="evaluation.counterfactual.completed",
        user_id=request.user_id,
        trace_id=f"trc_{uuid4().hex}",
        payload={
            "outcome_id": report.outcome_id,
            "decision_id": report.decision_id,
            "observed_reward": report.observed_reward,
            "estimated_regret": report.estimated_regret,
            "confidence": report.confidence,
        },
    )
    return report_response(report)


@_core_router.get(
    "/v1/evaluations/outcomes/{outcome_id}",
    response_model=CounterfactualReportResponse,
)
def get_evaluation_report(outcome_id: str, user_id: str) -> CounterfactualReportResponse:
    require_consent(user_id)
    payload = get_evaluation_service().store.get_report(outcome_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Evaluation report not found")
    trace = get_storage().get_decision_trace(payload["decision_id"])
    if trace is None or trace["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Evaluation report not found")
    return report_response(get_evaluation_service()._report_from_dict(payload))


@_core_router.get("/v1/decision-traces/{decision_id}", response_model=DecisionTraceResponse)
def get_decision_trace(decision_id: str) -> DecisionTraceResponse:
    trace = get_storage().get_decision_trace(decision_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Decision trace not found")
    return DecisionTraceResponse.model_validate(trace)


AppProfile = Literal["api", "legacy", "product"]


def create_app(profile: AppProfile = "api") -> FastAPI:
    """Create an isolated EchoSense application for a deployment profile."""

    application = FastAPI(title="EchoSense", version="0.24.0")
    application.include_router(_core_router)

    @application.get("/healthz", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok", "profile": profile, "version": application.version}

    if profile == "api":
        return application

    if profile == "legacy":
        from pathlib import Path

        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        from echosense.apple_music_sync import router as apple_music_sync_router
        from echosense.apple_music_web import router as apple_music_web_router
        from echosense.profile_recommendations import router as profile_recommendations_router
        from echosense.taste_profile import router as taste_profile_router

        ui_dir = Path(__file__).with_name("web")
        application.include_router(apple_music_web_router)
        application.include_router(apple_music_sync_router)
        application.include_router(taste_profile_router)
        application.include_router(profile_recommendations_router)
        application.mount("/ui", StaticFiles(directory=ui_dir), name="ui")

        @application.get("/", include_in_schema=False)
        def cognitive_dashboard() -> FileResponse:
            return FileResponse(ui_dir / "index.html")

        return application

    if profile == "product":
        from echosense.player_routes import router as player_router
        from echosense.product_ui import router as product_ui_router
        from echosense.spotify_auth import router as spotify_auth_router

        application.include_router(spotify_auth_router)
        application.include_router(player_router)
        application.include_router(product_ui_router)
        return application

    raise ValueError(f"Unknown EchoSense application profile: {profile}")


# Backwards-compatible API-only entry point.
app = create_app()
