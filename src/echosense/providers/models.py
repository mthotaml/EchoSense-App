from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class ProviderProvenance:
    provider: str
    source_path: str
    imported_at: datetime
    rank: int | None = None


@dataclass(frozen=True)
class Artist:
    provider: str
    provider_id: str
    name: str
    genres: tuple[str, ...] = ()
    popularity: int | None = None
    image_url: str | None = None
    external_url: str | None = None


@dataclass(frozen=True)
class Track:
    provider: str
    provider_id: str
    title: str
    artists: tuple[str, ...]
    album: str | None = None
    popularity: int | None = None
    image_url: str | None = None
    external_url: str | None = None
    isrc: str | None = None
    duration_ms: int | None = None

    @property
    def primary_artist(self) -> str:
        return self.artists[0] if self.artists else "Unknown artist"


@dataclass(frozen=True)
class Playlist:
    provider: str
    provider_id: str
    name: str
    description: str
    owner_name: str
    track_count: int
    can_browse: bool
    image_url: str | None = None


@dataclass(frozen=True)
class PlaylistTrack:
    track: Track | None
    position: int
    playable: bool
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class TrackObservation:
    track: Track
    provenance: ProviderProvenance
    observed_at: datetime | None = None


@dataclass(frozen=True)
class MusicDataImport:
    provider: str
    top_artists: tuple[tuple[Artist, ProviderProvenance], ...]
    top_tracks: tuple[TrackObservation, ...]
    recent_tracks: tuple[TrackObservation, ...]
    imported_at: datetime

    @classmethod
    def empty(cls, provider: str) -> MusicDataImport:
        return cls(provider, (), (), (), datetime.now(UTC))
