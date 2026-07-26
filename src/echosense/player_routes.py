from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel, Field

from echosense.spotify_auth import (
    SESSION_COOKIE,
    SPOTIFY_API_URL,
    _connected_session,
    _refresh_session,
)

router = APIRouter(prefix="/v1/player", tags=["spotify-player"])


class DeviceRequest(BaseModel):
    device_id: str = Field(min_length=1)
    play: bool = True


class PlayRequest(BaseModel):
    device_id: str | None = None
    spotify_uri: str | None = None
    position_ms: int | None = Field(default=None, ge=0)


class SeekRequest(BaseModel):
    position_ms: int = Field(ge=0)
    device_id: str | None = None


class VolumeRequest(BaseModel):
    volume_percent: int = Field(ge=0, le=100)
    device_id: str | None = None


def _spotify_request(
    session_id: str | None,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> httpx.Response:
    session = _connected_session(session_id)
    _refresh_session(session)
    try:
        response = httpx.request(
            method,
            f"{SPOTIFY_API_URL}{path}",
            params=params,
            json=json,
            headers={"Authorization": f"Bearer {session.access_token}"},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "spotify_player_unavailable", "message": str(exc)},
        ) from exc

    if response.status_code >= 400:
        try:
            spotify_error = response.json()
        except ValueError:
            spotify_error = {"message": response.text}
        raise HTTPException(
            status_code=response.status_code,
            detail={"code": "spotify_player_error", "spotify": spotify_error},
        )
    return response


@router.get("/token")
def player_token(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    _refresh_session(session)
    return {
        "access_token": session.access_token,
        "expires_at": session.expires_at,
    }


@router.get("/state", response_model=None)
def player_state(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response | dict[str, object]:
    response = _spotify_request(session_id, "GET", "/me/player")
    if response.status_code == 204 or not response.content:
        return Response(status_code=204)
    return response.json()


@router.get("/devices")
def player_devices(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    return _spotify_request(session_id, "GET", "/me/player/devices").json()


@router.put("/transfer", status_code=204)
def transfer_playback(
    request: DeviceRequest,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    _spotify_request(
        session_id,
        "PUT",
        "/me/player",
        json={"device_ids": [request.device_id], "play": request.play},
    )
    return Response(status_code=204)


@router.put("/play", status_code=204)
def play(
    request: PlayRequest,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    params = {"device_id": request.device_id} if request.device_id else None
    payload: dict[str, object] = {}
    if request.spotify_uri:
        payload["uris"] = [request.spotify_uri]
    if request.position_ms is not None:
        payload["position_ms"] = request.position_ms
    _spotify_request(session_id, "PUT", "/me/player/play", params=params, json=payload or None)
    return Response(status_code=204)


@router.put("/pause", status_code=204)
def pause(
    device_id: str | None = None,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    _spotify_request(
        session_id,
        "PUT",
        "/me/player/pause",
        params={"device_id": device_id} if device_id else None,
    )
    return Response(status_code=204)


@router.post("/next", status_code=204)
def next_track(
    device_id: str | None = None,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    _spotify_request(
        session_id,
        "POST",
        "/me/player/next",
        params={"device_id": device_id} if device_id else None,
    )
    return Response(status_code=204)


@router.post("/previous", status_code=204)
def previous_track(
    device_id: str | None = None,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    _spotify_request(
        session_id,
        "POST",
        "/me/player/previous",
        params={"device_id": device_id} if device_id else None,
    )
    return Response(status_code=204)


@router.put("/seek", status_code=204)
def seek(
    request: SeekRequest,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    params: dict[str, object] = {"position_ms": request.position_ms}
    if request.device_id:
        params["device_id"] = request.device_id
    _spotify_request(session_id, "PUT", "/me/player/seek", params=params)
    return Response(status_code=204)


@router.put("/volume", status_code=204)
def volume(
    request: VolumeRequest,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    params: dict[str, object] = {"volume_percent": request.volume_percent}
    if request.device_id:
        params["device_id"] = request.device_id
    _spotify_request(session_id, "PUT", "/me/player/volume", params=params)
    return Response(status_code=204)
