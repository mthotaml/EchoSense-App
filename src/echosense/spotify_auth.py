from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Literal
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


SpotifySession = ProviderConnection
_connection_repository: ProviderConnectionRepository | None = None


class SpotifyFeedbackRequest(BaseModel):
    outcome_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    signal: Literal["played", "completed", "skipped", "saved", "liked", "disliked", "rated"]
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
) -> dict[str, object]:
    preference = float(candidate.get("preference_weight", 0.0))
    context_fit = float(candidate.get("context_fit", 0.0))
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
        "overall_score": round(min(1.0, float(candidate["ranking_score"])) * 100),
        "factors": [
            {
                "name": "Music DNA affinity",
                "score": round(float(candidate["provider_base_score"]) * 100),
            },
            {"name": "Live context fit", "score": round(context_fit * 100)},
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
            },
            {"name": "Diversity guard", "score": 100},
        ],
        "observations": observations or ["Music DNA and recent listening"],
        "summary": (
            temporal_mood.explanation
            if temporal_mood and temporal_mood.mood
            else f"Selected from your Music DNA with {round(context_fit * 100)}% live-context fit."
        ),
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
            profile_response = client.get(
                SPOTIFY_PROFILE_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            profile_response.raise_for_status()
            profile = profile_response.json()
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


@router.get("/data")
def spotify_data(
    moment: ListeningMoment = Query(default="general"),
    weather: str | None = Query(default=None, max_length=32),
    region: str | None = Query(default=None, max_length=64),
    road_setting: str | None = Query(default=None, max_length=32),
    activity: str | None = Query(default=None, max_length=32),
    daypart: str | None = Query(default=None, max_length=32),
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    try:
        spotify_client = SpotifyClient(session, _refresh_session)
        imported = SpotifyProvider(spotify_client).import_music_data()
        repository = MusicDNARepository(get_connection_repository().storage)
        repository.save(session.provider_user_id, imported)
        music_dna = MusicDNAGenerator().generate(session.provider_user_id, imported)
        repository.save_profile(music_dna)
        storage = get_connection_repository().storage
        learning = PlaybackLearningService(storage)
        temporal_service = TemporalMoodLearningService(storage)
        temporal_profile = temporal_service.profile(
            user_id=session.provider_user_id,
            daypart=daypart or "unknown",
        )
        context_service = ListeningContextService()
        context_fits = context_service.score(imported, moment)
        ranking_context = context_service.ranking_context(moment)
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
        recommendation, candidate_slate = learning.rank(
            user_id=session.provider_user_id,
            provider="spotify",
            context=ranking_context,
            tracks=candidate_tracks,
            context_scores=combined_context_scores,
            context_weight=0.35 if live_context else 0.15,
        )
        diverse_slate = DiverseSlateService().build(
            candidate_tracks,
            candidate_slate,
            limit=5,
        )
        decision_ids: dict[str, str] = {}
        for slate_item in diverse_slate:
            slate_decision_id = f"dec_{uuid4().hex}"
            decision_ids[slate_item.track.provider_id] = slate_decision_id
            context_evidence = expanded.evidence.get(slate_item.track.provider_id, ())
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
                    "candidate_slate": candidate_slate,
                    "music_dna_confidence": music_dna.confidence,
                    "evidence_count": music_dna.evidence_count,
                    "listening_moment": moment,
                    "diverse_slate_rank": slate_item.rank,
                    "live_context": {
                        "weather": weather,
                        "region": region,
                        "road_setting": road_setting,
                        "activity": activity,
                        "daypart": daypart,
                    },
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
        raise HTTPException(
            status_code=429,
            detail={
                "code": "spotify_rate_limited",
                "retry_after_seconds": exc.retry_after,
            },
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "spotify_api_failed", "message": str(exc)},
        ) from exc
    result = music_dna_service.build_provider_profile(
        imported,
        display_name=str(session.profile.get("display_name") or "Spotify listener"),
        music_dna=music_dna,
        recommendation=recommendation,
        decision_id=decision_id,
        moment=moment,
        decision_evidence=(
            {
                "noticed": f"You selected {moment}.",
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
    )
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
            ),
        }
        for item in diverse_slate
    ]
    result["temporal_mood"] = temporal_profile.as_dict()
    return result


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
    try:
        saved = SpotifyLibrary(SpotifyClient(session, _refresh_session)).contains_track(track_id)
    except (SpotifyRateLimited, httpx.HTTPError, ValueError) as exc:
        raise _library_error(exc) from exc
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
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    try:
        SpotifyLibrary(SpotifyClient(session, _refresh_session)).remove_track(track_id)
    except (SpotifyRateLimited, httpx.HTTPError, ValueError) as exc:
        raise _library_error(exc) from exc
    return {"provider": "spotify", "track_id": track_id, "saved": False}


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
