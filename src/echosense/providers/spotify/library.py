from __future__ import annotations

from echosense.providers.spotify.client import SpotifyClient

LIBRARY_PATH = "/me/library"
LIBRARY_CONTAINS_PATH = "/me/library/contains"


class SpotifyLibrary:
    """Spotify-specific library operations behind the provider boundary."""

    def __init__(self, client: SpotifyClient) -> None:
        self.client = client

    @staticmethod
    def track_uri(track_id: str) -> str:
        normalized = track_id.strip()
        if not normalized or ":" in normalized or "," in normalized:
            raise ValueError("Invalid Spotify track identifier")
        return f"spotify:track:{normalized}"

    def contains_track(self, track_id: str) -> bool:
        payload = self.client.request(
            "GET",
            LIBRARY_CONTAINS_PATH,
            params={"uris": self.track_uri(track_id)},
        )
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], bool):
            raise ValueError("Spotify returned an invalid library status")
        return payload[0]

    def save_track(self, track_id: str) -> None:
        self.client.request(
            "PUT",
            LIBRARY_PATH,
            params={"uris": self.track_uri(track_id)},
        )

    def remove_track(self, track_id: str) -> None:
        self.client.request(
            "DELETE",
            LIBRARY_PATH,
            params={"uris": self.track_uri(track_id)},
        )
