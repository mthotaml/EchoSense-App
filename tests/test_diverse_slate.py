from echosense.diverse_slate import DiverseSlateService
from echosense.providers.models import Track


def _track(item_id: str, title: str, artist: str, *, isrc: str | None = None) -> Track:
    return Track("spotify", item_id, title, (artist,), isrc=isrc)


def test_slate_deduplicates_recordings_and_diversifies_adjacent_artists() -> None:
    tracks = [
        _track("one", "First", "Artist A", isrc="shared"),
        _track("duplicate", "First Remaster", "Artist A", isrc="shared"),
        _track("two", "Second", "Artist A"),
        _track("three", "Third", "Artist B"),
        _track("four", "Fourth", "Artist C"),
    ]
    ranked = [
        {
            "item_id": track.provider_id,
            "ranking_score": 1 - index * 0.1,
            "context_fit": 0.5,
            "preference_weight": 0.0,
        }
        for index, track in enumerate(tracks)
    ]

    slate = DiverseSlateService().build(tracks, ranked, limit=4)

    assert [item.track.provider_id for item in slate] == ["one", "three", "four", "two"]
    assert len({item.track.isrc for item in slate if item.track.isrc}) == 1
    assert all(
        left.track.primary_artist != right.track.primary_artist
        for left, right in zip(slate, slate[1:])
    )


def test_slate_excludes_live_queue_items() -> None:
    tracks = [_track("queued", "Queued", "A"), _track("fresh", "Fresh", "B")]
    ranked = [
        {"item_id": "queued", "ranking_score": 1.0},
        {"item_id": "fresh", "ranking_score": 0.9},
    ]

    slate = DiverseSlateService().build(tracks, ranked, excluded_ids={"queued"})

    assert [item.track.provider_id for item in slate] == ["fresh"]


def test_default_music_dna_round_contains_six_tracks() -> None:
    tracks = [
        _track(f"track-{index}", f"Track {index}", f"Artist {index}")
        for index in range(1, 8)
    ]
    ranked = [
        {"item_id": track.provider_id, "ranking_score": 1 - index * 0.05}
        for index, track in enumerate(tracks)
    ]

    slate = DiverseSlateService().build(tracks, ranked)

    assert len(slate) == 6
    assert [item.rank for item in slate] == [1, 2, 3, 4, 5, 6]
