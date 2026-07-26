from echosense.apple_music_sync import AppleMusicSyncService, AppleMusicSyncStore
from echosense.providers import FixtureMusicProvider
from echosense.storage import Storage


def test_first_sync_persists_normalized_signals_and_counts(tmp_path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'sync.db'}")
    store = AppleMusicSyncStore(storage)

    result = AppleMusicSyncService(FixtureMusicProvider(), store).run("user-sync")

    assert result["status"] == "completed"
    assert result["library_songs"] == 1
    assert result["recent_plays"] == 1
    assert result["total_signals"] == 2

    with storage.connect() as connection:
        rows = storage._execute(
            connection,
            "SELECT signal_type, item_id FROM provider_signals WHERE user_id = %s ORDER BY signal_type",
            ("user-sync",),
        ).fetchall()

    assert [(dict(row)["signal_type"], dict(row)["item_id"]) for row in rows] == [
        ("library_song", "fixture-library-001"),
        ("recent_play", "fixture-recent-001"),
    ]


def test_sync_status_is_not_started_before_first_run(tmp_path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'sync.db'}")

    assert AppleMusicSyncStore(storage).latest("new-user") is None
