from __future__ import annotations

from datetime import UTC, datetime

from echosense.providers.models import MusicDataImport, ProviderProvenance, TrackObservation
from echosense.providers.spotify.client import SpotifyClient
from echosense.providers.spotify.mapper import map_artist, map_track_observation

TOP_ARTISTS_PATH = "/me/top/artists"
TOP_TRACKS_PATH = "/me/top/tracks"
RECENT_TRACKS_PATH = "/me/player/recently-played"


class SpotifyProvider:
    def __init__(self, client: SpotifyClient) -> None:
        self.client = client

    def import_music_data(self) -> MusicDataImport:
        imported_at = datetime.now(UTC)
        artists = []
        seen_artists: set[str] = set()
        for rank, item in enumerate(
            self.client.items(
                TOP_ARTISTS_PATH,
                {"limit": 10, "time_range": "medium_term"},
                limit=10,
            ),
            start=1,
        ):
            artist = map_artist(item)
            if artist is None or artist.provider_id in seen_artists:
                continue
            seen_artists.add(artist.provider_id)
            artists.append(
                (
                    artist,
                    ProviderProvenance("spotify", TOP_ARTISTS_PATH, imported_at, rank),
                )
            )

        top_tracks = self._track_observations(
            TOP_TRACKS_PATH,
            {"limit": 10, "time_range": "medium_term"},
            limit=10,
            imported_at=imported_at,
        )
        recent_tracks = self._track_observations(
            RECENT_TRACKS_PATH,
            {"limit": 20},
            limit=20,
            imported_at=imported_at,
            recent=True,
        )
        return MusicDataImport(
            provider="spotify",
            top_artists=tuple(artists),
            top_tracks=tuple(top_tracks),
            recent_tracks=tuple(recent_tracks),
            imported_at=imported_at,
        )

    def _track_observations(
        self,
        path: str,
        params: dict[str, object],
        *,
        limit: int,
        imported_at: datetime,
        recent: bool = False,
    ) -> list[TrackObservation]:
        observations = []
        seen: set[str] = set()
        for rank, wrapper in enumerate(self.client.items(path, params, limit=limit), start=1):
            item = wrapper.get("track") if recent else wrapper
            if not isinstance(item, dict):
                continue
            observed_at = None
            if recent and isinstance(wrapper.get("played_at"), str):
                try:
                    observed_at = datetime.fromisoformat(
                        wrapper["played_at"].replace("Z", "+00:00")
                    )
                except ValueError:
                    observed_at = None
            observation = map_track_observation(
                item,
                source_path=path,
                imported_at=imported_at,
                rank=rank,
                observed_at=observed_at,
            )
            if observation is None or observation.track.provider_id in seen:
                continue
            seen.add(observation.track.provider_id)
            observations.append(observation)
        return observations
