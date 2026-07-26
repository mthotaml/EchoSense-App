from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from echosense import spotify_auth
from echosense.product_app import app

client = TestClient(app)


def test_spotify_session_is_disconnected_by_default() -> None:
    response = client.get("/auth/spotify/session")
    assert response.status_code == 200
    assert response.json() == {"connected": False}


def test_spotify_login_builds_authorization_redirect(monkeypatch) -> None:
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
    assert query["redirect_uri"] == [
        "http://127.0.0.1:8000/auth/spotify/callback"
    ]
    assert "echosense_spotify_oauth_state" in response.cookies
    assert "echosense_spotify_pkce_verifier" in response.cookies


def test_spotify_login_requires_client_id(monkeypatch) -> None:
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)

    response = client.get("/auth/spotify/login", follow_redirects=False)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "spotify_not_configured"


def test_spotify_callback_rejects_invalid_state() -> None:
    response = client.get(
        "/auth/spotify/callback?code=test-code&state=unexpected",
        cookies={"echosense_spotify_oauth_state": "expected"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_oauth_state"


def test_spotify_data_builds_live_music_profile(monkeypatch) -> None:
    session_id = "test-session"
    spotify_auth._sessions[session_id] = spotify_auth.SpotifySession(
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        profile={"display_name": "Mohan"},
    )

    def fake_get(session, path, params=None):
        if path == "/me/top/artists":
            return {
                "items": [
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
            }
        if path == "/me/top/tracks":
            return {
                "items": [
                    {
                        "id": "track-1",
                        "name": "A Real Track",
                        "artists": [{"name": "Artist One"}],
                        "album": {"name": "Album", "images": []},
                        "popularity": 64,
                        "external_urls": {"spotify": "https://open.spotify.com/track/1"},
                    }
                ]
            }
        return {"items": []}

    monkeypatch.setattr(spotify_auth, "_spotify_get", fake_get)

    response = client.get(
        "/auth/spotify/data",
        cookies={spotify_auth.SESSION_COOKIE: session_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["display_name"] == "Mohan"
    assert payload["profile"]["genres"][0]["name"] == "Ambient"
    assert payload["recommendation"]["title"] == "A Real Track"
    assert payload["recommendation"]["spotify_url"].endswith("/track/1")
    spotify_auth._sessions.pop(session_id, None)
