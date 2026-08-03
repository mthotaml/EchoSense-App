from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient

from echosense import spotify_auth
from echosense.product_app import app
from echosense.repositories.provider_connections import ProviderConnectionRepository
from echosense.storage import Storage
from echosense.temporal_mood import TemporalMoodLearningService


@pytest.fixture(autouse=True)
def connection_repository(tmp_path, monkeypatch) -> ProviderConnectionRepository:
    repository = ProviderConnectionRepository(
        Storage(f"sqlite:///{tmp_path / 'connections.db'}"),
        Fernet.generate_key(),
    )
    monkeypatch.setattr(spotify_auth, "_connection_repository", repository)
    return repository


@pytest.fixture
def client() -> TestClient:
    """Keep cookies and ASGI lifespan state isolated between authentication tests."""
    with TestClient(app) as test_client:
        yield test_client


def test_spotify_session_is_disconnected_by_default(client: TestClient) -> None:
    response = client.get("/auth/spotify/session")
    assert response.status_code == 200
    assert response.json() == {"connected": False}


def test_spotify_login_builds_authorization_redirect(monkeypatch, client: TestClient) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client-id")
    monkeypatch.setenv(
        "SPOTIFY_REDIRECT_URI",
        "http://127.0.0.1:8000/auth/spotify/callback",
    )

    response = client.get("/auth/spotify/login", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == (
        "https://accounts.spotify.com/authorize"
    )
    assert query["client_id"] == ["test-client-id"]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["http://127.0.0.1:8000/auth/spotify/callback"]
    assert "playlist-read-private" in query["scope"][0]
    assert "playlist-read-collaborative" in query["scope"][0]
    assert "echosense_spotify_oauth_state" in response.cookies
    assert "echosense_spotify_pkce_verifier" in response.cookies


def test_spotify_login_requires_client_id(monkeypatch, client: TestClient) -> None:
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)

    response = client.get("/auth/spotify/login", follow_redirects=False)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "spotify_not_configured"


def test_session_requires_encrypted_token_storage_when_cookie_is_present(
    monkeypatch, client: TestClient
) -> None:
    monkeypatch.setattr(spotify_auth, "_connection_repository", None)
    monkeypatch.delenv("ECHOSENSE_TOKEN_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("ECHOSENSE_TOKEN_ENCRYPTION_KEYS", raising=False)

    response = client.get(
        "/auth/spotify/session",
        cookies={spotify_auth.SESSION_COOKIE: "unknown-session"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "spotify_token_storage_not_configured"


def test_spotify_callback_rejects_invalid_state(client: TestClient) -> None:
    response = client.get(
        "/auth/spotify/callback?code=test-code&state=unexpected",
        cookies={"echosense_spotify_oauth_state": "expected"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_oauth_state"


def test_spotify_profile_retries_once_after_retry_after() -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"id": "spotify-user", "display_name": "Mohan"}),
        ]
    )
    delays: list[float] = []
    client = httpx.Client(transport=httpx.MockTransport(lambda request: next(responses)))

    profile = spotify_auth._spotify_profile_with_backoff(
        client,
        "access-token",
        sleep=delays.append,
    )

    assert profile["id"] == "spotify-user"
    assert delays == [2]


def test_spotify_profile_returns_bounded_rate_limit_error_after_retry() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, headers={"Retry-After": "3"})
        )
    )

    with pytest.raises(HTTPException) as error:
        spotify_auth._spotify_profile_with_backoff(
            client,
            "access-token",
            sleep=lambda _: None,
        )

    assert error.value.status_code == 429
    assert error.value.detail["code"] == "spotify_rate_limited"
    assert error.value.detail["retry_after_seconds"] == 3
    assert error.value.headers == {"Retry-After": "3"}


def test_spotify_auth_client_isolation(client: TestClient) -> None:
    assert spotify_auth.SESSION_COOKIE not in client.cookies
    client.cookies.set(spotify_auth.SESSION_COOKIE, "stale-session")

    with TestClient(app) as isolated_client:
        assert spotify_auth.SESSION_COOKIE not in isolated_client.cookies


