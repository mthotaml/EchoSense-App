from fastapi.testclient import TestClient

from echosense import profile_recommendations
from echosense.apple_music_sync import AppleMusicSyncService, AppleMusicSyncStore
from echosense.providers import FixtureMusicProvider
from echosense.storage import Storage
from echosense.web_app import app


def test_profile_aware_recommendation_requires_synced_profile(tmp_path, monkeypatch) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'recommendations.db'}")
    monkeypatch.setattr(profile_recommendations, "get_storage", lambda: storage)

    response = TestClient(app).get("/v1/users/new-user/recommendations/profile-aware")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "taste_profile_required"


def test_profile_aware_recommendation_uses_taste_evidence(tmp_path, monkeypatch) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'recommendations.db'}")
    provider = FixtureMusicProvider()
    AppleMusicSyncService(provider, AppleMusicSyncStore(storage)).run("profile-user")

    monkeypatch.setattr(profile_recommendations, "get_storage", lambda: storage)
    monkeypatch.setattr(profile_recommendations, "get_music_provider", lambda: provider)

    candidate = provider.candidates_for_context("general_listening", "profile-user", limit=1)[0]
    monkeypatch.setattr(
        profile_recommendations,
        "rank_candidates",
        lambda **_: (
            candidate,
            0.0,
            candidate.base_score,
            [{"item_id": candidate.item_id}],
            {"explored": False},
        ),
    )

    response = TestClient(app).get(
        "/v1/users/profile-user/recommendations/profile-aware?context=general_listening"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["item_id"] == "fixture-general-001"
    assert payload["top_artist"] == "Northbound"
    assert payload["taste_confidence"] > 0
    assert "Northbound" in payload["explanation"]

    trace = storage.get_decision_trace(payload["decision_id"])
    assert trace is not None
    assert trace["factors"]["taste_profile"]["evidence_count"] == 2
