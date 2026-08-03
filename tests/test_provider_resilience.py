from datetime import UTC, datetime, timedelta

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
