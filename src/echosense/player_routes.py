from __future__ import annotations

import os
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel, Field

from echosense.playback_continuity import PlaybackContinuityStore
from echosense.spotify_auth import (
    SESSION_COOKIE,
    SPOTIFY_API_URL,
    SpotifyFeedbackRequest,
    _connected_session,
    _refresh_session,
    get_connection_repository,
    spotify_feedback,
)
from echosense.spotify_resilience import SpotifyRequestDeferred, SpotifyRequestGovernor

router = APIRouter(prefix="/v1/player", tags=["spotify-player"])


class DeviceRequest(BaseModel):
    device_id: str = Field(min_length=1)
    play: bool = True


class PlayRequest(BaseModel):
    device_id: str | None = None
    spotify_uri: str | None = None
    position_ms: int | None = Field(default=None, ge=0)


class RecommendationPlayRequest(BaseModel):
    device_id: str = Field(min_length=1)
    outcome_id: str = Field(min_length=1)
    continuation_decision_ids: list[str] = Field(default_factory=list, max_length=49)


class SeekRequest(BaseModel):
    position_ms: int = Field(ge=0)
    device_id: str | None = None


class VolumeRequest(BaseModel):
    volume_percent: int = Field(ge=0, le=100)
    device_id: str | None = None


class QueueRequest(BaseModel):
    item_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    device_id: str | None = None


class ShuffleRequest(BaseModel):
    enabled: bool
    device_id: str | None = None


class RepeatRequest(BaseModel):
    mode: Literal["off", "track", "context"]
    device_id: str | None = None


def _queue_track(item: object) -> dict[str, object] | None:
    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
        return None
    artists = item.get("artists") if isinstance(item.get("artists"), list) else []
    return {
        "id": item["id"],
        "title": item.get("name") or "Unavailable track",
        "artists": [
            artist["name"]
            for artist in artists
            if isinstance(artist, dict) and isinstance(artist.get("name"), str)
        ],
        "playable": item.get("is_playable") is not False and item.get("is_local") is not True,
    }


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
    governor = SpotifyRequestGovernor(get_connection_repository().storage, session.provider_user_id)

    def deferred_error(exc: SpotifyRequestDeferred) -> HTTPException:
        code = {
            "QUOTA_EXCEEDED": "spotify_quota_exceeded",
            "RATE_LIMIT_EXCEEDED": "spotify_rate_limited",
        }.get(exc.reason, "spotify_request_deferred")
        return HTTPException(
            status_code=429,
            detail={
                "code": code,
                "reason": exc.reason,
                "endpoint": exc.endpoint,
                "retry_after_seconds": exc.retry_after,
                "retry_after": str(exc.retry_after),
                "locally_deferred": exc.locally_deferred,
                "correlation_id": uuid4().hex,
                "message": (
                    "EchoSense is waiting for Spotify's quota to resume. Reconnecting is not needed."
                    if code == "spotify_quota_exceeded"
                    else "EchoSense paused Spotify requests to prevent a longer lockout."
                ),
            },
            headers={"Retry-After": str(exc.retry_after)},
        )

    def send() -> httpx.Response:
        try:
            ticket = governor.begin(method, path, request_class="player")
        except SpotifyRequestDeferred as exc:
            raise deferred_error(exc) from exc
        try:
            response = httpx.request(
                method,
                f"{SPOTIFY_API_URL}{path}",
                params=params,
                json=json,
                headers={"Authorization": f"Bearer {session.access_token}"},
                timeout=max(
                    3.0,
                    min(
                        15.0,
                        float(os.getenv("ECHOSENSE_SPOTIFY_TIMEOUT_SECONDS", "8")),
                    ),
                ),
            )
            deferred = governor.observe_response(ticket, response, path)
            if deferred:
                raise deferred_error(deferred)
            return response
        except httpx.HTTPError as exc:
            governor.observe_transport_error(ticket)
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "spotify_player_unavailable",
                    "message": str(exc),
                    "correlation_id": uuid4().hex,
                },
            ) from exc

    response = send()
    if response.status_code == 401 and session.refresh_token:
        _refresh_session(session, force=True)
        response = send()

    if response.status_code >= 400:
        correlation_id = uuid4().hex
        retry_after = response.headers.get("Retry-After")
        try:
            spotify_error = response.json()
        except ValueError:
            spotify_error = {"message": response.text}
        if response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "spotify_rate_limited",
                    "retry_after": retry_after,
                    "correlation_id": correlation_id,
                },
                headers={"Retry-After": retry_after or "1"},
            )
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "code": "spotify_player_error",
                "spotify": spotify_error,
                "correlation_id": correlation_id,
            },
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
    session = _connected_session(session_id)
    continuity = PlaybackContinuityStore(get_connection_repository().storage)
    try:
        response = _spotify_request(session_id, "GET", "/me/player")
    except HTTPException as exc:
        if exc.status_code != 429:
            raise
        snapshot = continuity.latest(session.provider_user_id, "spotify")
        if snapshot:
            return {
                **snapshot.state,
                "continuity": {
                    "source": "last_known_good",
                    "revision": snapshot.revision,
                    "observed_at": snapshot.observed_at.isoformat(),
                    "requires_confirmation": True,
                    "provider_status": exc.detail,
                },
            }
        raise
    if response.status_code == 204 or not response.content:
        snapshot = continuity.latest(session.provider_user_id, "spotify")
        if snapshot:
            return {
                **snapshot.state,
                "continuity": {
                    "source": "snapshot",
                    "revision": snapshot.revision,
                    "observed_at": snapshot.observed_at.isoformat(),
                    "requires_confirmation": True,
                },
            }
        return Response(status_code=204)
    state = response.json()
    snapshot = continuity.observe(session.provider_user_id, "spotify", state)
    return {
        **state,
        "continuity": {
            "source": "live",
            "revision": snapshot.revision,
            "observed_at": snapshot.observed_at.isoformat(),
            "requires_confirmation": False,
        },
    }


