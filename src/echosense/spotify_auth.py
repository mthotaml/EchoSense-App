from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from math import ceil
from threading import Lock
from typing import Callable, Literal
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from echosense.context_candidates import ContextCandidateService
from echosense.diverse_slate import DiverseSlateService
from echosense.evaluation_service import EvaluationService
from echosense.listening_context import ListeningContextService, ListeningMoment
from echosense.listening_intelligence import ListeningIntelligenceService
from echosense.listening_intelligence_store import ListeningIntelligenceStore
from echosense.music_dna import MusicDNAGenerator
from echosense.music_dna_service import music_dna_service
from echosense.playback_learning import PlaybackLearningService
from echosense.providers.spotify import (
    SpotifyClient,
    SpotifyLibrary,
    SpotifyPlaylists,
    SpotifyProvider,
    SpotifyRateLimited,
)
from echosense.ranking_boosts import RecommendationBoosts, build_context_statement
from echosense.recording_identity import RecordingReference
from echosense.repositories.music_dna import MusicDNARepository
from echosense.repositories.provider_connections import (
    ProviderConnection,
    ProviderConnectionRepository,
)
from echosense.temporal_mood import (
    MoodEvidence,
    TemporalMoodLearningService,
    TemporalMoodProfile,
)

router = APIRouter(prefix="/auth/spotify", tags=["spotify-auth"])

SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_URL = "https://api.spotify.com/v1"
SPOTIFY_PROFILE_URL = f"{SPOTIFY_API_URL}/me"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8001/auth/spotify/callback"
DEFAULT_SCOPES = (
    "user-top-read user-read-recently-played user-read-email user-read-private "
    "user-library-read user-library-modify playlist-read-private "
    "playlist-read-collaborative streaming user-read-playback-state "
    "user-modify-playback-state"
)
SESSION_COOKIE = "echosense_spotify_session"
STATE_COOKIE = "echosense_spotify_oauth_state"
VERIFIER_COOKIE = "echosense_spotify_pkce_verifier"
SPOTIFY_PROFILE_RETRY_LIMIT_SECONDS = 30
SPOTIFY_LIBRARY_STATUS_CACHE_SECONDS = 300


SpotifySession = ProviderConnection
_connection_repository: ProviderConnectionRepository | None = None
_library_status_cache: dict[tuple[str, str], tuple[bool, float]] = {}
_library_cooldown_until: dict[str, float] = {}
_library_status_lock = Lock()


def _spotify_profile_with_backoff(
    client: httpx.Client,
    access_token: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    headers = {"Authorization": f"Bearer {access_token}"}
    for attempt in range(2):
        response = client.get(SPOTIFY_PROFILE_URL, headers=headers)
        if response.status_code != 429:
            response.raise_for_status()
            profile = response.json()
            if not isinstance(profile, dict):
                raise ValueError("Spotify profile response must be an object")
            return profile
        retry_header = response.headers.get("Retry-After", "1")
        retry_after = int(retry_header) if retry_header.isdigit() else 1
        retry_after = max(1, retry_after)
        if attempt == 0 and retry_after <= SPOTIFY_PROFILE_RETRY_LIMIT_SECONDS:
            sleep(retry_after)
            continue
        raise HTTPException(
            status_code=429,
            detail={
                "code": "spotify_rate_limited",
                "message": "Spotify is temporarily limiting connection requests. Wait before reconnecting.",
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )
    raise RuntimeError("Spotify profile retry loop ended unexpectedly")


class SpotifyFeedbackRequest(BaseModel):
    outcome_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    signal: Literal[
        "played", "completed", "skipped", "saved", "unsaved", "liked", "disliked", "rated"
    ]
    completion_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    playback_seconds: float | None = Field(default=None, ge=0.0)
    rating: int | None = Field(default=None, ge=1, le=5)


class SpotifyLibrarySaveRequest(BaseModel):
    outcome_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)


class TemporalMoodCorrectionRequest(BaseModel):
    daypart: str = Field(min_length=1, max_length=32)
    mood: str = Field(min_length=1, max_length=32)


class TemporalMoodSettingRequest(BaseModel):
    enabled: bool


def get_connection_repository() -> ProviderConnectionRepository:
    global _connection_repository
    if _connection_repository is None:
        try:
            _connection_repository = ProviderConnectionRepository.from_environment()
        except (KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "spotify_token_storage_not_configured",
                    "missing": "ECHOSENSE_TOKEN_ENCRYPTION_KEY",
                },
            ) from exc
    return _connection_repository


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "spotify_not_configured", "missing": name},
        )
    return value


