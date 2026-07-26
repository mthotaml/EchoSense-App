from fastapi.testclient import TestClient

from echosense.product_app import app

client = TestClient(app)


def test_landing_page_is_available() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "EchoSense" in response.text
    assert "EchoSense listens to you" in response.text
    assert "Today's pick" in response.text
    assert "Your Music DNA" in response.text


def test_demo_profile_is_ready() -> None:
    response = client.get("/v1/demo/taste-profile")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["confidence"] > 0
    assert payload["genres"]
    assert payload["coach"]


def test_demo_insights_are_focused() -> None:
    response = client.get("/v1/demo/insights")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 3
    assert all(item["title"] and item["detail"] for item in items)


def test_demo_timeline_is_available() -> None:
    response = client.get("/v1/demo/timeline")
    assert response.status_code == 200
    items = response.json()["items"]
    assert items[-1]["period"] == "Now"


def test_demo_recommendations_are_explained() -> None:
    response = client.get("/v1/demo/recommendations")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert all(item["reason"] and item["match_score"] for item in items)


def test_demo_feedback_is_recorded() -> None:
    response = client.post(
        "/v1/demo/feedback",
        json={"recommendation_id": "demo-rec-1", "reaction": "play"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "recorded"


def test_browser_player_uses_explicit_playback_commands() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "player.togglePlay" not in response.text
    assert "restorePlaybackState" in response.text
    assert "/v1/player/pause" in response.text
    assert "/v1/player/play" in response.text
    assert "/v1/player/recommendations/" in response.text
    assert "currentPlayOutcomeId" in response.text
    assert "The outcome is linked to this decision." in response.text
    assert "/auth/spotify/feedback" in response.text
    assert "pick.decision_id" in response.text
    assert "feedback('completed'" in response.text
    assert "feedback('skipped')" in response.text
    assert 'id="save"' in response.text
    assert "toggleSaved" in response.text
    assert "/auth/spotify/library/tracks/" in response.text
    assert "Saved to Spotify. EchoSense learned from this choice." in response.text
    assert 'id="playlists-panel"' in response.text
    assert "loadPlaylists" in response.text
    assert "loadPlaylistsSafely" in response.text
    assert "Spotify playlists are temporarily unavailable" in response.text
    assert "Promise.allSettled" in response.text
    assert "loadPlaylistTracks" in response.text
    assert "playPlaylistTrack" in response.text
    assert 'id="moment"' in response.text
    assert "/auth/spotify/data?" in response.text
    assert "Context evidence:" in response.text
    assert "disconnectSpotify" in response.text
    assert "/auth/spotify/logout" in response.text
    assert "setInterval(updateProgressClock,500)" in response.text
    assert "Last session restored · choose a device to resume" in response.text
    assert "continuity?.requires_confirmation" in response.text
    assert 'id="device-picker"' in response.text
    assert "loadDevices" in response.text
    assert "transferSelectedDevice" in response.text
    assert 'id="queue-panel"' in response.text
    assert "queueRecommendation" in response.text
    assert "loadQueue" in response.text
    assert "Spotify returned an incomplete listening profile" in response.text
    assert "detail.detail?.code" in response.text
    assert "$('#queue-add').disabled=true" in response.text
    assert 'id="shuffle"' in response.text
    assert 'id="repeat"' in response.text
    assert "/v1/player/shuffle" in response.text
    assert "/v1/player/repeat" in response.text
    assert 'id="dna-queue-panel"' in response.text
    assert "addDnaQueue" in response.text
    assert "Tracks already queued were skipped" in response.text
    assert "playDnaTrack" in response.text
    assert "queueDnaTrack" in response.text
    assert "Skip &amp; play next" in response.text
    assert "skipAndPlayNext" in response.text
    assert 'id="queue-skip"' in response.text
    assert 'id="live-context-panel"' in response.text
    assert "enableLiveContext" in response.text
    assert "navigator.geolocation.watchPosition" in response.text
    assert "/v1/context/resolve" in response.text
    assert "road_setting" in response.text
    assert "road_setting?.replace" in response.text
    assert "Raw coordinates are used transiently" in response.text
    assert "why_now?.factors" in response.text
    assert 'id="temporal-mood-panel"' in response.text
    assert "renderTemporalMood" in response.text
    assert "/auth/spotify/temporal-mood/correct" in response.text
    assert "/auth/spotify/temporal-mood/settings" in response.text
    assert "Temporal mood patterns reset" in response.text
    assert "never your mental or medical state" in response.text
    assert "/ui/player-lifecycle.js" in response.text

    lifecycle = client.get("/ui/player-lifecycle.js")
    assert lifecycle.status_code == 200
    assert "class PlayerLifecycle" in lifecycle.text
