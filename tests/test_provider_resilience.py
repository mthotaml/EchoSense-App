from datetime import UTC, datetime, timedelta

import httpx
import pytest

from echosense.spotify_resilience import (
    SpotifyRequestDeferred,
    SpotifyRequestGovernor,
    endpoint_group,
)
from echosense.storage import Storage


def test_provider_cooldown_and_snapshot_survive_storage_restart(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'resilience.db'}"
    first = Storage(database_url)
    first.set_provider_cooldown(
        provider="spotify",
        user_id="listener-1",
        cooldown_until=datetime.now(UTC) + timedelta(minutes=5),
        error_code="spotify_rate_limited",
        error_message="Retry later.",
    )
    first.save_provider_snapshot(
        provider="spotify",
        user_id="listener-1",
        resource_key="driving-plan",
        payload={"recommendation": {"id": "track-1"}},
    )

    restarted = Storage(database_url)
    cooldown = restarted.get_provider_cooldown("spotify", "listener-1")
    snapshot = restarted.get_provider_snapshot("spotify", "listener-1", "driving-plan")

    assert cooldown is not None
    assert cooldown["error_code"] == "spotify_rate_limited"
    assert datetime.fromisoformat(cooldown["cooldown_until"]) > datetime.now(UTC)
    assert snapshot is not None
    assert snapshot["payload"]["recommendation"]["id"] == "track-1"
    assert snapshot["exact_match"] is True


def test_provider_snapshot_falls_back_to_latest_verified_plan(tmp_path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'fallback.db'}")
    storage.save_provider_snapshot(
        provider="spotify",
        user_id="listener-1",
        resource_key="general-plan",
        payload={"recommendation": {"id": "track-general"}},
    )

    snapshot = storage.get_provider_snapshot("spotify", "listener-1", "driving-plan")

    assert snapshot is not None
    assert snapshot["payload"]["recommendation"]["id"] == "track-general"
    assert snapshot["exact_match"] is False


def test_request_budget_prevents_provider_call_before_spotify_lockout(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("ECHOSENSE_SPOTIFY_REQUEST_BUDGET", "5")
    storage = Storage(f"sqlite:///{tmp_path / 'budget.db'}")
    governor = SpotifyRequestGovernor(storage, "listener-1")
    for index in range(5):
        ticket = governor.begin("GET", f"/me/tracks/{'a' * 22}?request={index}")
        governor.observe_response(
            ticket,
            httpx.Response(200, request=httpx.Request("GET", "https://api.spotify.test")),
            "/me/tracks/aaaaaaaaaaaaaaaaaaaaaa",
        )

    second_listener = SpotifyRequestGovernor(storage, "listener-2")
    with pytest.raises(SpotifyRequestDeferred) as deferred:
        second_listener.begin("GET", "/me/player")

    assert deferred.value.reason == "LOCAL_REQUEST_BUDGET"
    assert deferred.value.locally_deferred is True
    assert governor.status()["mode"] == "cooldown"
    assert governor.status()["budget"]["requests_in_window"] == 5


def test_quota_exceeded_is_classified_and_explained(tmp_path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'quota.db'}")
    governor = SpotifyRequestGovernor(storage, "listener-1")
    ticket = governor.begin("GET", "/me/top/tracks")
    response = httpx.Response(
        429,
        headers={"Retry-After": "67"},
        json={"error": {"reason": "QUOTA_EXCEEDED", "message": "Quota reached"}},
        request=httpx.Request("GET", "https://api.spotify.test/me/top/tracks"),
    )

    deferred = governor.observe_response(ticket, response, "/me/top/tracks")
    status = governor.status()

    assert deferred is not None
    assert deferred.reason == "QUOTA_EXCEEDED"
    assert deferred.retry_after == 67
    assert status["reason"] == "quota_exceeded"
    assert status["telemetry"]["quota_limits"] == 1
    assert status["telemetry"]["top_endpoints"][0]["endpoint_group"] == "/me/top/tracks"


def test_endpoint_telemetry_never_retains_spotify_item_ids() -> None:
    assert endpoint_group("/me/tracks/6nTiIhLmQ3FWhvrGafw2zj") == "/me/tracks/:id"


def test_repeated_transport_failures_open_short_provider_circuit(tmp_path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'transport.db'}")
    governor = SpotifyRequestGovernor(storage, "listener-1")
    first = governor.begin("GET", "/me/player")
    governor.observe_transport_error(first)
    second = governor.begin("GET", "/me/player")
    governor.observe_transport_error(second)

    status = governor.status()

    assert status["mode"] == "cooldown"
    assert status["reason"] == "transport_circuit_open"
    assert status["retry_after_seconds"] <= 30
    assert status["telemetry"]["transport_errors"] == 2
