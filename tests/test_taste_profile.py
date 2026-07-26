from echosense.apple_music_sync import AppleMusicSyncService, AppleMusicSyncStore
from echosense.providers import FixtureMusicProvider
from echosense.storage import Storage
from echosense.taste_profile import TasteProfileBuilder


def test_taste_profile_is_empty_before_sync(tmp_path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'profile.db'}")

    profile = TasteProfileBuilder(storage).build("new-user")

    assert profile.status == "empty"
    assert profile.evidence_count == 0
    assert profile.confidence == 0.0
    assert profile.top_artists == []


def test_taste_profile_aggregates_synced_signals(tmp_path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'profile.db'}")
    AppleMusicSyncService(FixtureMusicProvider(), AppleMusicSyncStore(storage)).run("profile-user")

    profile = TasteProfileBuilder(storage).build("profile-user")

    assert profile.status == "ready"
    assert profile.evidence_count == 2
    assert profile.library_songs == 1
    assert profile.recent_plays == 1
    assert profile.discovery_ratio == 1.0
    assert profile.confidence == 0.08
    assert [item.name for item in profile.top_artists] == ["Northbound", "Echo Avenue"]
    assert profile.top_artists[0].evidence_count == 2
    assert "exploratory" in profile.summary
