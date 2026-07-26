from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

Reaction = Literal["love", "not_for_me", "save", "play"]


class MusicDNAService:
    """Product-facing service boundary for Music DNA demo data.

    The UI depends on this interface rather than a specific streaming provider.
    Later, these methods can delegate to the recommendation engine and Apple
    Music adapter without changing the product routes.
    """

    def __init__(self) -> None:
        self._feedback_events: list[dict[str, str]] = []

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