def test_spotify_data_builds_live_music_profile(
    monkeypatch,
    connection_repository: ProviderConnectionRepository,
    client: TestClient,
) -> None:
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client-id")
    session_id = "test-session"
    connection_repository.save(
        spotify_auth.SpotifySession(
            session_id=session_id,
            provider="spotify",
            provider_user_id="spotify-user",
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            profile={"display_name": "Mohan"},
        )
    )

    def fake_items(self, path, params, *, limit):
        if path == "/me/top/artists":
            yield from [
                {
                    "id": "artist-1",
                    "name": "Artist One",
                    "genres": ["indie rock", "ambient"],
                    "popularity": 70,
                    "images": [],
                    "external_urls": {"spotify": "https://open.spotify.com/artist/1"},
                },
                {
                    "id": "artist-2",
                    "name": "Artist Two",
                    "genres": ["ambient"],
                    "popularity": 50,
                    "images": [],
                    "external_urls": {"spotify": "https://open.spotify.com/artist/2"},
                },
            ]
        if path == "/me/top/tracks":
            yield {
                "id": "track-1",
                "name": "A Real Track",
                "artists": [{"name": "Artist One"}],
                "album": {"name": "Album", "images": []},
                "popularity": 64,
                "external_urls": {"spotify": "https://open.spotify.com/track/1"},
            }

    monkeypatch.setattr(spotify_auth.SpotifyClient, "items", fake_items)

    response = client.get(
        "/auth/spotify/data?moment=working",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["profile"]["display_name"] == "Mohan"
    assert payload["profile"]["genres"][0]["name"] == "Ambient"
    assert payload["profile"]["confidence"] > 0
    assert payload["profile"]["evidence_count"] == 3
    assert payload["profile"]["evidence_sources"] == [
        "/me/top/artists",
        "/me/top/tracks",
    ]
    assert payload["recommendation"]["title"] == "A Real Track"
    assert payload["recommendation"]["match_score"] == 75
    assert payload["recommendations"][0]["why_now"]["overall_score"] == 75
    assert payload["moment_impact"]["moment"] == "working"
    assert payload["moment_impact"]["source"] == "selected"
    assert payload["moment_impact"]["applied"] is True
    assert payload["moment_impact"]["compared_candidates"] == 1
    assert payload["recommendations"][0]["why_now"]["moment_impact"]["context_fit"] == 50
    assert payload["context_statement"].startswith("EchoSense is tailoring")
    assert sum(payload["effective_weights"].values()) == pytest.approx(1.0)
    assert payload["recommendation_boosts"] == {
        "music_dna": 0,
        "live_context": 0,
        "learned_preference": 0,
        "diversity": 0,
    }
    boosted = client.get(
        "/auth/spotify/data?moment=working&boost_live_context=80&boost_diversity=100",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )
    assert boosted.status_code == 200
    boosted_payload = boosted.json()
    assert boosted_payload["recommendation_boosts"]["live_context"] == 80
    assert boosted_payload["recommendation_boosts"]["diversity"] == 100
    assert "live context" in boosted_payload["context_statement"]
    assert "artist diversity" in boosted_payload["context_statement"]
    assert payload["recommendation"]["decision_id"].startswith("dec_")
    assert payload["recommendation"]["evidence"]["noticed"] == "You selected working."
    assert payload["recommendation"]["evidence"]["matched_genres"] == ["ambient"]
    assert "For working" in payload["recommendation"]["reason"]
    assert payload["recommendation"]["spotify_url"].endswith("/track/1")
    rotated = client.get(
        "/auth/spotify/data?moment=working&exclude=track-1",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )
    assert rotated.status_code == 200
    assert rotated.json()["recommendation"] is None
    assert rotated.json()["recommendations"] == []
    trace = connection_repository.storage.get_decision_trace(
        payload["recommendation"]["decision_id"]
    )
    assert trace is not None
    assert trace["context"] == "working"
    assert trace["factors"]["listening_moment"] == "working"
    assert trace["factors"]["requested_listening_moment"] == "working"
    assert trace["factors"]["listening_moment_source"] == "selected"
    assert trace["factors"]["track_snapshot"]["title"] == "A Real Track"
    assert trace["factors"]["track_snapshot"]["artist"] == "Artist One"
    intelligence = client.get(
        "/auth/spotify/intelligence",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )
    assert intelligence.status_code == 200
    assert intelligence.json()["scope"] == "connected_listener"
    assert intelligence.json()["data_status"] == "learning"
    snapshot = connection_repository.storage._execute
    with connection_repository.storage.connect() as database:
        row = snapshot(
            database,
            "SELECT normalized_json FROM music_data_imports WHERE user_id = %s",
            ("spotify-user",),
        ).fetchone()
    assert row is not None
    assert "access-token" not in dict(row)["normalized_json"]
    with connection_repository.storage.connect() as database:
        profile = snapshot(
            database,
            "SELECT profile_json FROM music_dna_profiles WHERE user_id = %s",
            ("spotify-user",),
        ).fetchone()
    assert profile is not None
    assert "access-token" not in dict(profile)["profile_json"]

    library_calls = []

    def fake_contains(self, track_id):
        library_calls.append(("contains", track_id))
        return False

    def fake_save(self, track_id):
        library_calls.append(("save", track_id))

    def fake_remove(self, track_id):
        library_calls.append(("remove", track_id))

    monkeypatch.setattr(spotify_auth.SpotifyLibrary, "contains_track", fake_contains)
    monkeypatch.setattr(spotify_auth.SpotifyLibrary, "save_track", fake_save)
    monkeypatch.setattr(spotify_auth.SpotifyLibrary, "remove_track", fake_remove)

    library_status = client.get(
        "/auth/spotify/library/tracks/track-1",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )
    saved = client.put(
        "/auth/spotify/library/tracks/track-1",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json={
            "outcome_id": "spotify-save-1",
            "decision_id": payload["recommendation"]["decision_id"],
        },
    )
    removed = client.delete(
        "/auth/spotify/library/tracks/track-1",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )

    assert library_status.json()["saved"] is False
    assert saved.status_code == 200
    assert saved.json()["saved"] is True
    assert saved.json()["learning"]["signal"] == "saved"
    assert saved.json()["learning"]["applied"] is True
    assert removed.json()["saved"] is False
    assert library_calls == [
        ("contains", "track-1"),
        ("save", "track-1"),
        ("remove", "track-1"),
    ]

    feedback = client.post(
        "/auth/spotify/feedback",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json={
            "outcome_id": "spotify-feedback-1",
            "decision_id": payload["recommendation"]["decision_id"],
            "signal": "skipped",
            "completion_ratio": 0.1,
            "playback_seconds": 12,
        },
    )
    duplicate = client.post(
        "/auth/spotify/feedback",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
        json={
            "outcome_id": "spotify-feedback-1",
            "decision_id": payload["recommendation"]["decision_id"],
            "signal": "skipped",
            "completion_ratio": 0.1,
            "playback_seconds": 12,
        },
    )
    assert feedback.status_code == 200
    assert feedback.json()["delta"] == -0.072
    assert feedback.json()["applied"] is True
    assert feedback.json()["evaluation"]["observed_reward"] < 0
    assert duplicate.json()["applied"] is False


def test_logout_revokes_server_connection_and_clears_cookie(
    connection_repository: ProviderConnectionRepository, client: TestClient
) -> None:
    session_id = "logout-session"
    connection_repository.save(
        spotify_auth.SpotifySession(
            session_id=session_id,
            provider="spotify",
            provider_user_id="spotify-user",
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            profile={"id": "spotify-user", "display_name": "Mohan"},
        )
    )

    response = client.post(
        "/auth/spotify/logout",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "disconnected"}
    assert connection_repository.get(session_id, "spotify") is None
    assert spotify_auth.SESSION_COOKIE in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_temporal_mood_controls_are_scoped_to_connected_listener(
    connection_repository: ProviderConnectionRepository, client: TestClient
) -> None:
    session_id = "temporal-session"
    connection_repository.save(
        spotify_auth.SpotifySession(
            session_id=session_id,
            provider="spotify",
            provider_user_id="spotify-user",
            access_token="access-token",
            refresh_token="refresh-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            profile={"id": "spotify-user", "display_name": "Mohan"},
        )
    )
    learning = TemporalMoodLearningService(connection_repository.storage)
    now = datetime.now(UTC)
    for index in range(3):
        learning.record(
            outcome_id=f"temporal-{index}",
            user_id="spotify-user",
            signal="liked",
            trace={
                "item_id": f"track-{index}",
                "factors": {
                    "temporal_mood": {
                        "mood": "romantic",
                        "daypart": "evening",
                        "source": "synthetic route evidence",
                        "confidence": 0.8,
                    }
                },
            },
            observed_at=now - timedelta(days=index),
        )

    cookies = {spotify_auth.SESSION_COOKIE: session_id}
    profile = client.get("/auth/spotify/temporal-mood?daypart=evening", cookies=cookies)
    assert profile.status_code == 200
    assert profile.json()["mood"] == "romantic"
    assert profile.json()["pattern_type"] == "stable_pattern"

    corrected = client.post(
        "/auth/spotify/temporal-mood/correct",
        cookies=cookies,
        json={"daypart": "evening", "mood": "romantic"},
    )
    assert corrected.json() == {"status": "corrected", "removed": 3}

    disabled = client.put(
        "/auth/spotify/temporal-mood/settings",
        cookies=cookies,
        json={"enabled": False},
    )
    assert disabled.json() == {"enabled": False}
    assert (
        client.get("/auth/spotify/temporal-mood?daypart=evening", cookies=cookies).json()["enabled"]
        is False
    )

    reset = client.delete("/auth/spotify/temporal-mood", cookies=cookies)
    assert reset.json() == {"status": "reset", "removed": 0}
