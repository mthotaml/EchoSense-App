from __future__ import annotations

from datetime import datetime
from typing import Any

from echosense.providers.models import Artist, ProviderProvenance, Track, TrackObservation

PROVIDER = "spotify"


def _first_image(value: object) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    image = value[0]
    return image.get("url") if isinstance(image, dict) else None


def _spotify_url(item: dict[str, Any]) -> str | None:
    urls = item.get("external_urls")
    return urls.get("spotify") if isinstance(urls, dict) else None


def map_artist(item: dict[str, Any]) -> Artist | None:
    provider_id = item.get("id")
    name = item.get("name")
    if not isinstance(provider_id, str) or not isinstance(name, str):
        return None
    genres = item.get("genres")
    return Artist(
        provider=PROVIDER,
        provider_id=provider_id,
        name=name,
        genres=tuple(genre for genre in genres or () if isinstance(genre, str)),
        popularity=item.get("popularity") if isinstance(item.get("popularity"), int) else None,
        image_url=_first_image(item.get("images")),
        external_url=_spotify_url(item),
    )


def map_track(item: dict[str, Any]) -> Track | None:
    provider_id = item.get("id")
    title = item.get("name")
    if not isinstance(provider_id, str) or not isinstance(title, str):
        return None
    raw_artists = item.get("artists")
    artists = tuple(
        artist["name"]
        for artist in raw_artists or ()
        if isinstance(artist, dict) and isinstance(artist.get("name"), str)
    )
    album = item.get("album")
    return Track(
        provider=PROVIDER,
        provider_id=provider_id,
        title=title,
        artists=artists,
        album=album.get("name") if isinstance(album, dict) else None,
        popularity=item.get("popularity") if isinstance(item.get("popularity"), int) else None,
        image_url=_first_image(album.get("images")) if isinstance(album, dict) else None,
        external_url=_spotify_url(item),
    )


def map_track_observation(
    item: dict[str, Any],
    *,
    source_path: str,
    imported_at: datetime,
    rank: int,
    observed_at: datetime | None = None,
) -> TrackObservation | None:
    track = map_track(item)
    if track is None:
        return None
    return TrackObservation(
        track=track,
        provenance=ProviderProvenance(PROVIDER, source_path, imported_at, rank),
        observed_at=observed_at,
    )
