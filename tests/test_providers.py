from __future__ import annotations

from dataclasses import dataclass

import pytest

from echosense.providers import AppleMusicProvider, FixtureMusicProvider, provider_from_environment


@dataclass
class StubDeveloperTokens:
    value: str = "developer-token"

    def token(self) -> str:
        return self.value


@dataclass
class StubUserTokens:
    value: str | None = "music-user-token"

    def retrieve(self, user_id: str) -> str | None:
        return self.value


def test_fixture_provider_returns_ordered_provider_neutral_candidates() -> None:
    candidates = FixtureMusicProvider().candidates_for_context("rainy_commute")

    assert len(candidates) == 3
    assert candidates[0].provider == "apple_music"
    assert candidates[0].item_id == "fixture-rain-001"
    assert candidates[0].base_score > candidates[1].base_score
    assert "rainy drive" in candidates[0].rationale


def test_fixture_provider_respects_limit() -> None:
    candidates = FixtureMusicProvider().candidates_for_context("commute", limit=2)

    assert [candidate.item_id for candidate in candidates] == [
        "fixture-drive-001",
        "fixture-drive-002",
    ]


def test_fixture_provider_exposes_sync_capabilities() -> None:
    provider = FixtureMusicProvider()

    assert provider.capabilities().library_sync is True
    assert provider.sync_library("user-1")[0].signal_type == "library_song"
    assert provider.sync_recent_plays("user-1")[0].signal_type == "recent_play"


def test_apple_music_library_sync_normalizes_tracks(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": [
                    {
                        "id": "song-123",
                        "attributes": {
                            "name": "A Real Song",
                            "artistName": "A Real Artist",
                            "albumName": "A Real Album",
                        },
                    }
                ]
            }

    def fake_get(url: str, **kwargs: object) -> Response:
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("echosense.providers.httpx.get", fake_get)
    provider = AppleMusicProvider(
        developer_tokens=StubDeveloperTokens(),
        user_tokens=StubUserTokens(),
        base_url="https://music.test/v1",
    )

    signals = provider.sync_library("user-1", limit=10)

    assert captured["url"] == "https://music.test/v1/me/library/songs"
    assert captured["headers"] == {
        "Authorization": "Bearer developer-token",
        "Music-User-Token": "music-user-token",
    }
    assert signals[0].provider == "apple_music"
    assert signals[0].item_id == "song-123"
    assert signals[0].name == "A Real Song"
    assert signals[0].artist == "A Real Artist"
    assert signals[0].source_path == "me.library.songs"


def test_apple_music_recent_sync_requires_user_authorization() -> None:
    provider = AppleMusicProvider(
        developer_tokens=StubDeveloperTokens(),
        user_tokens=StubUserTokens(value=None),
    )

    with pytest.raises(PermissionError, match="user authorization"):
        provider.sync_recent_plays("user-1")


def test_unknown_provider_configuration_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECHOSENSE_MUSIC_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="Unsupported music provider"):
        provider_from_environment()