@router.get("/devices")
def player_devices(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    payload = _spotify_request(session_id, "GET", "/me/player/devices").json()
    devices = payload.get("devices") if isinstance(payload, dict) else None
    if not isinstance(devices, list):
        raise HTTPException(
            status_code=502,
            detail={"code": "spotify_devices_invalid", "correlation_id": uuid4().hex},
        )
    return {
        "items": [
            {
                "id": device.get("id"),
                "name": device.get("name") or "Unnamed device",
                "type": device.get("type") or "unknown",
                "active": device.get("is_active") is True,
                "restricted": device.get("is_restricted") is True,
                "volume_percent": device.get("volume_percent"),
            }
            for device in devices
            if isinstance(device, dict) and isinstance(device.get("id"), str)
        ]
    }


@router.get("/queue")
def player_queue(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    payload = _spotify_request(session_id, "GET", "/me/player/queue").json()
    current = _queue_track(payload.get("currently_playing"))
    raw_queue = payload.get("queue") if isinstance(payload.get("queue"), list) else []
    return {
        "current": current,
        "up_next": [track for item in raw_queue if (track := _queue_track(item)) is not None],
    }


@router.post("/queue")
def add_to_queue(
    request: QueueRequest,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    storage = get_connection_repository().storage
    with storage.connect() as database:
        storage._execute(
            database,
            """
            CREATE TABLE IF NOT EXISTS playback_queue_commands (
                user_id TEXT NOT NULL,
                command_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                PRIMARY KEY (user_id, command_id)
            )
            """,
        )
        existing = storage._execute(
            database,
            """
            SELECT item_id FROM playback_queue_commands
            WHERE user_id = %s AND command_id = %s
            """,
            (session.provider_user_id, request.command_id),
        ).fetchone()
    if existing:
        if dict(existing)["item_id"] != request.item_id:
            raise HTTPException(status_code=409, detail={"code": "queue_command_conflict"})
        return {"status": "already_queued", "item_id": request.item_id, "applied": False}
    queue_payload = _spotify_request(session_id, "GET", "/me/player/queue").json()
    queued_items = [queue_payload.get("currently_playing")]
    if isinstance(queue_payload.get("queue"), list):
        queued_items.extend(queue_payload["queue"])
    if any(isinstance(item, dict) and item.get("id") == request.item_id for item in queued_items):
        return {
            "status": "already_queued",
            "item_id": request.item_id,
            "applied": False,
        }
    params: dict[str, object] = {"uri": f"spotify:track:{request.item_id}"}
    if request.device_id:
        params["device_id"] = request.device_id
    _spotify_request(session_id, "POST", "/me/player/queue", params=params)
    with storage.connect() as database:
        storage._execute(
            database,
            """
            INSERT INTO playback_queue_commands (user_id, command_id, item_id)
            VALUES (%s, %s, %s)
            """,
            (session.provider_user_id, request.command_id, request.item_id),
        )
    return {"status": "queued", "item_id": request.item_id, "applied": True}


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


@router.put("/recommendations/{decision_id}/play")
def play_recommendation(
    decision_id: str,
    request: RecommendationPlayRequest,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, object]:
    session = _connected_session(session_id)
    decision_ids = list(dict.fromkeys([decision_id, *request.continuation_decision_ids]))
    traces = [
        get_connection_repository().storage.get_decision_trace(candidate_decision_id)
        for candidate_decision_id in decision_ids
    ]
    if any(
        trace is None
        or trace["user_id"] != session.provider_user_id
        or trace["provider"] != "spotify"
        for trace in traces
    ):
        raise HTTPException(
            status_code=404,
            detail={"code": "recommendation_decision_not_found"},
        )
    item_ids = list(dict.fromkeys(str(trace["item_id"]) for trace in traces if trace is not None))
    item_id = item_ids[0]
    playback_params = {"device_id": request.device_id}
    _spotify_request(
        session_id,
        "PUT",
        "/me/player/shuffle",
        params={"state": "false", **playback_params},
    )
    _spotify_request(
        session_id,
        "PUT",
        "/me/player/repeat",
        params={"state": "off", **playback_params},
    )
    _spotify_request(
        session_id,
        "PUT",
        "/me/player/play",
        params=playback_params,
        json={"uris": [f"spotify:track:{candidate_item_id}" for candidate_item_id in item_ids]},
    )
    learning = spotify_feedback(
        SpotifyFeedbackRequest(
            outcome_id=request.outcome_id,
            decision_id=decision_id,
            signal="played",
        ),
        session_id,
    )
    return {
        "status": "playing",
        "decision_id": decision_id,
        "provider": "spotify",
        "item_id": item_id,
        "sequence_item_ids": item_ids,
        "playback_mode": {"shuffle": False, "repeat": "off"},
        "learning": learning,
    }


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


@router.put("/shuffle", status_code=204)
def shuffle(
    request: ShuffleRequest,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    params: dict[str, object] = {"state": str(request.enabled).lower()}
    if request.device_id:
        params["device_id"] = request.device_id
    _spotify_request(session_id, "PUT", "/me/player/shuffle", params=params)
    return Response(status_code=204)


@router.put("/repeat", status_code=204)
def repeat(
    request: RepeatRequest,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    params: dict[str, object] = {"state": request.mode}
    if request.device_id:
        params["device_id"] = request.device_id
    _spotify_request(session_id, "PUT", "/me/player/repeat", params=params)
    return Response(status_code=204)
