from datetime import UTC, datetime

from echosense.music_dna import MusicDNAGenerator
from echosense.providers.models import (
    Artist,
    MusicDataImport,
    ProviderProvenance,
    Track,
    TrackObservation,
)
from echosense.repositories.music_dna import MusicDNARepository
from echosense.storage import Storage


def observation(
    provider_id: str,
    artist: str,
    path: str,
    rank: int,
    *,
    popularity: int | None = None,
) -> TrackObservation:
    now = datetime(2026, 7, 25, tzinfo=UTC)
    return TrackObservation(
        Track("spotify", provider_id, provider_id, (artist,), popularity=popularity),
        ProviderProvenance("spotify", path, now, rank),
        now,
    )


def imported_data() -> MusicDataImport:
    now = datetime(2026, 7, 25, tzinfo=UTC)
    return MusicDataImport(
        provider="spotify",
        top_artists=(
            (
                Artist("spotify", "a1", "Artist One", ("ambient", "indie")),
                ProviderProvenance("spotify", "/me/top/artists", now, 1),
            ),
            (
                Artist("spotify", "a2", "Artist Two", ("ambient",)),
                ProviderProvenance("spotify", "/me/top/artists", now, 2),
            ),
        ),
        top_tracks=(
            observation("t1", "Artist One", "/me/top/tracks", 1, popularity=70),
            observation("t2", "Artist One", "/me/top/tracks", 2, popularity=50),
        ),
        recent_tracks=(
            observation("t1", "Artist One", "/me/player/recently-played", 1),
            observation("t3", "Artist Three", "/me/player/recently-played", 2),
        ),
        imported_at=now,
    )


def test_music_dna_is_evidence_backed_and_provider_neutral() -> None:
    profile = MusicDNAGenerator().generate("user-1", imported_data())

    assert profile.status == "ready"
    assert profile.evidence_count == 6
    assert profile.confidence == 0.15
    assert profile.discovery_score == 50
    assert profile.comfort_score == 50
    assert profile.diversity_score == 50
    assert profile.popularity_score == 60
    assert profile.genres[0].name == "ambient"
    assert profile.genres[0].evidence_count == 2
    assert profile.source_paths == (
        "/me/top/artists",
        "/me/top/tracks",
        "/me/player/recently-played",
    )
    assert not hasattr(profile, "spotify")


def test_music_dna_profile_round_trips_through_persistence(tmp_path) -> None:
    repository = MusicDNARepository(Storage(f"sqlite:///{tmp_path / 'dna.db'}"))
    profile = MusicDNAGenerator().generate("user-1", imported_data())

    repository.save_profile(profile)

    assert repository.get_profile("user-1") == profile
