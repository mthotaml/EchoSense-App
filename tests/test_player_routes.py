from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from echosense import player_routes, spotify_auth
from echosense.product_app import app
from echosense.repositories.provider_connections import ProviderConnectionRepository
from echosense.storage import Storage

client = TestClient(app)


@pytest.fixture(autouse=True)
def connection_repository(tmp_path, monkeypatch) -> ProviderConnectionRepository:
    repository = ProviderConnectionRepository(
        Storage(f"sqlite:///{tmp_path / 'connections.db'}"),
        Fernet.generate_key(),
    )
    monkeypatch.setattr(spotify_auth, "_connection_repository", repository)
    return repository


def _session(repository: ProviderConnectionRepository) -> str:
    session_id = "player-test-session"
    repository.save(
        spotify_auth.SpotifySession(
            session_id=session_id,
            provider="spotify",
            provider_user_id="spotify-user",
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            profile={"display_name": "Mohan", "product": "premium"},
        )
    )
    return session_id


def test_player_token_returns_current_access_token(
    connection_repository: ProviderConnectionRepository,
) -> None:
    session_id = _session(connection_repository)
    response = client.get(
        "/v1/player/token",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )
    assert response.status_code == 200
    assert response.json()["access_token"] == "access-token"


def test_transfer_playback_targets_browser_device(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
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


def test_play_recommendation_sends_spotify_uri(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
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


def test_token_expiry_during_command_refreshes_and_retries(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "client-secret")
    responses = iter(
        [
            httpx.Response(401, request=httpx.Request("PUT", "https://api.spotify.com")),
            httpx.Response(204, request=httpx.Request("PUT", "https://api.spotify.com")),
        ]
    )
    used_tokens: list[str] = []

    def fake_request(method, url, **kwargs):
        used_tokens.append(kwargs["headers"]["Authorization"])
        return next(responses)

    def fake_refresh(*args, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", spotify_auth.SPOTIFY_TOKEN_URL),
            json={"access_token": "refreshed-token", "expires_in": 3600},
        )

    monkeypatch.setattr(player_routes.httpx, "request", fake_request)
    monkeypatch.setattr(spotify_auth.httpx, "post", fake_refresh)

    response = client.put(
        "/v1/player/pause",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )

    assert response.status_code == 204
    assert used_tokens == ["Bearer access-token", "Bearer refreshed-token"]


def test_rate_limit_preserves_retry_after_and_stable_error(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)

    def fake_request(method, url, **kwargs):
        return httpx.Response(
            429,
            request=httpx.Request(method, url),
            headers={"Retry-After": "7"},
            json={"error": {"status": 429}},
        )

    monkeypatch.setattr(player_routes.httpx, "request", fake_request)

    response = client.get(
        "/v1/player/state",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "7"
    detail = response.json()["detail"]
    assert detail["code"] == "spotify_rate_limited"
    assert detail["retry_after"] == "7"
    assert detail["correlation_id"]
