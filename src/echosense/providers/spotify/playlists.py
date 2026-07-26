from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from echosense.providers.models import Playlist, PlaylistTrack
from echosense.providers.spotify.client import SpotifyClient
from echosense.providers.spotify.mapper import map_track

PLAYLISTS_PATH = "/me/playlists"


@dataclass(frozen=True)
class PlaylistPage:
    items: tuple[Playlist, ...]
    total: int
    offset: int
    limit: int

    @property
    def next_offset(self) -> int | None:
        candidate = self.offset + self.limit
        return candidate if candidate < self.total else None


@dataclass(frozen=True)
class PlaylistTrackPage:
    items: tuple[PlaylistTrack, ...]
    total: int
    offset: int
    limit: int

    @property
    def next_offset(self) -> int | None:
        candidate = self.offset + self.limit
        return candidate if candidate < self.total else None


def _first_image(item: dict[str, Any]) -> str | None:
    images = item.get("images")
    if not isinstance(images, list) or not images or not isinstance(images[0], dict):
        return None
    url = images[0].get("url")
    return url if isinstance(url, str) else None


def _page(payload: Any) -> tuple[list[Any], int, int, int]:
    if not isinstance(payload, dict):
        raise ValueError("Spotify returned an invalid playlist page")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("Spotify playlist page is missing items")
    total = payload.get("total")
    offset = payload.get("offset")
    limit = payload.get("limit")
    if not all(isinstance(value, int) for value in (total, offset, limit)):
        raise ValueError("Spotify playlist page is missing pagination")
    return items, total, offset, limit


class SpotifyPlaylists:
    """Spotify playlist parsing and pagination behind the provider boundary."""

    def __init__(self, client: SpotifyClient, provider_user_id: str) -> None:
        self.client = client
        self.provider_user_id = provider_user_id

    def list(self, *, limit: int, offset: int) -> PlaylistPage:
        payload = self.client.request(
            "GET",
            PLAYLISTS_PATH,
            params={"limit": limit, "offset": offset},
        )
        raw_items, total, page_offset, page_limit = _page(payload)
        playlists = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            provider_id = item.get("id")
            name = item.get("name")
            if not isinstance(provider_id, str) or not isinstance(name, str):
                continue
            owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
            owner_id = owner.get("id")
            owner_name = owner.get("display_name") or owner_id or "Spotify listener"
            contents = item.get("items") if isinstance(item.get("items"), dict) else {}
            track_count = contents.get("total", 0)
            playlists.append(
                Playlist(
                    provider="spotify",
                    provider_id=provider_id,
                    name=name,
                    description=item.get("description")
                    if isinstance(item.get("description"), str)
                    else "",
                    owner_name=str(owner_name),
                    track_count=track_count if isinstance(track_count, int) else 0,
                    can_browse=owner_id == self.provider_user_id
                    or item.get("collaborative") is True,
                    image_url=_first_image(item),
                )
            )
        return PlaylistPage(tuple(playlists), total, page_offset, page_limit)

    def tracks(self, playlist_id: str, *, limit: int, offset: int) -> PlaylistTrackPage:
        normalized_id = playlist_id.strip()
        if not normalized_id or "/" in normalized_id:
            raise ValueError("Invalid Spotify playlist identifier")
        payload = self.client.request(
            "GET",
            f"/playlists/{normalized_id}/items",
            params={"limit": limit, "offset": offset},
        )
        raw_items, total, page_offset, page_limit = _page(payload)
        tracks = []
        for position, entry in enumerate(raw_items, start=page_offset):
            item = entry.get("item") if isinstance(entry, dict) else None
            if not isinstance(item, dict):
                tracks.append(PlaylistTrack(None, position, False, "Unavailable on Spotify"))
                continue
            track = map_track(item)
            playable = (
                track is not None
                and item.get("is_local") is not True
                and item.get("is_playable") is not False
                and item.get("type", "track") == "track"
            )
            tracks.append(
                PlaylistTrack(
                    track,
                    position,
                    playable,
                    None if playable else "Unavailable for browser playback",
                )
            )
        return PlaylistTrackPage(tuple(tracks), total, page_offset, page_limit)
