from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

import httpx

from echosense.apple_auth import AppleDeveloperTokenProvider, AppleUserTokenVault
from echosense.providers.base import MusicDataProvider
from echosense.providers.models import (
    Artist,
    MusicDataImport,
    ProviderProvenance,
    Track,
    TrackObservation,
)
from echosense.storage import Storage


@dataclass(frozen=True)
class RecommendationCandidate:
    provider: str
    item_id: str
    rationale: str
    base_score: float = 0.0


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    catalog_search: bool
    library_sync: bool
    recent_plays_sync: bool
    playlists_sync: bool
    playback_handoff: bool


@dataclass(frozen=True)
class ProviderSignal:
    provider: str
    signal_type: str
    item_id: str
    name: str
    artist: str | None
    album: str | None
    storefront: str | None
    source_path: str


class MusicProvider(Protocol):
    def capabilities(self) -> ProviderCapabilities:
        """Describe supported provider operations without exposing credentials."""

    def candidates_for_context(
        self, context: str, user_id: str | None = None, limit: int = 5
    ) -> list[RecommendationCandidate]:
        """Return provider-neutral candidates for a normalized EchoSense context."""

    def sync_library(self, user_id: str, limit: int = 25) -> list[ProviderSignal]:
        """Import permitted user-library signals in a provider-neutral form."""

    def sync_recent_plays(self, user_id: str, limit: int = 25) -> list[ProviderSignal]:
        """Import permitted recent-play signals in a provider-neutral form."""


class FixtureMusicProvider:
    _catalog = {
        "rainy_commute": [
            RecommendationCandidate(
                "apple_music", "fixture-rain-001", "calmer music for a rainy drive", 0.8
            ),
            RecommendationCandidate(
                "apple_music", "fixture-rain-002", "steady acoustic music for wet roads", 0.7
            ),
            RecommendationCandidate(
                "apple_music", "fixture-rain-003", "low-distraction ambient music", 0.6
            ),
        ],
        "commute": [
            RecommendationCandidate(
                "apple_music", "fixture-drive-001", "steady music for your drive", 0.8
            ),
            RecommendationCandidate(
                "apple_music", "fixture-drive-002", "focused music for commuting", 0.7
            ),
            RecommendationCandidate("apple_music", "fixture-drive-003", "balanced road music", 0.6),
        ],
        "evening_wind_down": [
            RecommendationCandidate(
                "apple_music", "fixture-evening-001", "lower-energy music for the evening", 0.8
            ),
            RecommendationCandidate(
                "apple_music", "fixture-evening-002", "gentle music for winding down", 0.7
            ),
            RecommendationCandidate(
                "apple_music", "fixture-evening-003", "quiet late-day listening", 0.6
            ),
        ],
        "general_listening": [
            RecommendationCandidate(
                "apple_music", "fixture-general-001", "music based on the available context", 0.8
            ),
            RecommendationCandidate(
                "apple_music", "fixture-general-002", "a broadly suitable listening option", 0.7
            ),
            RecommendationCandidate(
                "apple_music", "fixture-general-003", "a balanced general selection", 0.6
            ),
        ],
    }

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities("fixture", True, True, True, False, False)

    def candidates_for_context(
        self, context: str, user_id: str | None = None, limit: int = 5
    ) -> list[RecommendationCandidate]:
        return self._catalog.get(context, self._catalog["general_listening"])[:limit]

    def sync_library(self, user_id: str, limit: int = 25) -> list[ProviderSignal]:
        return [
            ProviderSignal(
                "apple_music",
                "library_song",
                "fixture-library-001",
                "Midnight Drive",
                "Echo Avenue",
                "City Lights",
                "us",
                "fixture.library",
            )
        ][:limit]

    def sync_recent_plays(self, user_id: str, limit: int = 25) -> list[ProviderSignal]:
        return [
            ProviderSignal(
                "apple_music",
                "recent_play",
                "fixture-recent-001",
                "Rain on Glass",
                "Northbound",
                "Weather Systems",
                "us",
                "fixture.recent",
            )
        ][:limit]


