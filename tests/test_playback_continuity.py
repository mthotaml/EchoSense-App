from datetime import UTC, datetime, timedelta

from echosense.playback_continuity import PlaybackContinuityStore
from echosense.storage import Storage


def test_snapshot_is_versioned_and_expires(tmp_path) -> None:
    store = PlaybackContinuityStore(
        Storage(f"sqlite:///{tmp_path / 'continuity.db'}"),
        max_age=timedelta(minutes=15),
    )
    now = datetime(2026, 7, 26, 12, tzinfo=UTC)

    first = store.observe("user", "spotify", {"progress_ms": 1000}, now=now)
    second = store.observe("user", "spotify", {"progress_ms": 2000}, now=now)

    assert first.revision == 1
    assert second.revision == 2
    assert store.latest("user", "spotify", now=now).state["progress_ms"] == 2000
    assert store.latest("user", "spotify", now=now + timedelta(minutes=16)) is None
