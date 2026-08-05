from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import echosense.app as app_module
from echosense.cognitive_memory import CognitiveMemoryStore
from echosense.grounded_recommendation_api import app
from echosense.memory import InMemoryPreferenceMemory
from echosense.providers import FixtureMusicProvider
from echosense.storage import Storage


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    storage = Storage(f"sqlite:///{tmp_path / 'grounded.db'}")
    monkeypatch.setattr(app_module, "storage", storage)
    monkeypatch.setattr(app_module, "music_provider", FixtureMusicProvider())
    monkeypatch.setattr(app_module, "preference_memory", InMemoryPreferenceMemory())
    monkeypatch.setattr(app_module, "exposure_store", None)
    monkeypatch.setenv("ECHOSENSE_EXPLORATION_RATE", "0")
    return TestClient(app)


def grant(storage: Storage, user_id: str, purpose: str) -> None:
    storage.upsert_consent(user_id, purpose, "2026-07-20")


def payload(user_id: str = "user_1") -> dict[str, object]:
    return {
        "user_id": user_id,
        "signals": [
            {
                "type": "activity",
                "value": "driving",
                "confidence": 0.95,
                "purpose_id": "contextual_recommendation",
            },
            {
                "type": "weather",
                "value": "rain",
                "confidence": 0.9,
                "purpose_id": "contextual_recommendation",
            },
        ],
    }


def test_grounded_api_falls_back_without_memory_consent(client: TestClient) -> None:
    storage = app_module.get_storage()
    grant(storage, "user_1", "contextual_recommendation")

    response = client.post("/v1/recommendations", json=payload())

    assert response.status_code == 200
    body = response.json()
    assert body["context"] == "rainy_commute"
    assert body["canonical_track_id"].startswith("es_recording_")
    assert body["provider_binding"]["provider"] == "apple_music"
    assert body["provider_binding"]["provider_track_id"] == body["item_id"]
    assert body["cited_memory_ids"] == []
    assert 0.0 <= body["decision_confidence"] <= 1.0
    trace = storage.get_decision_trace(body["decision_id"])
    assert trace is not None
    assert trace["factors"]["memory_consent"] is False
    assert trace["factors"]["learning_provider"] == "echosense"
    assert trace["factors"]["recommendation"]["canonical_track_id"] == body["canonical_track_id"]
    assert trace["factors"]["understanding"]["memories"] == []


def test_grounded_api_cites_owned_active_memory(client: TestClient) -> None:
    storage = app_module.get_storage()
    grant(storage, "user_1", "contextual_recommendation")
    grant(storage, "user_1", "cognitive_memory")
    CognitiveMemoryStore(storage).remember(
        memory_id="mem_rain_1",
        user_id="user_1",
        memory_type="semantic",
        subject="user_1",
        predicate="prefers",
        object="calm music while driving in rain",
        context="rainy_commute",
        confidence=0.9,
        provenance_type="outcome",
        provenance_ref="outcome_1",
    )

    response = client.post("/v1/recommendations", json=payload())

    assert response.status_code == 200
    body = response.json()
    assert body["cited_memory_ids"] == ["mem_rain_1"]
    assert "1 relevant remembered fact" in body["explanation"]
    trace = storage.get_decision_trace(body["decision_id"])
    assert trace is not None
    assert trace["factors"]["grounded_explanation"]["memory_ids"] == ["mem_rain_1"]


def test_grounded_api_never_uses_another_users_memory(client: TestClient) -> None:
    storage = app_module.get_storage()
    grant(storage, "user_1", "contextual_recommendation")
    grant(storage, "user_1", "cognitive_memory")
    CognitiveMemoryStore(storage).remember(
        memory_id="mem_other",
        user_id="other_user",
        memory_type="semantic",
        subject="other_user",
        predicate="prefers",
        object="rainy commute music",
        context="rainy_commute",
        confidence=1.0,
        provenance_type="outcome",
        provenance_ref="other_outcome",
    )

    response = client.post("/v1/recommendations", json=payload())

    assert response.status_code == 200
    assert response.json()["cited_memory_ids"] == []