def _redirect_uri() -> str:
    return os.getenv("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip()


def _scopes() -> str:
    return os.getenv("SPOTIFY_SCOPES", DEFAULT_SCOPES).strip()


def _why_now(
    candidate: dict[str, object],
    context_labels: tuple[str, ...],
    *,
    weather: str | None,
    region: str | None,
    road_setting: str | None,
    activity: str | None,
    daypart: str | None,
    temporal_mood: TemporalMoodProfile | None = None,
    context_statement: str | None = None,
    moment_impact: dict[str, object] | None = None,
) -> dict[str, object]:
    preference = float(candidate.get("preference_weight", 0.0))
    context_fit = float(candidate.get("context_fit", 0.0))
    effective_weights = dict(candidate.get("effective_weights", {}))
    observations = list(context_labels)
    for value, label in (
        (weather, "weather"),
        (region, "coarse location"),
        (road_setting, "road setting"),
        (activity, "movement"),
        (daypart, "local time"),
    ):
        if value and not any(value.replace("_", " ") in item for item in observations):
            observations.append(f"{label}: {value.replace('_', ' ')}")
    return {
        "overall_score": int(candidate["normalized_score"]),
        "factors": [
            {
                "name": "Music DNA affinity",
                "score": round(float(candidate["provider_base_score"]) * 100),
                "effective_weight": round(float(effective_weights.get("music_dna", 0)) * 100),
            },
            {
                "name": "Live context fit",
                "score": round(context_fit * 100),
                "effective_weight": round(float(effective_weights.get("live_context", 0)) * 100),
            },
            *(
                [
                    {
                        "name": (
                            "Time pattern"
                            if temporal_mood.pattern_type == "stable_pattern"
                            else "Recent mood shift"
                        ),
                        "score": round(temporal_mood.confidence * 100),
                    }
                ]
                if temporal_mood and temporal_mood.mood
                else []
            ),
            {
                "name": "Learned preference",
                "score": round(max(-1.0, min(1.0, preference)) * 100),
                "effective_weight": round(
                    float(effective_weights.get("learned_preference", 0)) * 100
                ),
            },
            {
                "name": "Diversity guard",
                "score": round(float(candidate.get("diversity_fit", 1.0)) * 100),
                "effective_weight": round(float(effective_weights.get("diversity", 0)) * 100),
            },
        ],
        "observations": observations or ["Music DNA and recent listening"],
        "summary": context_statement
        or (
            temporal_mood.explanation
            if temporal_mood and temporal_mood.mood
            else f"Selected from your Music DNA with {round(context_fit * 100)}% live-context fit."
        ),
        "moment_impact": moment_impact,
    }


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _basic_authorization(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return base64.b64encode(raw).decode("ascii")


def _cookie_secure(request: Request) -> bool:
    return request.url.scheme == "https"


def _refresh_session(session: SpotifySession, *, force: bool = False) -> None:
    if not force and session.expires_at > datetime.now(UTC) + timedelta(seconds=30):
        return
    if not session.refresh_token:
        raise HTTPException(status_code=401, detail={"code": "spotify_reconnect_required"})
    client_id = _required_environment("SPOTIFY_CLIENT_ID")
    client_secret = _required_environment("SPOTIFY_CLIENT_SECRET")
    try:
        response = httpx.post(
            SPOTIFY_TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": session.refresh_token},
            headers={
                "Authorization": f"Basic {_basic_authorization(client_id, client_secret)}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "spotify_refresh_failed", "message": str(exc)},
        ) from exc
    session.access_token = str(payload["access_token"])
    session.refresh_token = payload.get("refresh_token", session.refresh_token)
    session.expires_at = datetime.now(UTC) + timedelta(seconds=int(payload.get("expires_in", 3600)))
    get_connection_repository().save(session)


def _connected_session(session_id: str | None) -> SpotifySession:
    session = get_connection_repository().get(session_id, "spotify") if session_id else None
    if session is None:
        raise HTTPException(status_code=401, detail={"code": "spotify_not_connected"})
    return session


@router.get("/login")
def spotify_login(request: Request) -> RedirectResponse:
    client_id = _required_environment("SPOTIFY_CLIENT_ID")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": _redirect_uri(),
            "scope": _scopes(),
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": _code_challenge(verifier),
            "show_dialog": "false",
        }
    )
    response = RedirectResponse(f"{SPOTIFY_AUTHORIZE_URL}?{query}", status_code=302)
    secure = _cookie_secure(request)
    response.set_cookie(
        STATE_COOKIE, state, max_age=600, httponly=True, secure=secure, samesite="lax"
    )
    response.set_cookie(
        VERIFIER_COOKIE, verifier, max_age=600, httponly=True, secure=secure, samesite="lax"
    )
    return response


@router.get("/callback")
def spotify_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    expected_state: str | None = Cookie(default=None, alias=STATE_COOKIE),
    verifier: str | None = Cookie(default=None, alias=VERIFIER_COOKIE),
) -> RedirectResponse:
    if error:
        return RedirectResponse(f"/?spotify_error={error}", status_code=302)
    if (
        not code
        or not state
        or not expected_state
        or not secrets.compare_digest(state, expected_state)
    ):
        raise HTTPException(status_code=400, detail={"code": "invalid_oauth_state"})
    if not verifier:
        raise HTTPException(status_code=400, detail={"code": "missing_pkce_verifier"})

    client_id = _required_environment("SPOTIFY_CLIENT_ID")
    client_secret = _required_environment("SPOTIFY_CLIENT_SECRET")
    try:
        with httpx.Client(timeout=15.0) as client:
            token_response = client.post(
                SPOTIFY_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _redirect_uri(),
                    "code_verifier": verifier,
                },
                headers={
                    "Authorization": f"Basic {_basic_authorization(client_id, client_secret)}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
            access_token = str(token_payload["access_token"])
            profile = _spotify_profile_with_backoff(client, access_token)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "spotify_exchange_failed", "message": str(exc)},
        ) from exc

    session_id = secrets.token_urlsafe(32)
    expires_in = int(token_payload.get("expires_in", 3600))
    connection = SpotifySession(
        session_id=session_id,
        provider="spotify",
        provider_user_id=str(profile["id"]),
        access_token=access_token,
        refresh_token=token_payload.get("refresh_token"),
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
        profile=profile,
    )
    get_connection_repository().save(connection)
    response = RedirectResponse("/?spotify=connected", status_code=302)
    response.delete_cookie(STATE_COOKIE)
    response.delete_cookie(VERIFIER_COOKIE)
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
    )
    return response