class AppleMusicProvider:
    """Apple-specific authentication, synchronization and parsing behind MusicProvider."""

    def __init__(
        self,
        developer_tokens: AppleDeveloperTokenProvider,
        user_tokens: AppleUserTokenVault | None = None,
        storefront: str = "us",
        base_url: str = "https://api.music.apple.com/v1",
        timeout_seconds: float = 5.0,
    ) -> None:
        self.developer_tokens = developer_tokens
        self.user_tokens = user_tokens
        self.storefront = storefront
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities("apple_music", True, True, True, True, True)

    def _headers(
        self, user_id: str | None = None, *, require_user_token: bool = False
    ) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.developer_tokens.token()}"}
        music_user_token = (
            self.user_tokens.retrieve(user_id) if user_id and self.user_tokens else None
        )
        if music_user_token:
            headers["Music-User-Token"] = music_user_token
        elif require_user_token:
            raise PermissionError("Apple Music user authorization is required")
        return headers

    def _get(
        self,
        path: str,
        *,
        user_id: str | None = None,
        params: dict[str, object] | None = None,
        require_user_token: bool = False,
    ) -> dict[str, object]:
        response = httpx.get(
            f"{self.base_url}{path}",
            headers=self._headers(user_id, require_user_token=require_user_token),
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def candidates_for_context(
        self, context: str, user_id: str | None = None, limit: int = 5
    ) -> list[RecommendationCandidate]:
        term_by_context = {
            "rainy_commute": "calm driving",
            "commute": "driving",
            "evening_wind_down": "chill evening",
            "general_listening": "recommended music",
        }
        term = term_by_context.get(context, term_by_context["general_listening"])
        payload = self._get(
            f"/catalog/{self.storefront}/search",
            user_id=user_id,
            params={"term": term, "types": "songs", "limit": min(max(limit, 1), 25)},
        )
        songs = payload.get("results", {}).get("songs", {}).get("data", [])
        if not songs:
            raise LookupError(f"Apple Music returned no candidates for context {context}")
        count = len(songs)
        return [
            RecommendationCandidate(
                provider="apple_music",
                item_id=item["id"],
                rationale=f"music matching the {context.replace('_', ' ')} context",
                base_score=round(1.0 - (index / max(count, 1)) * 0.2, 6),
            )
            for index, item in enumerate(songs)
        ]

    def _signals(
        self, payload: dict[str, object], signal_type: str, source_path: str
    ) -> list[ProviderSignal]:
        signals: list[ProviderSignal] = []
        for item in payload.get("data", []):
            attributes = item.get("attributes", {})
            signals.append(
                ProviderSignal(
                    provider="apple_music",
                    signal_type=signal_type,
                    item_id=item["id"],
                    name=attributes.get("name", "Unknown track"),
                    artist=attributes.get("artistName"),
                    album=attributes.get("albumName"),
                    storefront=self.storefront,
                    source_path=source_path,
                )
            )
        return signals

    def sync_library(self, user_id: str, limit: int = 25) -> list[ProviderSignal]:
        bounded_limit = min(max(limit, 1), 100)
        payload = self._get(
            "/me/library/songs",
            user_id=user_id,
            params={"limit": bounded_limit},
            require_user_token=True,
        )
        return self._signals(payload, "library_song", "me.library.songs")

    def sync_recent_plays(self, user_id: str, limit: int = 25) -> list[ProviderSignal]:
        bounded_limit = min(max(limit, 1), 30)
        payload = self._get(
            "/me/recent/played/tracks",
            user_id=user_id,
            params={"limit": bounded_limit},
            require_user_token=True,
        )
        return self._signals(payload, "recent_play", "me.recent.played.tracks")


def provider_from_environment(storage: Storage | None = None) -> MusicProvider:
    provider_name = os.getenv("ECHOSENSE_MUSIC_PROVIDER", "fixture").lower()
    if provider_name == "fixture":
        return FixtureMusicProvider()
    if provider_name == "apple_music":
        store = storage or Storage()
        vault = None
        if os.getenv("ECHOSENSE_TOKEN_ENCRYPTION_KEY"):
            vault = AppleUserTokenVault.from_environment(store)
        return AppleMusicProvider(
            developer_tokens=AppleDeveloperTokenProvider.from_environment(),
            user_tokens=vault,
            storefront=os.getenv("APPLE_MUSIC_STOREFRONT", "us"),
        )
    raise ValueError(f"Unsupported music provider: {provider_name}")


__all__ = [
    "AppleMusicProvider",
    "Artist",
    "FixtureMusicProvider",
    "MusicDataImport",
    "MusicDataProvider",
    "MusicProvider",
    "ProviderCapabilities",
    "ProviderProvenance",
    "ProviderSignal",
    "RecommendationCandidate",
    "Track",
    "TrackObservation",
    "provider_from_environment",
]
