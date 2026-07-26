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

from echosense.evaluation_service import EvaluationService
from echosense.music_dna import MusicDNAGenerator
from echosense.music_dna_service import music_dna_service
from echosense.playback_learning import PlaybackLearningService
from echosense.providers.spotify import SpotifyClient, SpotifyProvider, SpotifyRateLimited
from echosense.repositories.music_dna import MusicDNARepository
from echosense.repositories.provider_connections import (
    ProviderConnection,
    ProviderConnectionRepository,
)

router = APIRouter(prefix="/auth/spotify", tags=["spotify-auth"])

SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_URL = "https://api.spotify.com/v1"
SPOTIFY_PROFILE_URL = f"{SPOTIFY_API_URL}/me"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8001/auth/spotify/callback"
DEFAULT_SCOPES = "user-top-read user-read-recently-played user-read-email user-read-private"
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
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    try:
        imported = SpotifyProvider(SpotifyClient(session, _refresh_session)).import_music_data()
        repository = MusicDNARepository(get_connection_repository().storage)
        repository.save(session.provider_user_id, imported)
        music_dna = MusicDNAGenerator().generate(session.provider_user_id, imported)
        repository.save_profile(music_dna)
        learning = PlaybackLearningService(get_connection_repository().storage)
        recommendation, candidate_slate = learning.rank(
            user_id=session.provider_user_id,
            provider="spotify",
            context="general_listening",
            tracks=[item.track for item in imported.top_tracks],
        )
        decision_id = f"dec_{uuid4().hex}"
        if recommendation is not None:
            get_connection_repository().storage.save_decision_trace(
                decision_id=decision_id,
                user_id=session.provider_user_id,
                context="general_listening",
                context_confidence=music_dna.confidence,
                provider="spotify",
                item_id=recommendation.provider_id,
                factors={
                    "candidate_slate": candidate_slate,
                    "music_dna_confidence": music_dna.confidence,
                    "evidence_count": music_dna.evidence_count,
                },
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
    return music_dna_service.build_provider_profile(
        imported,
        display_name=str(session.profile.get("display_name") or "Spotify listener"),
        music_dna=music_dna,
        recommendation=recommendation,
        decision_id=decision_id if recommendation else None,
    )


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
        storage.append_event(
            event_id=f"evt_{uuid4().hex}",
            event_type="playback.learning.applied",
            user_id=session.provider_user_id,
            trace_id=f"trc_{uuid4().hex}",
            payload=asdict(result),
        )
    return {
        **asdict(result),
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


@router.post("/logout")
def spotify_logout(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> JSONResponse:
    if session_id:
        get_connection_repository().revoke(session_id, "spotify")
    response = JSONResponse({"status": "disconnected"})
    response.delete_cookie(SESSION_COOKIE)
    return response