@router.get("/session")
def spotify_session(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = get_connection_repository().get(session_id, "spotify") if session_id else None
    if session is None:
        return {"connected": False}
    profile = session.profile
    return {
        "connected": True,
        "profile": {
            "id": profile.get("id"),
            "display_name": profile.get("display_name"),
            "email": profile.get("email"),
            "country": profile.get("country"),
            "product": profile.get("product"),
            "images": profile.get("images", []),
        },
        "expires_at": session.expires_at,
    }


def _spotify_data_resource_key(
    *,
    moment: str,
    weather: str | None,
    region: str | None,
    road_setting: str | None,
    activity: str | None,
    daypart: str | None,
    boosts: tuple[int, int, int, int],
) -> str:
    fingerprint = json.dumps(
        {
            "moment": moment,
            "weather": weather,
            "region": region,
            "road_setting": road_setting,
            "activity": activity,
            "daypart": daypart,
            "boosts": boosts,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"recommendations:{hashlib.sha256(fingerprint.encode()).hexdigest()[:24]}"


def _provider_cooldown(storage, user_id: str) -> tuple[int, str] | None:
    state = storage.get_provider_cooldown("spotify", user_id)
    if state is None or not state.get("cooldown_until"):
        return None
    remaining = (
        datetime.fromisoformat(state["cooldown_until"]) - datetime.now(UTC)
    ).total_seconds()
    if remaining <= 0:
        return None
    return ceil(remaining), str(state.get("error_code") or "spotify_temporarily_unavailable")


def _cached_spotify_data(
    storage,
    *,
    user_id: str,
    resource_key: str,
    reason: str,
    retry_after: int,
) -> dict[str, object] | None:
    snapshot = storage.get_provider_snapshot("spotify", user_id, resource_key)
    if snapshot is None:
        return None
    payload = snapshot["payload"]
    payload["resilience"] = {
        "mode": "last_known_good",
        "reason": reason,
        "captured_at": snapshot["captured_at"],
        "retry_after_seconds": retry_after,
        "exact_context_match": snapshot["exact_match"],
    }
    payload["context_statement"] = (
        "Spotify is cooling down. EchoSense is using your last verified playback plan."
    )
    payload["moment_impact"] = {
        **payload.get("moment_impact", {}),
        "message": "Using the last verified plan until Spotify is available again.",
    }
    return payload


@router.get("/data")
def spotify_data(
    moment: ListeningMoment = Query(default="general"),
    weather: str | None = Query(default=None, max_length=32),
    region: str | None = Query(default=None, max_length=64),
    road_setting: str | None = Query(default=None, max_length=32),
    activity: str | None = Query(default=None, max_length=32),
    daypart: str | None = Query(default=None, max_length=32),
    boost_music_dna: int = Query(default=0, ge=0, le=100),
    boost_live_context: int = Query(default=0, ge=0, le=100),
    boost_learned_preference: int = Query(default=0, ge=0, le=100),
    boost_diversity: int = Query(default=0, ge=0, le=100),
    exclude: list[str] = Query(default=[]),
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    storage = get_connection_repository().storage
    resource_key = _spotify_data_resource_key(
        moment=moment,
        weather=weather,
        region=region,
        road_setting=road_setting,
        activity=activity,
        daypart=daypart,
        boosts=(
            boost_music_dna,
            boost_live_context,
            boost_learned_preference,
            boost_diversity,
        ),
    )
    cooldown = _provider_cooldown(storage, session.provider_user_id)
    if cooldown:
        cooldown_remaining, cooldown_reason = cooldown
        cached = _cached_spotify_data(
            storage,
            user_id=session.provider_user_id,
            resource_key=resource_key,
            reason=cooldown_reason,
            retry_after=cooldown_remaining,
        )
        if cached is not None:
            return cached
        raise HTTPException(
            status_code=429,
            detail={
                "code": "spotify_rate_limited",
                "retry_after_seconds": cooldown_remaining,
            },
            headers={"Retry-After": str(cooldown_remaining)},
        )
    try:
        spotify_client = SpotifyClient(session, _refresh_session)
        imported = SpotifyProvider(spotify_client).import_music_data()
        repository = MusicDNARepository(get_connection_repository().storage)
        repository.save(session.provider_user_id, imported)
        music_dna = MusicDNAGenerator().generate(session.provider_user_id, imported)
        repository.save_profile(music_dna)
        learning = PlaybackLearningService(storage)
        intelligence_store = ListeningIntelligenceStore(storage)
        echo_identity = intelligence_store.resolve_user(
            provider="spotify",
            provider_user_id=session.provider_user_id,
            display_name=str(session.profile.get("display_name") or "Spotify listener"),
        )
        temporal_service = TemporalMoodLearningService(storage)
        temporal_profile = temporal_service.profile(
            user_id=session.provider_user_id,
            daypart=daypart or "unknown",
        )
        context_service = ListeningContextService()
        effective_moment, moment_source = context_service.resolve_moment(moment, activity)
        context_fits = context_service.score(imported, effective_moment)
        ranking_context = context_service.ranking_context(effective_moment)
        top_tracks = {item.track.provider_id: item.track for item in imported.top_tracks}
        recent_tracks = {item.track.provider_id: item.track for item in imported.recent_tracks}
        expanded = ContextCandidateService().expand(
            spotify_client,
            weather=weather,
            region=region,
            road_setting=road_setting,
            activity=activity,
            daypart=daypart,
            mood=temporal_profile.mood,
            moment=effective_moment,
        )
        candidate_tracks = list(
            {
                track.provider_id: track
                for track in (
                    *top_tracks.values(),
                    *expanded.tracks,
                    *recent_tracks.values(),
                )
            }.values()
        )
        combined_context_scores = {item_id: fit.score for item_id, fit in context_fits.items()}
        for item_id, score in expanded.scores.items():
            combined_context_scores[item_id] = max(
                combined_context_scores.get(item_id, 0.0),
                score,
            )
        live_context = any((weather, region, road_setting, activity, daypart))
        moment_context_available = effective_moment != "general"
        boosts = RecommendationBoosts(
            music_dna=boost_music_dna,
            live_context=boost_live_context,
            learned_preference=boost_learned_preference,
            diversity=boost_diversity,
        )
        effective_weights = boosts.effective_weights(
            live_context_available=live_context or moment_context_available
        )
        recent_artist_positions: dict[str, int] = {}
        for position, observation in enumerate(imported.recent_tracks[:20]):
            recent_artist_positions.setdefault(
                observation.track.primary_artist.casefold(), position
            )
        diversity_scores = {
            track.provider_id: (
                min(1.0, 0.25 + recent_artist_positions[track.primary_artist.casefold()] / 20)
                if track.primary_artist.casefold() in recent_artist_positions
                else 1.0
            )
            for track in candidate_tracks
        }
        baseline_context_fits = context_service.score(imported, "general")
        baseline_context_scores = {
            item_id: fit.score for item_id, fit in baseline_context_fits.items()
        }
        _, baseline_slate = learning.rank(
            user_id=session.provider_user_id,
            provider="spotify",
            context="general_listening",
            tracks=candidate_tracks,
            context_scores=baseline_context_scores,
            context_weight=0.35 if live_context else 0.15,
            diversity_scores=diversity_scores,
            boosts=boosts,
            live_context_available=live_context,
        )
        baseline_ranks = {str(item["item_id"]): int(item["final_rank"]) for item in baseline_slate}
        context_statement = build_context_statement(
            moment=effective_moment,
            weather=weather,
            region=region,
            road_setting=road_setting,
            activity=activity,
            daypart=daypart,
            boosts=boosts,
            effective_weights=effective_weights,
        )
        recommendation, candidate_slate = learning.rank(
            user_id=session.provider_user_id,
            provider="spotify",
            context=ranking_context,
            tracks=candidate_tracks,
            context_scores=combined_context_scores,
            context_weight=0.35 if live_context else 0.15,
            diversity_scores=diversity_scores,
            boosts=boosts,
            live_context_available=live_context or moment_context_available,
        )
        moment_ranks = {str(item["item_id"]): int(item["final_rank"]) for item in candidate_slate}
        moment_changed_order = effective_moment != "general" and any(
            baseline_ranks.get(item_id) != rank for item_id, rank in moment_ranks.items()
        )
        moment_impact = {
            "moment": effective_moment,
            "requested_moment": moment,
            "source": moment_source,
            "applied": effective_moment != "general",
            "changed_order": moment_changed_order,
            "compared_candidates": len(candidate_slate),
            "message": (
                "Any moment is selected; no activity-specific reranking is applied."
                if effective_moment == "general"
                else (
                    f"{effective_moment.title()} "
                    f"({'detected automatically' if moment_source == 'detected' else 'selected'}) "
                    "changed the candidate ordering using moment-specific "
                    "catalog evidence and context-fit scoring."
                    if moment_changed_order
                    else f"{effective_moment.title()} "
                    f"({'detected automatically' if moment_source == 'detected' else 'selected'}) "
                    "was applied, but the available evidence did not "
                    "materially change this ordering."
                )
            ),
        }
        excluded_ids = {item_id for item_id in exclude[:50] if item_id}
        diverse_slate = DiverseSlateService().build(
            candidate_tracks,
            candidate_slate,
            limit=6,
            excluded_ids=excluded_ids,
        )
        recommendation = diverse_slate[0].track if diverse_slate else None
        decision_ids: dict[str, str] = {}
        for slate_item in diverse_slate:
            slate_decision_id = f"dec_{uuid4().hex}"
            decision_ids[slate_item.track.provider_id] = slate_decision_id
            echo_track_id = intelligence_store.observe_track(
                RecordingReference(
                    provider="spotify",
                    provider_id=slate_item.track.provider_id,
                    title=slate_item.track.title,
                    artists=slate_item.track.artists,
                    album=slate_item.track.album,
                    isrc=slate_item.track.isrc,
                    duration_ms=slate_item.track.duration_ms,
                ),
                image_url=slate_item.track.image_url,
                metadata={"spotify_url": slate_item.track.external_url},
            )
            context_evidence = expanded.evidence.get(slate_item.track.provider_id, ())
            ranked_candidate = next(
                item for item in candidate_slate if item["item_id"] == slate_item.track.provider_id
            )
            inferred_mood = temporal_service.infer_track(
                slate_item.track,
                context_evidence,
            )
            if temporal_profile.mood and any("learned" in label for label in context_evidence):
                inferred_mood = inferred_mood or temporal_service.infer_track(
                    slate_item.track,
                    (f"learned {temporal_profile.mood} pattern",),
                )
                if inferred_mood is None:
                    inferred_mood = MoodEvidence(
                        temporal_profile.mood,
                        temporal_profile.pattern_type,
                        temporal_profile.confidence,
                    )
            storage.save_decision_trace(
                decision_id=slate_decision_id,
                user_id=session.provider_user_id,
                context=ranking_context,
                context_confidence=music_dna.confidence,
                provider="spotify",
                item_id=slate_item.track.provider_id,
                factors={
                    "echo_user_id": echo_identity.echo_user_id,
                    "echo_track_id": echo_track_id,
                    "track_snapshot": {
                        "title": slate_item.track.title,
                        "artist": slate_item.track.primary_artist,
                        "artists": list(slate_item.track.artists),
                        "album": slate_item.track.album,
                        "image_url": slate_item.track.image_url,
                        "isrc": slate_item.track.isrc,
                        "duration_ms": slate_item.track.duration_ms,
                    },
                    "recommendation_score": ranked_candidate["normalized_score"],
                    "candidate_slate": candidate_slate,
                    "music_dna_confidence": music_dna.confidence,
                    "evidence_count": music_dna.evidence_count,
                    "listening_moment": effective_moment,
                    "requested_listening_moment": moment,
                    "listening_moment_source": moment_source,
                    "moment_impact": {
                        **moment_impact,
                        "baseline_rank": baseline_ranks.get(slate_item.track.provider_id),
                        "moment_rank": moment_ranks.get(slate_item.track.provider_id),
                        "rank_change": (
                            baseline_ranks.get(slate_item.track.provider_id, 0)
                            - moment_ranks.get(slate_item.track.provider_id, 0)
                        ),
                    },
                    "diverse_slate_rank": slate_item.rank,
                    "live_context": {
                        "weather": weather,
                        "region": region,
                        "road_setting": road_setting,
                        "activity": activity,
                        "daypart": daypart,
                    },
                    "recommendation_boosts": boosts.as_dict(),
                    "effective_weights": effective_weights,
                    "context_statement": context_statement,
                    "context_evidence": list(context_evidence),
                    "temporal_mood": (
                        {
                            "mood": inferred_mood.mood,
                            "daypart": daypart or "unknown",
                            "source": inferred_mood.source,
                            "confidence": inferred_mood.confidence,
                            "recording_key": (
                                f"isrc:{slate_item.track.isrc}"
                                if slate_item.track.isrc
                                else f"spotify:{slate_item.track.provider_id}"
                            ),
                            "policy_version": TemporalMoodLearningService.POLICY_VERSION,
                        }
                        if inferred_mood
                        else {
                            "mood": None,
                            "daypart": daypart or "unknown",
                            "policy_version": TemporalMoodLearningService.POLICY_VERSION,
                        }
                    ),
                },
            )
        decision_id = (
            decision_ids.get(recommendation.provider_id) if recommendation is not None else None
        )
    except SpotifyRateLimited as exc:
        storage.set_provider_cooldown(
            provider="spotify",
            user_id=session.provider_user_id,
            cooldown_until=datetime.now(UTC) + timedelta(seconds=exc.retry_after),
            error_code="spotify_rate_limited",
            error_message="Spotify requested a provider-wide cooldown.",
        )
        cached = _cached_spotify_data(
            storage,
            user_id=session.provider_user_id,
            resource_key=resource_key,
            reason="spotify_rate_limited",
            retry_after=exc.retry_after,
        )
        if cached is not None:
            return cached
        raise HTTPException(
            status_code=429,
            detail={
                "code": "spotify_rate_limited",
                "retry_after_seconds": exc.retry_after,
            },
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except httpx.TimeoutException as exc:
        retry_after = 30
        storage.set_provider_cooldown(
            provider="spotify",
            user_id=session.provider_user_id,
            cooldown_until=datetime.now(UTC) + timedelta(seconds=retry_after),
            error_code="spotify_temporarily_unavailable",
            error_message="Spotify timed out.",
        )
        cached = _cached_spotify_data(
            storage,
            user_id=session.provider_user_id,
            resource_key=resource_key,
            reason="spotify_temporarily_unavailable",
            retry_after=retry_after,
        )
        if cached is not None:
            return cached
        raise HTTPException(
            status_code=503,
            detail={
                "code": "spotify_temporarily_unavailable",
                "message": (
                    "Spotify took too long to respond. Your connection is still saved; "
                    "wait a moment and refresh EchoSense."
                ),
            },
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        retry_after = 60
        storage.set_provider_cooldown(
            provider="spotify",
            user_id=session.provider_user_id,
            cooldown_until=datetime.now(UTC) + timedelta(seconds=retry_after),
            error_code="spotify_api_failed",
            error_message="Spotify provider request failed.",
        )
        cached = _cached_spotify_data(
            storage,
            user_id=session.provider_user_id,
            resource_key=resource_key,
            reason="spotify_api_failed",
            retry_after=retry_after,
        )
        if cached is not None:
            return cached
        raise HTTPException(
            status_code=502,
            detail={
                "code": "spotify_api_failed",
                "message": "Spotify is temporarily unavailable. Refresh EchoSense to try again.",
            },
        ) from exc
    result = music_dna_service.build_provider_profile(
        imported,
        display_name=str(session.profile.get("display_name") or "Spotify listener"),
        music_dna=music_dna,
        recommendation=recommendation,
        decision_id=decision_id,
        moment=effective_moment,
        decision_evidence=(
            {
                "noticed": (
                    f"EchoSense detected {effective_moment}."
                    if moment_source == "detected"
                    else f"You selected {effective_moment}."
                ),
                "remembered": (
                    f"Your Music DNA currently has {music_dna.evidence_count} listening signals."
                ),
                "matched_genres": list(
                    context_fits[recommendation.provider_id].matched_genres
                    if recommendation.provider_id in context_fits
                    else ()
                ),
                "context_fit": (
                    context_fits[recommendation.provider_id].score
                    if recommendation.provider_id in context_fits
                    else 0.0
                ),
                "learned_preference": next(
                    (
                        item["preference_weight"]
                        for item in candidate_slate
                        if item["item_id"] == recommendation.provider_id
                    ),
                    0.0,
                ),
            }
            if recommendation
            else None
        ),
        match_score=(
            int(
                next(
                    item["normalized_score"]
                    for item in candidate_slate
                    if item["item_id"] == recommendation.provider_id
                )
            )
            if recommendation
            else None
        ),
    )
    if recommendation is None:
        result["recommendation"] = None
    result["recommendations"] = [
        {
            **music_dna_service._track_view(item.track),
            "rank": item.rank,
            "score": item.score,
            "reason": item.reason,
            "decision_id": decision_ids[item.track.provider_id],
            "why_now": _why_now(
                next(
                    candidate
                    for candidate in candidate_slate
                    if candidate["item_id"] == item.track.provider_id
                ),
                expanded.evidence.get(item.track.provider_id, ()),
                weather=weather,
                region=region,
                road_setting=road_setting,
                activity=activity,
                daypart=daypart,
                temporal_mood=temporal_profile,
                context_statement=context_statement,
                moment_impact={
                    **moment_impact,
                    "baseline_rank": baseline_ranks.get(item.track.provider_id),
                    "moment_rank": moment_ranks.get(item.track.provider_id),
                    "rank_change": (
                        baseline_ranks.get(item.track.provider_id, 0)
                        - moment_ranks.get(item.track.provider_id, 0)
                    ),
                    "context_fit": round(
                        float(
                            next(
                                candidate["context_fit"]
                                for candidate in candidate_slate
                                if candidate["item_id"] == item.track.provider_id
                            )
                        )
                        * 100
                    ),
                    "evidence": list(expanded.evidence.get(item.track.provider_id, ())),
                },
            ),
        }
        for item in diverse_slate
    ]
    result["temporal_mood"] = temporal_profile.as_dict()
    result["context_statement"] = context_statement
    result["recommendation_boosts"] = boosts.as_dict()
    result["effective_weights"] = effective_weights
    result["moment_impact"] = moment_impact
    result["resilience"] = {"mode": "live"}
    storage.save_provider_snapshot(
        provider="spotify",
        user_id=session.provider_user_id,
        resource_key=resource_key,
        payload=result,
    )
    storage.clear_provider_cooldown("spotify", session.provider_user_id)
    return result


@router.get("/intelligence")
def spotify_listening_intelligence(
    history_limit: int = Query(default=30, ge=1, le=100),
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    storage = get_connection_repository().storage
    snapshot = ListeningIntelligenceService(storage).snapshot(
        session.provider_user_id,
        history_limit=history_limit,
    )
    intelligence_store = ListeningIntelligenceStore(storage)
    identity = intelligence_store.resolve_user(
        provider="spotify",
        provider_user_id=session.provider_user_id,
        display_name=str(session.profile.get("display_name") or "Spotify listener"),
    )
    snapshot["provider_neutral"] = intelligence_store.listener_snapshot(identity.echo_user_id)
    return snapshot


@router.get("/intelligence/kpis")
def spotify_provider_neutral_kpis(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    intelligence_store = ListeningIntelligenceStore(get_connection_repository().storage)
    identity = intelligence_store.resolve_user(
        provider="spotify",
        provider_user_id=session.provider_user_id,
        display_name=str(session.profile.get("display_name") or "Spotify listener"),
    )
    return intelligence_store.listener_snapshot(identity.echo_user_id)


@router.post("/feedback")
def spotify_feedback(
    request: SpotifyFeedbackRequest,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    try:
        storage = get_connection_repository().storage
        result = PlaybackLearningService(storage).record(
            outcome_id=request.outcome_id,
            user_id=session.provider_user_id,
            decision_id=request.decision_id,
            signal=request.signal,
            completion_ratio=request.completion_ratio,
            playback_seconds=request.playback_seconds,
            rating=request.rating,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={"code": "decision_not_found"}) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_feedback", "message": str(exc)},
        ) from exc
    evaluation_outcome = {
        "completed": "completed",
        "skipped": "skipped",
        "saved": "liked",
        "liked": "liked",
        "disliked": "disliked",
        "rated": (
            "liked"
            if request.rating and request.rating >= 4
            else "disliked"
            if request.rating and request.rating <= 2
            else None
        ),
    }.get(request.signal)
    report = None
    if evaluation_outcome:
        report = EvaluationService(storage).attribute_and_evaluate(
            outcome_id=request.outcome_id,
            decision_id=request.decision_id,
            outcome=evaluation_outcome,
            playback_seconds=request.playback_seconds,
            completion_ratio=request.completion_ratio,
            attribution_window_seconds=86400,
        )
    if result.applied:
        trace = storage.get_decision_trace(request.decision_id)
        temporal_applied = (
            TemporalMoodLearningService(storage).record(
                outcome_id=request.outcome_id,
                user_id=session.provider_user_id,
                signal=request.signal,
                trace=trace,
                completion_ratio=request.completion_ratio,
                rating=request.rating,
            )
            if trace
            else False
        )
        if trace:
            factors = trace["factors"]
            intelligence_store = ListeningIntelligenceStore(storage)
            identity = intelligence_store.resolve_user(
                provider=trace["provider"],
                provider_user_id=session.provider_user_id,
                display_name=str(session.profile.get("display_name") or "Spotify listener"),
                echo_user_id=factors.get("echo_user_id"),
            )
            echo_track_id = factors.get("echo_track_id")
            if not echo_track_id:
                track = factors.get("track_snapshot") or {}
                echo_track_id = intelligence_store.observe_track(
                    RecordingReference(
                        provider=trace["provider"],
                        provider_id=trace["item_id"],
                        title=str(track.get("title") or "Unknown track"),
                        artists=tuple(
                            track.get("artists") or [track.get("artist") or "Unknown artist"]
                        ),
                        album=track.get("album"),
                        isrc=track.get("isrc"),
                        duration_ms=track.get("duration_ms"),
                    ),
                    image_url=track.get("image_url"),
                )
            listening_session_id = intelligence_store.ensure_session(
                echo_user_id=identity.echo_user_id,
                provider=trace["provider"],
                provider_session_id=session.session_id,
                context={
                    "ranking_context": trace["context"],
                    "listening_moment": factors.get("listening_moment"),
                    "live_context": factors.get("live_context"),
                },
            )
            intelligence_store.record_event(
                event_id=request.outcome_id,
                echo_user_id=identity.echo_user_id,
                echo_track_id=str(echo_track_id),
                provider=trace["provider"],
                provider_track_id=trace["item_id"],
                event_type=request.signal,
                context=trace["context"],
                decision_id=request.decision_id,
                listening_session_id=listening_session_id,
                playback_seconds=request.playback_seconds,
                completion_ratio=request.completion_ratio,
                rating=request.rating,
                payload={"source": "playback_learning_outcome"},
            )
        storage.append_event(
            event_id=f"evt_{uuid4().hex}",
            event_type="playback.learning.applied",
            user_id=session.provider_user_id,
            trace_id=f"trc_{uuid4().hex}",
            payload=asdict(result),
        )
    else:
        temporal_applied = False
    return {
        **asdict(result),
        "temporal_mood_applied": temporal_applied,
        "evaluation": (
            {
                "observed_reward": report.observed_reward,
                "estimated_regret": report.estimated_regret,
                "confidence": report.confidence,
            }
            if report
            else None
        ),
    }


@router.get("/temporal-mood")
def spotify_temporal_mood(
    daypart: str = Query(min_length=1, max_length=32),
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    return (
        TemporalMoodLearningService(get_connection_repository().storage)
        .profile(
            user_id=session.provider_user_id,
            daypart=daypart,
        )
        .as_dict()
    )


@router.post("/temporal-mood/correct")
def correct_spotify_temporal_mood(
    request: TemporalMoodCorrectionRequest,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    removed = TemporalMoodLearningService(get_connection_repository().storage).correct(
        user_id=session.provider_user_id,
        daypart=request.daypart,
        mood=request.mood,
    )
    return {"status": "corrected", "removed": removed}


@router.put("/temporal-mood/settings")
def set_spotify_temporal_mood(
    request: TemporalMoodSettingRequest,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    TemporalMoodLearningService(get_connection_repository().storage).set_enabled(
        session.provider_user_id,
        request.enabled,
    )
    return {"enabled": request.enabled}


@router.delete("/temporal-mood")
def reset_spotify_temporal_mood(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    removed = TemporalMoodLearningService(get_connection_repository().storage).reset(
        session.provider_user_id
    )
    return {"status": "reset", "removed": removed}


def _library_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SpotifyRateLimited):
        return HTTPException(
            status_code=429,
            detail={
                "code": "spotify_rate_limited",
                "retry_after_seconds": exc.retry_after,
            },
            headers={"Retry-After": str(exc.retry_after)},
        )
    return HTTPException(
        status_code=502,
        detail={"code": "spotify_library_failed", "message": str(exc)},
    )


@router.get("/library/tracks/{track_id}")
def spotify_library_status(
    track_id: str,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    cache_key = (session.provider_user_id, track_id)
    with _library_status_lock:
        now = time.monotonic()
        cooldown_until = _library_cooldown_until.get(session.provider_user_id, 0)
        if cooldown_until > now:
            raise _library_error(SpotifyRateLimited(max(1, ceil(cooldown_until - now))))
        cached = _library_status_cache.get(cache_key)
        if cached and cached[1] > now:
            return {"provider": "spotify", "track_id": track_id, "saved": cached[0]}
        try:
            saved = SpotifyLibrary(SpotifyClient(session, _refresh_session)).contains_track(
                track_id
            )
        except SpotifyRateLimited as exc:
            _library_cooldown_until[session.provider_user_id] = now + exc.retry_after
            raise _library_error(exc) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise _library_error(exc) from exc
        _library_status_cache[cache_key] = (
            saved,
            now + SPOTIFY_LIBRARY_STATUS_CACHE_SECONDS,
        )
    return {"provider": "spotify", "track_id": track_id, "saved": saved}


@router.put("/library/tracks/{track_id}")
def spotify_save_track(
    track_id: str,
    request: SpotifyLibrarySaveRequest,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    try:
        SpotifyLibrary(SpotifyClient(session, _refresh_session)).save_track(track_id)
    except (SpotifyRateLimited, httpx.HTTPError, ValueError) as exc:
        raise _library_error(exc) from exc
    with _library_status_lock:
        _library_status_cache[(session.provider_user_id, track_id)] = (
            True,
            time.monotonic() + SPOTIFY_LIBRARY_STATUS_CACHE_SECONDS,
        )
    learning = spotify_feedback(
        SpotifyFeedbackRequest(
            outcome_id=request.outcome_id,
            decision_id=request.decision_id,
            signal="saved",
        ),
        session_id,
    )
    return {
        "provider": "spotify",
        "track_id": track_id,
        "saved": True,
        "learning": learning,
    }


@router.delete("/library/tracks/{track_id}")
def spotify_remove_track(
    track_id: str,
    request: SpotifyLibrarySaveRequest,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    try:
        SpotifyLibrary(SpotifyClient(session, _refresh_session)).remove_track(track_id)
    except (SpotifyRateLimited, httpx.HTTPError, ValueError) as exc:
        raise _library_error(exc) from exc
    with _library_status_lock:
        _library_status_cache[(session.provider_user_id, track_id)] = (
            False,
            time.monotonic() + SPOTIFY_LIBRARY_STATUS_CACHE_SECONDS,
        )
    learning = spotify_feedback(
        SpotifyFeedbackRequest(
            outcome_id=request.outcome_id,
            decision_id=request.decision_id,
            signal="unsaved",
        ),
        session_id,
    )
    return {
        "provider": "spotify",
        "track_id": track_id,
        "saved": False,
        "learning": learning,
    }


@router.get("/playlists")
def spotify_playlists(
    limit: int = Query(default=8, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    try:
        page = SpotifyPlaylists(
            SpotifyClient(session, _refresh_session),
            session.provider_user_id,
        ).list(limit=limit, offset=offset)
    except (SpotifyRateLimited, httpx.HTTPError, ValueError) as exc:
        raise _library_error(exc) from exc
    return {
        "items": [
            {
                "provider": item.provider,
                "id": item.provider_id,
                "name": item.name,
                "description": item.description,
                "owner_name": item.owner_name,
                "track_count": item.track_count,
                "can_browse": item.can_browse,
                "image_url": item.image_url,
            }
            for item in page.items
        ],
        "total": page.total,
        "offset": page.offset,
        "limit": page.limit,
        "next_offset": page.next_offset,
    }


@router.get("/playlists/{playlist_id}/tracks")
def spotify_playlist_tracks(
    playlist_id: str,
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    try:
        page = SpotifyPlaylists(
            SpotifyClient(session, _refresh_session),
            session.provider_user_id,
        ).tracks(playlist_id, limit=limit, offset=offset)
    except (SpotifyRateLimited, httpx.HTTPError, ValueError) as exc:
        raise _library_error(exc) from exc
    items = []
    for item in page.items:
        track = item.track
        items.append(
            {
                "position": item.position,
                "playable": item.playable,
                "unavailable_reason": item.unavailable_reason,
                "track": (
                    {
                        "provider": track.provider,
                        "id": track.provider_id,
                        "title": track.title,
                        "artists": list(track.artists),
                        "album": track.album,
                        "image_url": track.image_url,
                        "external_url": track.external_url,
                        "uri": f"spotify:track:{track.provider_id}",
                    }
                    if track
                    else None
                ),
            }
        )
    return {
        "items": items,
        "total": page.total,
        "offset": page.offset,
        "limit": page.limit,
        "next_offset": page.next_offset,
    }


@router.post("/logout")
def spotify_logout(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> JSONResponse:
    if session_id:
        get_connection_repository().revoke(session_id, "spotify")
    response = JSONResponse({"status": "disconnected"})
    response.delete_cookie(SESSION_COOKIE)
    return response
