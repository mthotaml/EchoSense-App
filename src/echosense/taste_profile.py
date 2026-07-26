from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from echosense.app import get_storage
from echosense.apple_music_sync import AppleMusicSyncStore
from echosense.storage import Storage

router = APIRouter(prefix="/v1/users/{user_id}", tags=["taste-profile"])


class TasteProfileItem(BaseModel):
    name: str
    score: float
    evidence_count: int


class TasteProfileResponse(BaseModel):
    user_id: str
    status: str
    evidence_count: int
    confidence: float
    library_songs: int
    recent_plays: int
    discovery_ratio: float
    top_artists: list[TasteProfileItem]
    top_albums: list[TasteProfileItem]
    summary: str


class TasteProfileBuilder:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        AppleMusicSyncStore(storage).initialize()

    def _signals(self, user_id: str) -> list[dict[str, Any]]:
        with self.storage.connect() as connection:
            rows = self.storage._execute(
                connection,
                """
                SELECT signal_type, item_id, name, artist, album
                FROM provider_signals
                WHERE user_id = %s AND provider = 'apple_music'
                ORDER BY synced_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _rank(counter: Counter[str], limit: int = 5) -> list[TasteProfileItem]:
        total = sum(counter.values())
        if total == 0:
            return []
        return [
            TasteProfileItem(
                name=name,
                score=round(count / total, 3),
                evidence_count=count,
            )
            for name, count in counter.most_common(limit)
        ]

    def build(self, user_id: str) -> TasteProfileResponse:
        signals = self._signals(user_id)
        if not signals:
            return TasteProfileResponse(
                user_id=user_id,
                status="empty",
                evidence_count=0,
                confidence=0.0,
                library_songs=0,
                recent_plays=0,
                discovery_ratio=0.0,
                top_artists=[],
                top_albums=[],
                summary="Sync a music provider to build your portable taste profile.",
            )

        library = [signal for signal in signals if signal["signal_type"] == "library_song"]
        recent = [signal for signal in signals if signal["signal_type"] == "recent_play"]
        artist_counts: Counter[str] = Counter()
        album_counts: Counter[str] = Counter()
        for signal in signals:
            weight = 2 if signal["signal_type"] == "recent_play" else 1
            if signal.get("artist"):
                artist_counts[signal["artist"]] += weight
            if signal.get("album"):
                album_counts[signal["album"]] += weight

        library_ids = {signal["item_id"] for signal in library}
        discoveries = sum(1 for signal in recent if signal["item_id"] not in library_ids)
        discovery_ratio = round(discoveries / len(recent), 3) if recent else 0.0
        evidence_count = len(signals)
        confidence = round(min(1.0, evidence_count / 25), 3)
        top_artists = self._rank(artist_counts)
        leader = top_artists[0].name if top_artists else "your current listening"
        tendency = "exploratory" if discovery_ratio >= 0.5 else "familiarity-led"

        return TasteProfileResponse(
            user_id=user_id,
            status="ready",
            evidence_count=evidence_count,
            confidence=confidence,
            library_songs=len(library),
            recent_plays=len(recent),
            discovery_ratio=discovery_ratio,
            top_artists=top_artists,
            top_albums=self._rank(album_counts),
            summary=f"Your current profile leans toward {leader} and is {tendency} based on recent listening.",
        )


@router.get("/taste-profile", response_model=TasteProfileResponse)
def get_taste_profile(user_id: str) -> TasteProfileResponse:
    return TasteProfileBuilder(get_storage()).build(user_id)
