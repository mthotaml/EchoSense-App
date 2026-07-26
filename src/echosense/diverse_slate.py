from __future__ import annotations

import re
from dataclasses import dataclass

from echosense.providers.models import Track


@dataclass(frozen=True)
class SlateItem:
    track: Track
    rank: int
    score: float
    reason: str


class DiverseSlateService:
    """Builds a provider-neutral, fatigue-aware sequence from a ranked candidate slate."""

    def build(
        self,
        tracks: list[Track],
        ranked: list[dict[str, object]],
        *,
        limit: int = 5,
        excluded_ids: set[str] | None = None,
    ) -> list[SlateItem]:
        by_id = {track.provider_id: track for track in tracks}
        excluded = excluded_ids or set()
        selected: list[SlateItem] = []
        recording_keys: set[str] = set()
        artist_counts: dict[str, int] = {}
        deferred: list[tuple[Track, dict[str, object]]] = []

        for candidate in ranked:
            track = by_id.get(str(candidate["item_id"]))
            if track is None or track.provider_id in excluded:
                continue
            key = self._recording_key(track)
            artist = track.primary_artist.casefold()
            if key in recording_keys or artist_counts.get(artist, 0) >= 2:
                continue
            if selected and selected[-1].track.primary_artist.casefold() == artist:
                deferred.append((track, candidate))
                continue
            self._append(selected, track, candidate, recording_keys, artist_counts)
            if len(selected) == limit:
                return selected

        for track, candidate in deferred:
            artist = track.primary_artist.casefold()
            if self._recording_key(track) in recording_keys or artist_counts.get(artist, 0) >= 2:
                continue
            self._append(selected, track, candidate, recording_keys, artist_counts)
            if len(selected) == limit:
                break
        return selected

    @staticmethod
    def _append(
        selected: list[SlateItem],
        track: Track,
        candidate: dict[str, object],
        recording_keys: set[str],
        artist_counts: dict[str, int],
    ) -> None:
        artist = track.primary_artist.casefold()
        score = float(candidate["ranking_score"])
        context_fit = float(candidate.get("context_fit", 0.0))
        preference = float(candidate.get("preference_weight", 0.0))
        evidence = []
        if context_fit > 0:
            evidence.append("fits this listening moment")
        if preference > 0:
            evidence.append("learned from your positive feedback")
        evidence.append("ranked from your Music DNA")
        selected.append(
            SlateItem(
                track=track,
                rank=len(selected) + 1,
                score=score,
                reason=", ".join(evidence).capitalize() + ".",
            )
        )
        recording_keys.add(DiverseSlateService._recording_key(track))
        artist_counts[artist] = artist_counts.get(artist, 0) + 1

    @staticmethod
    def _recording_key(track: Track) -> str:
        if track.isrc:
            return f"isrc:{track.isrc.casefold()}"
        normalized = re.sub(
            r"\W+",
            " ",
            f"{track.title} {' '.join(track.artists)}".casefold(),
        ).strip()
        return f"metadata:{normalized}"
