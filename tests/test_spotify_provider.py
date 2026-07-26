from datetime import UTC, datetime, timedelta

import httpx

from echosense.providers.spotify.client import SpotifyClient, SpotifyRateLimited
from echosense.providers.spotify.mapper import map_track
from echosense.providers.spotify.provider import (
    RECENT_TRACKS_PATH,
    TOP_ARTISTS_PATH,
    TOP_TRACKS_PATH,
    SpotifyProvider,
)
from echosense.repositories.provider_connections import ProviderConnection


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def items(self, path, params, *, limit):
        self.calls.append((path, params, limit))
        if path == TOP_ARTISTS_PATH:
            yield {"id": "artist-1", "name": "One", "genres": ["ambient"]}
            yield {"id": "artist-1", "name": "Duplicate", "genres": []}
        elif path == TOP_TRACKS_PATH:
            yield {
                "id": "track-1",
                "name": "Track",
                "artists": [{"name": "One"}],
                "album": {"name": "Album"},
            }
        elif path == RECENT_TRACKS_PATH:
            item = {
                "track": {
                    "id": "track-1",
                    "name": "Track",
                    "artists": [{"name": "One"}],
                },
                "played_at": "2026-07-25T12:00:00Z",
            }
            yield item
            yield item


def test_track_mapper_preserves_identity_metadata() -> None:
    track = map_track(
        {
            "id": "track-identity",
            "name": "Identity",
            "artists": [{"name": "Echo Artist"}],
            "external_ids": {"isrc": "USABC1234567"},
            "duration_ms": 201000,
        }
    )

    assert track is not None
    assert track.isrc == "USABC1234567"
    assert track.duration_ms == 201000


def test_provider_uses_bounded_sources_and_preserves_lineage() -> None:
    client = FakeClient()
    imported = SpotifyProvider(client).import_music_data()

    assert client.calls == [
        (TOP_ARTISTS_PATH, {"limit": 10, "time_range": "medium_term"}, 10),
        (TOP_TRACKS_PATH, {"limit": 10, "time_range": "medium_term"}, 10),
        (RECENT_TRACKS_PATH, {"limit": 20}, 20),
    ]
    assert [item[0].provider_id for item in imported.top_artists] == ["artist-1"]
    assert [item.track.provider_id for item in imported.recent_tracks] == ["track-1"]
    assert imported.top_tracks[0].provenance.source_path == TOP_TRACKS_PATH
    assert imported.recent_tracks[0].observed_at == datetime(2026, 7, 25, 12, tzinfo=UTC)


def test_client_follows_next_page_but_stops_at_requested_limit(monkeypatch) -> None:
    connection = ProviderConnection(
        session_id="session",
        provider="spotify",
        provider_user_id="user",
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        profile={},
    )
    requests = []

    def fake_get(url, **kwargs):
        requests.append((url, kwargs.get("params")))
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "1"}, {"id": "2"}],
                    "next": "https://api.spotify.com/v1/next-page",
                },
                request=httpx.Request("GET", url),
            )
        return httpx.Response(
            200,
            json={"items": [{"id": "3"}, {"id": "4"}], "next": None},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    refreshes = []
    client = SpotifyClient(connection, lambda session, **kwargs: refreshes.append(kwargs))

    assert [item["id"] for item in client.items("/first", {"limit": 3}, limit=3)] == [
        "1",
        "2",
        "3",
    ]
    assert requests == [
        ("https://api.spotify.com/v1/first", {"limit": 3}),
        ("https://api.spotify.com/v1/next-page", None),
    ]
    assert len(refreshes) == 2


def test_client_preserves_rate_limit_retry_after(monkeypatch) -> None:
    connection = ProviderConnection(
        session_id="session",
        provider="spotify",
        provider_user_id="user",
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        profile={},
    )
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kwargs: httpx.Response(
            429,
            headers={"Retry-After": "7"},
            request=httpx.Request("GET", url),
        ),
    )
    client = SpotifyClient(connection, lambda session, **kwargs: None)

    try:
        list(client.items("/limited", {"limit": 1}, limit=1))
    except SpotifyRateLimited as exc:
        assert exc.retry_after == 7
    else:
        raise AssertionError("Expected SpotifyRateLimited")
