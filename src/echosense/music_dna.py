from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from echosense.providers.models import MusicDataImport


@dataclass(frozen=True)
class TasteDimension:
    name: str
    score: float
    evidence_count: int


@dataclass(frozen=True)
class MusicDNAProfile:
    user_id: str
    status: str
    confidence: float
    evidence_count: int
    discovery_score: int
    comfort_score: int
    diversity_score: int
    popularity_score: int
    genres: tuple[TasteDimension, ...]
    top_artists: tuple[TasteDimension, ...]
    source_paths: tuple[str, ...]
    generated_at: datetime


class MusicDNAGenerator:
    """Builds explainable provider-neutral taste dimensions from normalized signals."""

    def generate(self, user_id: str, imported: MusicDataImport) -> MusicDNAProfile:
        artists = [artist for artist, _ in imported.top_artists]
        top_tracks = [item.track for item in imported.top_tracks]
        recent_tracks = [item.track for item in imported.recent_tracks]
        evidence_count = len(artists) + len(top_tracks) + len(recent_tracks)

        genre_counts: dict[str, int] = {}
        for artist in artists:
            for genre in artist.genres:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1
        genres = self._dimensions(genre_counts)

        artist_weights: dict[str, int] = {}
        for rank, artist in enumerate(artists, start=1):
            artist_weights[artist.name] = artist_weights.get(artist.name, 0) + max(
                1, len(artists) - rank + 1
            )
        for observation in (*imported.top_tracks, *imported.recent_tracks):
            for artist_name in observation.track.artists:
                artist_weights[artist_name] = artist_weights.get(artist_name, 0) + 1

        top_ids = {track.provider_id for track in top_tracks}
        discoveries = sum(track.provider_id not in top_ids for track in recent_tracks)
        discovery_ratio = discoveries / len(recent_tracks) if recent_tracks else 0.0
        discovery_score = round(discovery_ratio * 100)

        all_tracks = [*top_tracks, *recent_tracks]
        unique_artists = {name for track in all_tracks for name in track.artists}
        diversity_score = (
            round(min(1.0, len(unique_artists) / len(all_tracks)) * 100) if all_tracks else 0
        )
        known_popularity = [
            track.popularity for track in top_tracks if track.popularity is not None
        ]
        popularity_score = (
            round(sum(known_popularity) / len(known_popularity)) if known_popularity else 0
        )
        confidence = round(min(0.95, evidence_count / 40), 3)
        source_paths = tuple(
            dict.fromkeys(
                [
                    *(provenance.source_path for _, provenance in imported.top_artists),
                    *(item.provenance.source_path for item in imported.top_tracks),
                    *(item.provenance.source_path for item in imported.recent_tracks),
                ]
            )
        )
        return MusicDNAProfile(
            user_id=user_id,
            status="ready" if evidence_count else "empty",
            confidence=confidence,
            evidence_count=evidence_count,
            discovery_score=discovery_score,
            comfort_score=100 - discovery_score,
            diversity_score=diversity_score,
            popularity_score=popularity_score,
            genres=genres,
            top_artists=self._dimensions(artist_weights),
            source_paths=source_paths,
            generated_at=imported.imported_at,
        )

    @staticmethod
    def _dimensions(counts: dict[str, int], limit: int = 5) -> tuple[TasteDimension, ...]:
        total = sum(counts.values())
        if total == 0:
            return ()
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
        return tuple(TasteDimension(name, round(count / total, 3), count) for name, count in ranked)
