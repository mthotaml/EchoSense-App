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
