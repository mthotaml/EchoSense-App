from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import echosense.cognitive_memory_api as api
from echosense.cognitive_memory import CognitiveMemoryStore
from echosense.storage import Storage


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    store = Storage(f"sqlite:///{tmp_path / 'memory-api.db'}")
    monkeypatch.setattr(api, "storage", store)
    monkeypatch.setattr(api, "memory_store", CognitiveMemoryStore(store))
    return TestClient(api.app)


def grant_consent(client: TestClient, user_id: str) -> None:
    api.get_storage().upsert_consent(user_id, api.MEMORY_PURPOSE, "2026-07-20")


def payload(memory_id: str = "mem-1", object_value: str = "train") -> dict[str, object]:
    return {
        "memory_id": memory_id,
        "memory_type": "semantic",
        "subject": "commute",
        "predicate": "usual_mode",
        "object": object_value,
        "context": "weekday",
        "confidence": 0.9,
        "provenance_type": "explicit_statement",
        "provenance_ref": "signal-1",
    }


def test_write_requires_memory_consent(client: TestClient) -> None:
    response = client.put("/v1/users/u1/memories/mem-1", json=payload())
    assert response.status_code == 403
    assert response.json()["detail"]["missing_purposes"] == ["cognitive_memory"]


def test_write_get_and_search_are_user_scoped(client: TestClient) -> None:
    grant_consent(client, "u1")
    grant_consent(client, "u2")

    created = client.put("/v1/users/u1/memories/mem-1", json=payload())
    assert created.status_code == 201
    assert created.json()["user_id"] == "u1"

    fetched = client.get("/v1/users/u1/memories/mem-1")
    assert fetched.status_code == 200
    assert fetched.json()["object"] == "train"

    cross_user = client.get("/v1/users/u2/memories/mem-1")
    assert cross_user.status_code == 404

    results = client.post(
        "/v1/users/u1/memories:search",
        json={"query": "weekday commute train", "limit": 5},
    )
    assert results.status_code == 200
    assert results.json()[0]["memory"]["memory_id"] == "mem-1"


def test_semantic_update_exposes_supersession(client: TestClient) -> None:
    grant_consent(client, "u1")
    first = client.put("/v1/users/u1/memories/mem-1", json=payload())
    second = client.put(
        "/v1/users/u1/memories/mem-2",
        json=payload("mem-2", "bicycle"),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["supersedes_memory_id"] == "mem-1"
    assert client.get("/v1/users/u1/memories/mem-1").json()["status"] == "superseded"


def test_memory_id_must_match_path(client: TestClient) -> None:
    grant_consent(client, "u1")
    response = client.put("/v1/users/u1/memories/other", json=payload())
    assert response.status_code == 422


def test_recording_emits_outbox_event(client: TestClient) -> None:
    grant_consent(client, "u1")
    response = client.put("/v1/users/u1/memories/mem-1", json=payload())
    assert response.status_code == 201

    with api.get_storage().connect() as connection:
        row = api.get_storage()._execute(
            connection,
            "SELECT event_type, user_id FROM event_outbox WHERE event_type = %s",
            ("memory.recorded",),
        ).fetchone()
    assert dict(row) == {"event_type": "memory.recorded", "user_id": "u1"}
