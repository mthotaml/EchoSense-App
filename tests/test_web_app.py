from fastapi.testclient import TestClient

from echosense.web_app import app


def test_cognitive_dashboard_and_assets_are_served() -> None:
    client = TestClient(app)

    dashboard = client.get("/")
    stylesheet = client.get("/ui/styles.css")
    provider_stylesheet = client.get("/ui/provider-card.css")
    script = client.get("/ui/app.js")
    apple_music_script = client.get("/ui/apple-music.js")

    assert dashboard.status_code == 200
    assert "EchoSense" in dashboard.text
    assert "Train once." in dashboard.text
    assert "Listen everywhere." in dashboard.text
    assert "Connect Apple Music" in dashboard.text
    assert "Not connected" in dashboard.text
    assert "apple-music-card" in dashboard.text
    assert "musickit/v3/musickit.js" in dashboard.text
    assert "/ui/styles.css" in dashboard.text
    assert "/ui/provider-card.css" in dashboard.text
    assert "/ui/app.js" in dashboard.text
    assert "/ui/apple-music.js" in dashboard.text
    assert stylesheet.status_code == 200
    assert "--accent" in stylesheet.text
    assert provider_stylesheet.status_code == 200
    assert '.provider-card[data-state="connected"]' in provider_stylesheet.text
    assert '.provider-card[data-state="error"]' in provider_stylesheet.text
    assert script.status_code == 200
    assert 'request("/v1/recommendations"' in script.text
    assert apple_music_script.status_code == 200
    assert "MusicKit.configure" in apple_music_script.text
    assert "music.authorize()" in apple_music_script.text
    assert 'setAppleMusicState("connecting"' in apple_music_script.text
    assert "renderCompletedSync(sync)" in apple_music_script.text
    assert "/providers/apple-music/sync" in apple_music_script.text
    assert "/taste-profile" in apple_music_script.text
    assert "renderTasteProfile(profile)" in apple_music_script.text
    assert 'setAppleMusicState("error"' in apple_music_script.text


def test_apple_music_config_is_explicitly_disabled_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("APPLE_MUSIC_TEAM_ID", raising=False)
    monkeypatch.delenv("APPLE_MUSIC_KEY_ID", raising=False)
    monkeypatch.delenv("APPLE_MUSIC_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("APPLE_MUSIC_PRIVATE_KEY_PATH", raising=False)

    response = TestClient(app).get("/v1/providers/apple-music/config")

    assert response.status_code == 200
    assert response.json() == {
        "configured": False,
        "developer_token": None,
        "app_name": "EchoSense",
        "app_build": "0.1.0",
    }


def test_dashboard_keeps_backend_health_available() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
