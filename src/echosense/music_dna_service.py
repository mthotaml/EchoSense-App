from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timezone
from typing import Literal
from uuid import uuid4

from echosense.music_dna import MusicDNAProfile
from echosense.providers.models import Artist, MusicDataImport, Track

Reaction = Literal["love", "not_for_me", "save", "play"]


class MusicDNAService:
    """Product-facing service boundary for Music DNA demo data.

    The UI depends on this interface rather than a specific streaming provider.
    Later, these methods can delegate to the recommendation engine and Apple
    Music adapter without changing the product routes.
    """

    def __init__(self) -> None:
        self._feedback_events: list[dict[str, str]] = []

    def build_provider_profile(
        self,
        imported: MusicDataImport,
        *,
        display_name: str,
        music_dna: MusicDNAProfile | None = None,
        recommendation: Track | None = None,
        decision_id: str | None = None,
    ) -> dict[str, object]:
        artists = [artist for artist, _ in imported.top_artists]
        top_tracks = [item.track for item in imported.top_tracks]
        recent_tracks = [item.track for item in imported.recent_tracks]
        genre_counts = Counter(genre for artist in artists for genre in artist.genres)
        genres = [
            {"name": name.title(), "score": count} for name, count in genre_counts.most_common(5)
        ]
        recommendation = recommendation or (
            top_tracks[0] if top_tracks else (recent_tracks[0] if recent_tracks else None)
        )
        leading_artists = [artist.name for artist in artists[:3]]
        reason = (
            f"This fits the pattern formed by {', '.join(leading_artists)}."
            if leading_artists
            else f"This reflects your recent {imported.provider.title()} listening."
        )
        average_popularity = (
            round(sum(track.popularity or 0 for track in top_tracks) / len(top_tracks))
            if top_tracks
            else 0
        )
        return {
            "profile": {
                "display_name": display_name,
                "genres": genres,
                "top_artists": [self._artist_view(artist) for artist in artists],
                "top_tracks": [self._track_view(track) for track in top_tracks],
                "recent_tracks": [self._track_view(track) for track in recent_tracks],
                "average_popularity": average_popularity,
                "confidence": music_dna.confidence if music_dna else 0.0,
                "discovery_score": music_dna.discovery_score if music_dna else 0,
                "comfort_score": music_dna.comfort_score if music_dna else 0,
                "diversity_score": music_dna.diversity_score if music_dna else 0,
                "evidence_count": music_dna.evidence_count if music_dna else 0,
                "evidence_sources": list(music_dna.source_paths) if music_dna else [],
            },
            "recommendation": (
                {
                    **self._track_view(recommendation),
                    "decision_id": decision_id,
                    "reason": reason,
                    "match_score": 96,
                }
                if recommendation
                else None
            ),
            "insight": (
                f"Your strongest current signal is {genres[0]['name']}."
                if genres
                else "EchoSense is still collecting enough listening history to identify your strongest signal."
            ),
            "timeline": leading_artists[:4],
            "generated_at": datetime.now(UTC),
        }

    @staticmethod
    def _artist_view(artist: Artist) -> dict[str, object]:
        return {
            "id": artist.provider_id,
            "name": artist.name,
            "genres": list(artist.genres),
            "popularity": artist.popularity,
            "image_url": artist.image_url,
            f"{artist.provider}_url": artist.external_url,
        }

    @staticmethod
    def _track_view(track: Track) -> dict[str, object]:
        return {
            "id": track.provider_id,
            "title": track.title,
            "artist": track.primary_artist,
            "artists": list(track.artists),
            "album": track.album,
            "popularity": track.popularity,
            "image_url": track.image_url,
            f"{track.provider}_url": track.external_url,
        }

    def get_profile(self) -> dict[str, object]:
        return {
            "user_id": "demo-user",
            "display_name": "Alex",
            "status": "ready",
            "confidence": 0.91,
            "discovery_score": 78,
            "comfort_score": 64,
            "genres": [
                {"name": "Indie", "score": 88},
                {"name": "Electronic", "score": 74},
                {"name": "Ambient", "score": 61},
            ],
            "top_artists": ["Bon Iver", "ODESZA", "Radiohead"],
            "recent_shift": "Your listening has become calmer and more atmospheric this week.",
            "coach": "Stay with this direction. A little more ambient and modern classical will expand your taste without making it feel unfamiliar.",
        }

    def get_insights(self) -> list[dict[str, str]]:
        return [
            {
                "title": "Taste shift",
                "detail": "Ambient listening is up 18% this month.",
            },
            {
                "title": "Discovery",
                "detail": "You found 14 new artists this week.",
            },
            {
                "title": "Listening rhythm",
                "detail": "Your calmest sessions happen after 8 PM.",
            },
        ]

    def get_timeline(self) -> list[dict[str, str]]:
        return [
            {"period": "2023", "label": "Indie"},
            {"period": "2024", "label": "Electronic"},
            {"period": "2025", "label": "Ambient"},
            {"period": "Now", "label": "Cinematic electronic"},
        ]

    def get_recommendations(self) -> list[dict[str, object]]:
        return [
            {
                "recommendation_id": "demo-rec-1",
                "title": "A Walk",
                "artist": "Tycho",
                "provider": "apple_music",
                "match_score": 94,
                "reason": "It matches your recent preference for spacious electronic music and reflective evening listening.",
                "context": "Evening wind-down",
            },
            {
                "recommendation_id": "demo-rec-2",
                "title": "Near Light",
                "artist": "Ólafur Arnalds",
                "provider": "apple_music",
                "match_score": 89,
                "reason": "It keeps the calm character you enjoy while adding more acoustic texture and detail.",
                "context": "Focused listening",
            },
        ]

    def record_feedback(self, recommendation_id: str, reaction: Reaction) -> dict[str, str]:
        event_id = f"feedback_{uuid4().hex}"
        self._feedback_events.append(
            {
                "event_id": event_id,
                "recommendation_id": recommendation_id,
                "reaction": reaction,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return {"event_id": event_id, "status": "recorded"}


music_dna_service = MusicDNAService()
