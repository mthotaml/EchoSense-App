from datetime import UTC, datetime

from echosense.listening_context import ListeningContextService
from echosense.providers.models import (
    Artist,
    MusicDataImport,
    ProviderProvenance,
    Track,
    TrackObservation,
)


def test_context_fit_uses_normalized_artist_genres() -> None:
    now = datetime(2026, 7, 26, tzinfo=UTC)
    provenance = ProviderProvenance("spotify", "/me/top/tracks", now, 1)
    imported = MusicDataImport(
        provider="spotify",
        top_artists=(
            (
                Artist("spotify", "artist-1", "Focus Artist", ("ambient", "indie rock")),
                ProviderProvenance("spotify", "/me/top/artists", now, 1),
            ),
        ),
        top_tracks=(
            TrackObservation(
                Track("spotify", "track-1", "Focus", ("Focus Artist",)),
                provenance,
            ),
        ),
        recent_tracks=(),
        imported_at=now,
    )

    working = ListeningContextService().score(imported, "working")["track-1"]
    social = ListeningContextService().score(imported, "social")["track-1"]

    assert working.score == 0.5
    assert working.matched_genres == ("ambient",)
    assert social.score == 0.0
    assert social.matched_genres == ()
    assert ListeningContextService.ranking_context("general") == "general_listening"
