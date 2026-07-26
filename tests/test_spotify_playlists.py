from echosense.providers.spotify.playlists import SpotifyPlaylists


class FakeClient:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, *, params=None):
        self.calls.append((method, path, params))
        return self.responses.pop(0)


def test_playlists_are_normalized_with_explicit_browse_permission() -> None:
    client = FakeClient(
        [
            {
                "items": [
                    {
                        "id": "owned",
                        "name": "Focus",
                        "description": "Deep work",
                        "owner": {"id": "listener", "display_name": "Mohan"},
                        "collaborative": False,
                        "images": [{"url": "https://image/owned"}],
                        "items": {"total": 24},
                    },
                    {
                        "id": "followed",
                        "name": "Public mix",
                        "owner": {"id": "someone-else", "display_name": "Curator"},
                        "collaborative": False,
                    },
                ],
                "total": 10,
                "offset": 0,
                "limit": 2,
            }
        ]
    )

    page = SpotifyPlaylists(client, "listener").list(limit=2, offset=0)

    assert [item.provider_id for item in page.items] == ["owned", "followed"]
    assert page.items[0].can_browse is True
    assert page.items[0].track_count == 24
    assert page.items[1].can_browse is False
    assert page.next_offset == 2
    assert client.calls == [("GET", "/me/playlists", {"limit": 2, "offset": 0})]


def test_playlist_tracks_use_items_endpoint_and_keep_unavailable_rows() -> None:
    client = FakeClient(
        [
            {
                "items": [
                    {
                        "item": {
                            "id": "track-1",
                            "name": "Deep Focus",
                            "type": "track",
                            "is_playable": True,
                            "artists": [{"name": "Echo Artist"}],
                            "album": {"name": "Focus Album", "images": []},
                        }
                    },
                    {"item": None},
                    {
                        "item": {
                            "id": "local-1",
                            "name": "Local Track",
                            "type": "track",
                            "is_local": True,
                            "artists": [],
                        }
                    },
                ],
                "total": 3,
                "offset": 0,
                "limit": 20,
            }
        ]
    )

    page = SpotifyPlaylists(client, "listener").tracks("focus", limit=20, offset=0)

    assert [item.playable for item in page.items] == [True, False, False]
    assert page.items[0].track.title == "Deep Focus"
    assert page.items[1].track is None
    assert page.items[1].unavailable_reason == "Unavailable on Spotify"
    assert page.next_offset is None
    assert client.calls == [("GET", "/playlists/focus/items", {"limit": 20, "offset": 0})]
