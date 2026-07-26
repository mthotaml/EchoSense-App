import pytest

from echosense.providers.spotify.library import (
    LIBRARY_CONTAINS_PATH,
    LIBRARY_PATH,
    SpotifyLibrary,
)


class FakeClient:
    def __init__(self, status=None) -> None:
        self.status = status
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def request(self, method, path, *, params=None):
        self.calls.append((method, path, params))
        return self.status


def test_library_uses_current_generic_spotify_endpoints() -> None:
    client = FakeClient([True])
    library = SpotifyLibrary(client)

    assert library.contains_track("track-1") is True
    library.save_track("track-1")
    library.remove_track("track-1")

    params = {"uris": "spotify:track:track-1"}
    assert client.calls == [
        ("GET", LIBRARY_CONTAINS_PATH, params),
        ("PUT", LIBRARY_PATH, params),
        ("DELETE", LIBRARY_PATH, params),
    ]


@pytest.mark.parametrize("track_id", ["", " ", "spotify:track:one", "one,two"])
def test_library_rejects_unsafe_track_identifiers(track_id: str) -> None:
    with pytest.raises(ValueError, match="Invalid Spotify track identifier"):
        SpotifyLibrary.track_uri(track_id)


@pytest.mark.parametrize("payload", [None, {}, [], [True, False], ["true"]])
def test_library_rejects_invalid_status_payloads(payload) -> None:
    with pytest.raises(ValueError, match="invalid library status"):
        SpotifyLibrary(FakeClient(payload)).contains_track("track-1")
