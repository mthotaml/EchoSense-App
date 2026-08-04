from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import echosense.app as app_module
from echosense.memory import InMemoryPreferenceMemory
from echosense.providers import FixtureMusicProvider
from echosense.storage import Storage


def test_in_memory_learning_is_idempotent_and_bounded() -> None:
    memory = InMemoryPreferenceMemory()
    first = memory.apply_outcome(
        user_id="u1",
        provider="apple_music",
        item_id="song-1",
        context="rainy_commute",
        delta=0.12,
        outcome_id="outcome-1",
    )
    duplicate = memory.apply_outcome(
        user_id="u1",
        provider="apple_music",
        item_id="song-1",
        context="rainy_commute",
        delta=0.12,
        outcome_id="outcome-1",
    )
    assert duplicate.weight == first.weight
    assert duplicate.evidence_count == 1

    for index in range(20):
        result = memory.apply_outcome(
            user_id="u1",
            provider="apple_music",
            item_id="song-1",
            context="rainy_commute",
            delta=0.12,
            outcome_id=f"positive-{index}",
        )
    assert result.weight == 1.0

    for index in range(30):
        result = memory.apply_outcome(
            user_id="u1",
            provider="apple_music",
            item_id="song-1",
            context="rainy_commute",
            delta=-0.15,
            outcome_id=f"negative-{index}",
        )
    assert result.weight == -1.0


def test_preference_weight_halves_after_one_half_life() -> None:
    memory = InMemoryPreferenceMemory()
    preference = memory.apply_outcome(
        user_id="u1",
        provider="apple_music",
        item_id="song-1",
        context="rainy_commute",
        delta=1.0,
        outcome_id="outcome-1",
    )
    future = preference.decay_anchor + timedelta(days=30)

    weights = memory.rank_weights(
        user_id="u1",
        context="rainy_commute",
        candidates=[("apple_music", "song-1")],
        now=future,
        half_life_days=30,
    )

    assert weights[("apple_music", "song-1")] == 0.5
    assert memory.decay_preferences(now=future, half_life_days=30) == 1
    stored = memory.get_preference(
        user_id="u1",
        provider="apple_music",
        item_id="song-1",
        context="rainy_commute",
    )
    assert stored is not None
    assert stored.weight == 0.5
    assert stored.evidence_count == 1


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    store = Storage(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(app_module, "storage", store)
    monkeypatch.setattr(app_module, "music_provider", FixtureMusicProvider())
    monkeypatch.setattr(app_module, "preference_memory", InMemoryPreferenceMemory())
    monkeypatch.setattr(app_module, "exposure_store", None)
    monkeypatch.setenv("ECHOSENSE_EXPLORATION_RATE", "0")
    return TestClient(app_module.app)


def grant_consent(client: TestClient) -> None:
    response = client.put(
        "/v1/consents",
        json={
            "user_id": "user_fixture_01",
            "purpose_id": "contextual_recommendation",
            "policy_version": "2026-07-20",
        },
    )
    assert response.status_code == 204


def recommendation_payload() -> dict[str, object]:
    return {
        "user_id": "user_fixture_01",
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


def test_outcome_updates_preference_from_recorded_decision(client: TestClient) -> None:
    grant_consent(client)
    recommendation = client.post("/v1/recommendations", json=recommendation_payload())
    decision_id = recommendation.json()["decision_id"]

    outcome = client.post(
        "/v1/outcomes",
        json={
            "outcome_id": "outcome-fixture-1",
            "user_id": "user_fixture_01",
            "decision_id": decision_id,
            "outcome": "liked",
        },
    )
    assert outcome.status_code == 200
    body = outcome.json()
    assert body["context"] == "rainy_commute"
    assert body["provider"] == "echosense"
    assert body["item_id"].startswith("es_recording_")
    assert body["weight"] == 0.12
    assert body["evidence_count"] == 1

    duplicate = client.post(
        "/v1/outcomes",
        json={
            "outcome_id": "outcome-fixture-1",
            "user_id": "user_fixture_01",
            "decision_id": decision_id,
            "outcome": "liked",
        },
    )
    assert duplicate.json()["weight"] == 0.12
    assert duplicate.json()["evidence_count"] == 1


def test_negative_preference_can_demote_provider_favorite(client: TestClient) -> None:
    grant_consent(client)
    memory = app_module.get_preference_memory()
    for index in range(8):
        memory.apply_outcome(
            user_id="user_fixture_01",
            provider="apple_music",
            item_id="fixture-rain-001",
            context="rainy_commute",
            delta=-0.15,
            outcome_id=f"dislike-{index}",
        )

    recommendation = client.post("/v1/recommendations", json=recommendation_payload())

    assert recommendation.status_code == 200
    assert recommendation.json()["item_id"] == "fixture-rain-002"
    trace = client.get(f"/v1/decision-traces/{recommendation.json()['decision_id']}").json()
    assert trace["factors"]["candidate_count"] == 3
    assert trace["factors"]["preference_weight"] == 0.0
    assert trace["factors"]["ranking_score"] == 0.75
