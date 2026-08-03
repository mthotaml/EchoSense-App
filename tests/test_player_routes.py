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


def _decision(
    repository: ProviderConnectionRepository,
    *,
    decision_id: str = "decision-1",
    user_id: str = "spotify-user",
    item_id: str = "recommended-track",
) -> None:
    repository.storage.save_decision_trace(
        decision_id=decision_id,
        user_id=user_id,
        context="working",
        context_confidence=0.91,
        provider="spotify",
        item_id=item_id,
        factors={"candidate_slate": []},
    )


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


def test_player_state_restores_recent_snapshot_when_provider_has_no_active_device(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
    live_state = {
        "is_playing": True,
        "progress_ms": 42000,
        "item": {"id": "track-1", "name": "Continuity"},
        "device": {"id": "phone", "name": "Mohan's phone"},
    }
    responses = iter(
        [
            httpx.Response(
                200,
                request=httpx.Request("GET", "https://api.spotify.com"),
                json=live_state,
            ),
            httpx.Response(204, request=httpx.Request("GET", "https://api.spotify.com")),
        ]
    )
    monkeypatch.setattr(player_routes.httpx, "request", lambda *args, **kwargs: next(responses))

    live = client.get(
        "/v1/player/state",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )
    restored = client.get(
        "/v1/player/state",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )

    assert live.json()["continuity"]["source"] == "live"
    assert restored.json()["progress_ms"] == 42000
    assert restored.json()["device"]["id"] == "phone"
    assert restored.json()["continuity"]["source"] == "snapshot"
    assert restored.json()["continuity"]["requires_confirmation"] is True


def test_player_state_uses_last_known_good_during_provider_cooldown(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
    provider_calls = 0

    def live_request(*args, **kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return httpx.Response(
            200,
            request=httpx.Request("GET", "https://api.spotify.com"),
            json={
                "is_playing": True,
                "progress_ms": 12000,
                "item": {"id": "track-lkg", "name": "Verified Playback"},
                "device": {"id": "browser", "name": "EchoSense Browser"},
            },
        )

    monkeypatch.setattr(player_routes.httpx, "request", live_request)
    live = client.get(
        "/v1/player/state",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )
    connection_repository.storage.set_provider_cooldown(
        provider="spotify",
        user_id=player_routes.SpotifyRequestGovernor.APP_SCOPE,
        cooldown_until=datetime.now(UTC) + timedelta(minutes=5),
        error_code="quota_exceeded",
        error_message="Spotify quota exhausted.",
    )

    cached = client.get(
        "/v1/player/state",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )

    assert live.status_code == 200
    assert cached.status_code == 200
    assert cached.json()["item"]["id"] == "track-lkg"
    assert cached.json()["continuity"]["source"] == "last_known_good"
    assert cached.json()["continuity"]["provider_status"]["reason"] == "QUOTA_EXCEEDED"
    assert provider_calls == 1


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


def test_devices_are_normalized_and_restricted_state_is_preserved(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
    payload = {
        "devices": [
            {
                "id": "phone",
                "name": "Mohan's phone",
                "type": "smartphone",
                "is_active": True,
                "is_restricted": False,
                "volume_percent": 64,
            },
            {
                "id": "speaker",
                "name": "Office speaker",
                "type": "speaker",
                "is_restricted": True,
            },
        ]
    }
    monkeypatch.setattr(
        player_routes.httpx,
        "request",
        lambda method, url, **kwargs: httpx.Response(
            200, request=httpx.Request(method, url), json=payload
        ),
    )
    response = client.get(
        "/v1/player/devices",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )

    assert response.json()["items"][0]["active"] is True
    assert response.json()["items"][0]["volume_percent"] == 64
    assert response.json()["items"][1]["restricted"] is True


def test_queue_is_ordered_and_add_command_is_idempotent(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == "GET":
            return httpx.Response(
                200,
                request=httpx.Request(method, url),
                json={
                    "currently_playing": {"id": "now", "name": "Now", "artists": []},
                    "queue": [
                        {"id": "next-1", "name": "First", "artists": []},
                        {"id": "next-2", "name": "Second", "artists": []},
                    ],
                },
            )
        return httpx.Response(204, request=httpx.Request(method, url))

    monkeypatch.setattr(player_routes.httpx, "request", fake_request)
    queue = client.get("/v1/player/queue", cookies={spotify_auth.SESSION_COOKIE: session_id})
    payload = {"item_id": "next-3", "command_id": "queue-command-1"}
    first = client.post(
        "/v1/player/queue",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json=payload,
    )
    duplicate = client.post(
        "/v1/player/queue",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json=payload,
    )

    assert [item["id"] for item in queue.json()["up_next"]] == ["next-1", "next-2"]
    assert first.json()["applied"] is True
    assert duplicate.json()["applied"] is False
    assert len([call for call in calls if call[0] == "POST"]) == 1


def test_queue_rejects_item_already_present_under_a_new_command(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return httpx.Response(
            200,
            request=httpx.Request(method, url),
            json={
                "currently_playing": {"id": "now", "name": "Now", "artists": []},
                "queue": [{"id": "duplicate", "name": "Already next", "artists": []}],
            },
        )

    monkeypatch.setattr(player_routes.httpx, "request", fake_request)
    response = client.post(
        "/v1/player/queue",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json={"item_id": "duplicate", "command_id": "new-command"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "already_queued",
        "item_id": "duplicate",
        "applied": False,
    }
    assert [call[0] for call in calls] == ["GET"]


def test_shuffle_and_repeat_commands_are_device_scoped(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((url, kwargs["params"]))
        return httpx.Response(204, request=httpx.Request(method, url))

    monkeypatch.setattr(player_routes.httpx, "request", fake_request)
    shuffle = client.put(
        "/v1/player/shuffle",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json={"enabled": True, "device_id": "browser"},
    )
    repeat = client.put(
        "/v1/player/repeat",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json={"mode": "track", "device_id": "browser"},
    )

    assert shuffle.status_code == 204
    assert repeat.status_code == 204
    assert calls[0][1] == {"state": "true", "device_id": "browser"}
    assert calls[1][1] == {"state": "track", "device_id": "browser"}


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


def test_context_playback_resolves_owned_decision_and_records_after_success(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
    _decision(connection_repository)
    requests = []

    def fake_request(method, url, **kwargs):
        requests.append({"method": method, "url": url, **kwargs})
        return httpx.Response(204, request=httpx.Request(method, url))

    monkeypatch.setattr(player_routes.httpx, "request", fake_request)
    payload = {"device_id": "browser-device", "outcome_id": "played-outcome-1"}

    first = client.put(
        "/v1/player/recommendations/decision-1/play",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json=payload,
    )
    duplicate = client.put(
        "/v1/player/recommendations/decision-1/play",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json=payload,
    )

    assert first.status_code == 200
    assert first.json()["item_id"] == "recommended-track"
    assert first.json()["learning"]["signal"] == "played"
    assert first.json()["learning"]["applied"] is True
    assert duplicate.json()["learning"]["applied"] is False
    assert requests[0]["params"] == {"state": "false", "device_id": "browser-device"}
    assert requests[1]["params"] == {"state": "off", "device_id": "browser-device"}
    assert requests[2]["params"] == {"device_id": "browser-device"}
    assert requests[2]["json"] == {"uris": ["spotify:track:recommended-track"]}


def test_context_playback_installs_owned_dna_sequence_in_order(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
    _decision(connection_repository)
    _decision(
        connection_repository,
        decision_id="decision-2",
        item_id="second-dna-track",
    )
    _decision(
        connection_repository,
        decision_id="decision-3",
        item_id="third-dna-track",
    )
    captured: list[dict[str, object]] = []

    def fake_request(method, url, **kwargs):
        captured.append({"method": method, "url": url, **kwargs})
        return httpx.Response(204, request=httpx.Request(method, url))

    monkeypatch.setattr(player_routes.httpx, "request", fake_request)
    response = client.put(
        "/v1/player/recommendations/decision-1/play",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json={
            "device_id": "browser-device",
            "outcome_id": "sequence-outcome",
            "continuation_decision_ids": ["decision-2", "decision-3"],
        },
    )

    assert response.status_code == 200
    assert response.json()["sequence_item_ids"] == [
        "recommended-track",
        "second-dna-track",
        "third-dna-track",
    ]
    assert captured[0]["params"] == {"state": "false", "device_id": "browser-device"}
    assert captured[1]["params"] == {"state": "off", "device_id": "browser-device"}
    assert captured[2]["json"] == {
        "uris": [
            "spotify:track:recommended-track",
            "spotify:track:second-dna-track",
            "spotify:track:third-dna-track",
        ]
    }
    assert response.json()["playback_mode"] == {"shuffle": False, "repeat": "off"}


def test_context_playback_rejects_unowned_dna_sequence(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
    _decision(connection_repository)
    _decision(
        connection_repository,
        decision_id="unowned-decision",
        user_id="another-user",
        item_id="unowned-track",
    )
    monkeypatch.setattr(
        player_routes.httpx,
        "request",
        lambda *args, **kwargs: pytest.fail("Spotify must not receive a mixed-owner sequence"),
    )

    response = client.put(
        "/v1/player/recommendations/decision-1/play",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json={
            "device_id": "browser-device",
            "outcome_id": "unowned-sequence",
            "continuation_decision_ids": ["unowned-decision"],
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "recommendation_decision_not_found"


def test_context_playback_hides_cross_user_decisions(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
    _decision(connection_repository, user_id="another-user")
    monkeypatch.setattr(
        player_routes.httpx,
        "request",
        lambda *args, **kwargs: pytest.fail("Spotify must not receive an unowned decision"),
    )

    response = client.put(
        "/v1/player/recommendations/decision-1/play",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json={"device_id": "browser-device", "outcome_id": "unowned-outcome"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "recommendation_decision_not_found"


def test_context_playback_failure_does_not_create_learning_evidence(
    monkeypatch, connection_repository: ProviderConnectionRepository
) -> None:
    session_id = _session(connection_repository)
    _decision(connection_repository)

    def fake_request(method, url, **kwargs):
        return httpx.Response(
            503,
            request=httpx.Request(method, url),
            json={"error": {"message": "device unavailable"}},
        )

    monkeypatch.setattr(player_routes.httpx, "request", fake_request)
    response = client.put(
        "/v1/player/recommendations/decision-1/play",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json={"device_id": "browser-device", "outcome_id": "failed-outcome"},
    )

    assert response.status_code == 503
    with connection_repository.storage.connect() as database:
        row = connection_repository.storage._execute(
            database,
            "SELECT COUNT(*) AS count FROM playback_learning_outcomes",
        ).fetchone()
    assert dict(row)["count"] == 0


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
