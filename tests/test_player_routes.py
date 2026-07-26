from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient

from echosense import player_routes, spotify_auth
from echosense.product_app import app

client = TestClient(app)


def _session() -> str:
    session_id = "player-test-session"
    spotify_auth._sessions[session_id] = spotify_auth.SpotifySession(
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        profile={"display_name": "Mohan", "product": "premium"},
    )
    return session_id


def test_player_token_returns_current_access_token() -> None:
    session_id = _session()
    response = client.get(
        "/v1/player/token",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )
    assert response.status_code == 200
    assert response.json()["access_token"] == "access-token"
    spotify_auth._sessions.pop(session_id, None)


def test_transfer_playback_targets_browser_device(monkeypatch) -> None:
    session_id = _session()
    captured: dict[str, object] = {}

    def fake_request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return httpx.Response(204, request=httpx.Request(method, url))

    monkeypatch.setattr(player_routes.httpx, "request", fake_request)
    response = client.put(
        "/v1/player/transfer",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json={"device_id": "browser-device", "play": False},
    )

    assert response.status_code == 204
    assert captured["method"] == "PUT"
    assert captured["json"] == {"device_ids": ["browser-device"], "play": False}
    spotify_auth._sessions.pop(session_id, None)


def test_play_recommendation_sends_spotify_uri(monkeypatch) -> None:
    session_id = _session()
    captured: dict[str, object] = {}

    def fake_request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return httpx.Response(204, request=httpx.Request(method, url))

    monkeypatch.setattr(player_routes.httpx, "request", fake_request)
    response = client.put(
        "/v1/player/play",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json={"device_id": "browser-device", "spotify_uri": "spotify:track:abc"},
    )

    assert response.status_code == 204
    assert captured["params"] == {"device_id": "browser-device"}
    assert captured["json"] == {"uris": ["spotify:track:abc"]}
    spotify_auth._sessions.pop(session_id, None)
