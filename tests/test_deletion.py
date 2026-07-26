from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import echosense.app as app_module
from echosense.cognitive_memory import CognitiveMemoryStore
from echosense.evaluation_service import EvaluationService
from echosense.exposure_store import ExposureStore
from echosense.memory import InMemoryPreferenceMemory
from echosense.memory_lifecycle_service import MemoryLifecycleService
from echosense.providers import FixtureMusicProvider
from echosense.storage import Storage


@pytest.fixture()
def deletion_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, Storage, InMemoryPreferenceMemory]:
    store = Storage(f"sqlite:///{tmp_path / 'deletion.db'}")
    memory = InMemoryPreferenceMemory()
    monkeypatch.setattr(app_module, "storage", store)
    monkeypatch.setattr(app_module, "preference_memory", memory)
    monkeypatch.setattr(app_module, "music_provider", FixtureMusicProvider())
    monkeypatch.setattr(app_module, "deletion_coordinator", None)
    monkeypatch.setattr(app_module, "evaluation_service", None)
    monkeypatch.setattr(app_module, "exposure_store", None)
    monkeypatch.setenv("ECHOSENSE_DELETION_HASH_SALT", "test-only-salt")
    return TestClient(app_module.app), store, memory


def seed_user(store: Storage, memory: InMemoryPreferenceMemory) -> str:
    user_id = "user-delete-01"
    store.upsert_consent(user_id, "contextual_recommendation", "2026-07-20")
    store.upsert_apple_music_user_token(user_id, "encrypted-secret")
    store.save_decision_trace(
        decision_id="dec-delete-01",
        user_id=user_id,
        context="rainy_commute",
        context_confidence=0.9,
        provider="apple_music",
        item_id="fixture-rain-001",
        factors={
            "weather": "rain",
            "candidate_slate": [
                {
                    "provider": "apple_music",
                    "item_id": "fixture-rain-001",
                    "rank": 1,
                    "provider_base_score": 0.8,
                    "preference_weight": 0.0,
                    "ranking_score": 0.8,
                    "selected": True,
                },
                {
                    "provider": "apple_music",
                    "item_id": "fixture-rain-002",
                    "rank": 2,
                    "provider_base_score": 0.7,
                    "preference_weight": 0.0,
                    "ranking_score": 0.7,
                    "selected": False,
                },
            ],
        },
    )
    store.append_event(
        event_id="evt-delete-01",
        event_type="recommendation.ranked",
        user_id=user_id,
        trace_id="trc-delete-01",
        payload={"decision_id": "dec-delete-01"},
    )
    ExposureStore(store).record_selection(user_id, "apple_music", "fixture-rain-001")
    CognitiveMemoryStore(store).remember(
        memory_id="mem-delete-01",
        user_id=user_id,
        memory_type="semantic",
        subject="commute",
        predicate="preferred_music",
        object="instrumental",
        context="rainy_commute",
        confidence=0.8,
        provenance_type="outcome",
        provenance_ref="outcome-delete-01",
    )
    MemoryLifecycleService(store).execute(
        run_id="lifecycle-delete-01",
        user_id=user_id,
        mode="dry_run",
    )
    memory.apply_outcome(
        user_id=user_id,
        provider="apple_music",
        item_id="fixture-rain-001",
        context="rainy_commute",
        delta=0.12,
        outcome_id="outcome-delete-01",
    )
    EvaluationService(store).attribute_and_evaluate(
        outcome_id="outcome-evaluation-delete-01",
        decision_id="dec-delete-01",
        outcome="liked",
        completion_ratio=1.0,
    )
    return user_id


def test_deletion_requires_explicit_confirmation(
    deletion_context: tuple[TestClient, Storage, InMemoryPreferenceMemory],
) -> None:
    client, _, _ = deletion_context
    response = client.post(
        "/v1/users/user-delete-01/deletions",
        json={"purpose_id": "contextual_recommendation", "confirmation": "no"},
    )
    assert response.status_code == 422


def test_deletion_removes_sql_tokens_memory_evaluation_and_exposures(
    deletion_context: tuple[TestClient, Storage, InMemoryPreferenceMemory],
) -> None:
    client, store, memory = deletion_context
    user_id = seed_user(store, memory)

    response = client.post(
        f"/v1/users/{user_id}/deletions",
        json={"purpose_id": "contextual_recommendation", "confirmation": "delete"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["counts"] == {
        "attributed_outcomes": 1,
        "counterfactual_reports": 1,
        "cognitive_memories": 1,
        "memory_lifecycle_runs": 1,
        "recommendation_exposures": 1,
        "decision_traces": 1,
        "provider_tokens": 1,
        "outbox_events": 2,
        "consent_grants": 1,
        "preferences": 1,
        "learning_outcomes": 1,
    }
    assert body["subject_hash"] != user_id
    assert not store.has_active_consent(user_id, "contextual_recommendation")
    assert store.get_decision_trace("dec-delete-01") is None
    assert store.get_apple_music_user_token(user_id) is None
    assert CognitiveMemoryStore(store).get("mem-delete-01") is None
    assert MemoryLifecycleService(store).get("lifecycle-delete-01") is None
    assert memory.get_preference(
        user_id=user_id,
        provider="apple_music",
        item_id="fixture-rain-001",
        context="rainy_commute",
    ) is None

    with store.connect() as connection:
        outcomes = store._execute(
            connection,
            "SELECT COUNT(*) AS count FROM attributed_outcomes WHERE decision_id = %s",
            ("dec-delete-01",),
        ).fetchone()
        reports = store._execute(
            connection,
            "SELECT COUNT(*) AS count FROM counterfactual_reports WHERE decision_id = %s",
            ("dec-delete-01",),
        ).fetchone()
        exposures = store._execute(
            connection,
            "SELECT COUNT(*) AS count FROM recommendation_exposures WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    assert int(dict(outcomes)["count"]) == 0
    assert int(dict(reports)["count"]) == 0
    assert int(dict(exposures)["count"]) == 0

    status = client.get(f"/v1/deletions/{body['deletion_id']}")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    assert "user_id" not in status.json()

    with store.connect() as connection:
        old_events = store._execute(
            connection,
            "SELECT COUNT(*) AS count FROM event_outbox WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        receipt_events = store._execute(
            connection,
            "SELECT COUNT(*) AS count FROM event_outbox WHERE event_type = %s",
            ("privacy.user_data.deleted",),
        ).fetchone()
    assert int(dict(old_events)["count"]) == 0
    assert int(dict(receipt_events)["count"]) == 1
