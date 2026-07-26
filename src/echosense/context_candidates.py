from __future__ import annotations

from dataclasses import dataclass

import httpx

from echosense.providers.models import Track
from echosense.providers.spotify.client import SpotifyClient, SpotifyRateLimited
from echosense.providers.spotify.mapper import map_track


@dataclass(frozen=True)
class ContextCandidateResult:
    tracks: tuple[Track, ...]
    scores: dict[str, float]
    evidence: dict[str, tuple[str, ...]]


class ContextCandidateService:
    """Expands the slate with catalog tracks related to transient context."""

    def expand(
        self,
        client: SpotifyClient,
        *,
        weather: str | None,
        region: str | None,
        road_setting: str | None,
        activity: str | None,
        daypart: str | None,
        mood: str | None = None,
    ) -> ContextCandidateResult:
        queries = self.queries(
            weather=weather,
            region=region,
            road_setting=road_setting,
            activity=activity,
            daypart=daypart,
            mood=mood,
        )
        tracks: dict[str, Track] = {}
        scores: dict[str, float] = {}
        evidence: dict[str, list[str]] = {}
        for query, label, score in queries:
            try:
                payload = client.request(
                    "GET",
                    "/search",
                    params={"q": query, "type": "track", "limit": 5},
                )
            except (
                SpotifyRateLimited,
                httpx.HTTPError,
                ImportError,
                KeyError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                continue
            items = payload.get("tracks", {}).get("items", []) if isinstance(payload, dict) else []
            for raw in items:
                track = map_track(raw) if isinstance(raw, dict) else None
                if track is None:
                    continue
                tracks.setdefault(track.provider_id, track)
                scores[track.provider_id] = max(scores.get(track.provider_id, 0.0), score)
                evidence.setdefault(track.provider_id, []).append(label)
        return ContextCandidateResult(
            tuple(tracks.values()),
            scores,
            {item_id: tuple(dict.fromkeys(labels)) for item_id, labels in evidence.items()},
        )

    @staticmethod
    def queries(
        *,
        weather: str | None,
        region: str | None,
        road_setting: str | None,
        activity: str | None,
        daypart: str | None,
        mood: str | None = None,
    ) -> list[tuple[str, str, float]]:
        result: list[tuple[str, str, float]] = []
        if mood in {"romantic", "melancholy", "calm", "reflective", "energetic", "uplifting"}:
            result.append(
                (
                    f"{mood} {daypart.replace('_', ' ') if daypart else ''} music".strip(),
                    f"learned {mood} {daypart.replace('_', ' ') if daypart else ''} pattern".strip(),
                    1.0,
                )
            )
        if road_setting == "coastal":
            result.append(
                (
                    "beach coastal drive",
                    "coastal drive matched to your Music DNA",
                    1.0,
                )
            )
        elif road_setting == "mountain":
            result.append(
                (
                    "mountain scenic drive",
                    "mountain drive matched to your Music DNA",
                    1.0,
                )
            )
        if weather in {"sunny", "rainy", "cloudy", "partly_cloudy"}:
            term = {"partly_cloudy": "cloudy"}.get(weather, weather)
            result.append((f"{term} day", f"{weather.replace('_', ' ')} weather", 1.0))
        if region and region != "your area":
            query = "California Los Angeles" if region == "Southern California" else region
            result.append((query, f"local connection to {region}", 0.8))
        if activity in {"driving", "fast_driving"}:
            result.append(
                (
                    "upbeat driving" if activity == "fast_driving" else "driving",
                    "higher-energy driving context"
                    if activity == "fast_driving"
                    else "driving context",
                    1.0,
                )
            )
        if daypart:
            result.append((f"{daypart.replace('_', ' ')} music", f"{daypart} timing", 0.65))
        return result[:6]
