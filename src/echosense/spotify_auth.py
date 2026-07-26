from __future__ import annotations

import base64
import hashlib
import os
import secrets
from collections import Counter
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

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


def _refresh_session(session: SpotifySession) -> None:
    if session.expires_at > datetime.now(UTC) + timedelta(seconds=30):
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


def _spotify_get(
    session: SpotifySession, path: str, params: dict[str, object] | None = None
) -> dict[str, object]:
    _refresh_session(session)
    try:
        response = httpx.get(
            f"{SPOTIFY_API_URL}{path}",
            params=params,
            headers={"Authorization": f"Bearer {session.access_token}"},
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "spotify_api_failed", "message": str(exc)},
        ) from exc


def _connected_session(session_id: str | None) -> SpotifySession:
    session = get_connection_repository().get(session_id, "spotify") if session_id else None
    if session is None:
        raise HTTPException(status_code=401, detail={"code": "spotify_not_connected"})
    return session


def _artist_summary(item: dict[str, object]) -> dict[str, object]:
    images = item.get("images") or []
    image_url = images[0].get("url") if isinstance(images, list) and images else None
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "genres": item.get("genres", []),
        "popularity": item.get("popularity"),
        "image_url": image_url,
        "spotify_url": (item.get("external_urls") or {}).get("spotify"),
    }


def _track_summary(item: dict[str, object]) -> dict[str, object]:
    artists = item.get("artists") or []
    album = item.get("album") or {}
    images = album.get("images") or [] if isinstance(album, dict) else []
    image_url = images[0].get("url") if isinstance(images, list) and images else None
    return {
        "id": item.get("id"),
        "title": item.get("name"),
        "artist": artists[0].get("name")
        if isinstance(artists, list) and artists
        else "Unknown artist",
        "artists": [artist.get("name") for artist in artists if isinstance(artist, dict)],
        "album": album.get("name") if isinstance(album, dict) else None,
        "popularity": item.get("popularity"),
        "image_url": image_url,
        "spotify_url": (item.get("external_urls") or {}).get("spotify"),
    }


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
    top_artists_payload = _spotify_get(
        session, "/me/top/artists", {"limit": 10, "time_range": "medium_term"}
    )
    top_tracks_payload = _spotify_get(
        session, "/me/top/tracks", {"limit": 10, "time_range": "medium_term"}
    )
    recent_payload = _spotify_get(session, "/me/player/recently-played", {"limit": 20})

    artist_items = top_artists_payload.get("items") or []
    track_items = top_tracks_payload.get("items") or []
    recent_items = recent_payload.get("items") or []
    top_artists = [_artist_summary(item) for item in artist_items if isinstance(item, dict)]
    top_tracks = [_track_summary(item) for item in track_items if isinstance(item, dict)]
    recent_tracks = [
        _track_summary(item["track"])
        for item in recent_items
        if isinstance(item, dict) and isinstance(item.get("track"), dict)
    ]

    genre_counts = Counter(
        genre
        for artist in top_artists
        for genre in artist.get("genres", [])
        if isinstance(genre, str)
    )
    genres = [{"name": name.title(), "score": count} for name, count in genre_counts.most_common(5)]
    recommendation = top_tracks[0] if top_tracks else (recent_tracks[0] if recent_tracks else None)
    leading_artists = [artist["name"] for artist in top_artists[:3] if artist.get("name")]
    reason = (
        f"This fits the pattern formed by {', '.join(leading_artists)}."
        if leading_artists
        else "This reflects your recent Spotify listening."
    )
    average_popularity = (
        round(sum(int(track.get("popularity") or 0) for track in top_tracks) / len(top_tracks))
        if top_tracks
        else 0
    )

    return {
        "profile": {
            "display_name": session.profile.get("display_name") or "Spotify listener",
            "genres": genres,
            "top_artists": top_artists,
            "top_tracks": top_tracks,
            "recent_tracks": recent_tracks,
            "average_popularity": average_popularity,
        },
        "recommendation": (
            {**recommendation, "reason": reason, "match_score": 96} if recommendation else None
        ),
        "insight": (
            f"Your strongest current signal is {genres[0]['name']}."
            if genres
            else "EchoSense is still collecting enough listening history to identify your strongest signal."
        ),
        "timeline": [artist["name"] for artist in top_artists[:4] if artist.get("name")],
        "generated_at": datetime.now(UTC),
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
