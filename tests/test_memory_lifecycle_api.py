from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import echosense.memory_lifecycle_api as api
from echosense.cognitive_memory import CognitiveMemoryStore
from echosense.memory_lifecycle_service import MemoryLifecycleService
from echosense.storage import Storage


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    store = Storage(f"sqlite:///{tmp_path / 'lifecycle-api.db'}")
    monkeypatch.setattr(api, "storage", store)
    monkeypatch.setattr(api, "lifecycle_service", MemoryLifecycleService(store))
    return TestClient(api.app)


def grant_consent(user_id: str) -> None:
    api.get_storage().upsert_consent(user_id, api.MEMORY_PURPOSE, "2026-07-20")


def add_episodic_memories(user_id: str) -> None:
    memory_store = CognitiveMemoryStore(api.get_storage())
    for index in range(3):
        memory_store.remember(
            memory_id=f"mem_{user_id}_{index}",
            user_id=user_id,
            memory_type="episodic",
            subject=user_id,
            predicate="prefers",
            object="calm music",
            context="rainy_commute",
            confidence=0.8,
            provenance_type="outcome",
            provenance_ref=f"outcome_{user_id}_{index}",
        )


def test_execute_requires_memory_consent(client: TestClient) -> None:
    response = client.post(
        "/v1/users/u1/memory-lifecycle-runs",
        json={"run_id": "run_1"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["missing_purposes"] == ["cognitive_memory"]


def test_dry_run_is_deterministic_and_retrievable(client: TestClient) -> None:
    grant_consent("u1")
    add_episodic_memories("u1")
    payload = {
        "run_id": "run_1",
        "mode": "dry_run",
        "protected_memory_ids": ["mem_manual", "mem_manual"],
    }

    first = client.post("/v1/users/u1/memory-lifecycle-runs", json=payload)
    second = client.post("/v1/users/u1/memory-lifecycle-runs", json=payload)
    fetched = client.get("/v1/users/u1/memory-lifecycle-runs/run_1")

    assert first.status_code == 200
    assert second.status_code == 200
    assert fetched.status_code == 200
    assert first.json() == second.json() == fetched.json()
    assert len(first.json()["plan"]["consolidations"]) == 1
    assert first.json()["consolidated_memory_ids"] == []
    assert "mem_manual" in first.json()["plan"]["protected_memory_ids"]


def test_apply_is_user_scoped_and_conflicts_on_mode_reuse(client: TestClient) -> None:
    grant_consent("u1")
    grant_consent("u2")
    add_episodic_memories("u1")

    applied = client.post(
        "/v1/users/u1/memory-lifecycle-runs",
        json={"run_id": "run_apply", "mode": "apply"},
    )
    cross_user = client.get("/v1/users/u2/memory-lifecycle-runs/run_apply")
    conflict = client.post(
        "/v1/users/u1/memory-lifecycle-runs",
        json={"run_id": "run_apply", "mode": "dry_run"},
    )

    assert applied.status_code == 200
    assert len(applied.json()["consolidated_memory_ids"]) == 1
    assert cross_user.status_code == 404
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "lifecycle_run_conflict"
