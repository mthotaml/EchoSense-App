from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import echosense.app as app_module
from echosense.memory import InMemoryPreferenceMemory
from echosense.providers import FixtureMusicProvider
from echosense.storage import Storage


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    storage = Storage(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(app_module, "storage", storage)
    monkeypatch.setattr(app_module, "music_provider", FixtureMusicProvider())
    monkeypatch.setattr(app_module, "preference_memory", InMemoryPreferenceMemory())
    monkeypatch.setattr(app_module, "evaluation_service", None)
    monkeypatch.setattr(app_module, "deletion_coordinator", None)
    monkeypatch.setattr(app_module, "exposure_store", None)
    monkeypatch.setenv("ECHOSENSE_EXPLORATION_RATE", "0")
    return TestClient(app_module.app)


def recommendation_payload(user_id: str = "user_fixture_01") -> dict[str, object]:
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


def grant_consent(client: TestClient, user_id: str = "user_fixture_01") -> None:
    response = client.put(
        "/v1/consents",
        json={
            "user_id": user_id,
            "purpose_id": "contextual_recommendation",
            "policy_version": "2026-07-20",
        },
    )
    assert response.status_code == 204


def test_recommendation_requires_server_side_consent(client: TestClient) -> None:
    response = client.post("/v1/recommendations", json=recommendation_payload())
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "consent_required"


def test_rainy_commute_recommendation_is_grounded_and_traceable(client: TestClient) -> None:
    grant_consent(client)
    response = client.post("/v1/recommendations", json=recommendation_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["context"] == "rainy_commute"
    assert body["provider"] == "apple_music"
    assert "rainy drive" in body["explanation"]
    assert body["decision_id"].startswith("dec_")

    trace = client.get(f"/v1/decision-traces/{body['decision_id']}")
    assert trace.status_code == 200
    factors = trace.json()["factors"]
    assert factors["activity"] == "driving"
    assert factors["weather"] == "rain"
    assert factors["candidate_count"] == 3
    assert factors["provider_base_score"] == 0.8
    assert factors["preference_weight"] == 0.0
    assert factors["ranking_policy"]["novelty_weight"] == 0.05
    assert factors["ranking_policy"]["explored"] is False
    assert len(factors["candidate_slate"]) == 3
    assert factors["candidate_slate"][0]["selected"] is True
    assert factors["candidate_slate"][0]["rank"] == 1
    assert factors["candidate_slate"][0]["novelty_score"] == 1.0
    assert factors["candidate_slate"][0]["exposure_count"] == 0
    assert factors["candidate_slate"][1]["selected"] is False


def test_selected_item_exposure_reduces_its_future_novelty(client: TestClient) -> None:
    grant_consent(client)
    first = client.post("/v1/recommendations", json=recommendation_payload()).json()
    second = client.post("/v1/recommendations", json=recommendation_payload()).json()

    first_trace = client.get(f"/v1/decision-traces/{first['decision_id']}").json()
    second_trace = client.get(f"/v1/decision-traces/{second['decision_id']}").json()
    first_selected = first_trace["factors"]["candidate_slate"][0]
    second_candidates = {
        item["item_id"]: item for item in second_trace["factors"]["candidate_slate"]
    }

    assert first_selected["exposure_count"] == 0
    assert second_candidates[first["item_id"]]["exposure_count"] == 1
    assert second_candidates[first["item_id"]]["novelty_score"] == 0.5


def test_counterfactual_evaluation_is_consent_protected_and_idempotent(
    client: TestClient,
) -> None:
    grant_consent(client)
    decision = client.post("/v1/recommendations", json=recommendation_payload()).json()
    request = {
        "outcome_id": "outcome_eval_01",
        "user_id": "user_fixture_01",
        "decision_id": decision["decision_id"],
        "outcome": "liked",
        "playback_seconds": 180.0,
        "completion_ratio": 0.95,
    }

    first = client.post("/v1/evaluations/outcomes", json=request)
    second = client.post("/v1/evaluations/outcomes", json=request)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["selected_item_id"] == decision["item_id"]
    assert first.json()["confidence"] == "medium"

    stored = client.get(
        "/v1/evaluations/outcomes/outcome_eval_01",
        params={"user_id": "user_fixture_01"},
    )
    assert stored.status_code == 200
    assert stored.json() == first.json()


def test_evaluation_report_isolated_by_user_and_blocked_after_revocation(
    client: TestClient,
) -> None:
    grant_consent(client)
    grant_consent(client, "other_user")
    decision = client.post("/v1/recommendations", json=recommendation_payload()).json()
    result = client.post(
        "/v1/evaluations/outcomes",
        json={
            "outcome_id": "outcome_private_01",
            "user_id": "user_fixture_01",
            "decision_id": decision["decision_id"],
            "outcome": "completed",
            "completion_ratio": 1.0,
        },
    )
    assert result.status_code == 200

    cross_user = client.get(
        "/v1/evaluations/outcomes/outcome_private_01",
        params={"user_id": "other_user"},
    )
    assert cross_user.status_code == 404

    revoke = client.delete(
        "/v1/users/user_fixture_01/consents/contextual_recommendation"
    )
    assert revoke.status_code == 204
    revoked = client.get(
        "/v1/evaluations/outcomes/outcome_private_01",
        params={"user_id": "user_fixture_01"},
    )
    assert revoked.status_code == 403


def test_revocation_blocks_future_processing(client: TestClient) -> None:
    grant_consent(client)
    revoke = client.delete(
        "/v1/users/user_fixture_01/consents/contextual_recommendation"
    )
    assert revoke.status_code == 204

    response = client.post("/v1/recommendations", json=recommendation_payload())
    assert response.status_code == 403
