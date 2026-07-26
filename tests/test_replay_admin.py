from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import echosense.operations_api as operations_api
from echosense.dlq_replay import ReplayService
from echosense.replay_audit import ReplayAuditStore
from echosense.storage import Storage


class FakeProducer:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def produce(self, **kwargs: object) -> None:
        self.records.append(kwargs)

    def flush(self, timeout: float) -> int:
        return 0


class FakeRegistry:
    def validate(self, subject: str, event: dict[str, object]) -> int:
        if event.get("event_type") == "invalid.event":
            raise ValueError("invalid event")
        return 42


def envelope(event_id: str = "evt-1", event_type: str = "recommendation.ranked") -> dict[str, object]:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "schema_version": "1.0.0",
        "occurred_at": "2026-07-20T20:00:00+00:00",
        "user_id": "user-1",
        "trace_id": "trace-1",
        "payload": {},
    }


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FakeProducer]:
    store = Storage(f"sqlite:///{tmp_path / 'ops.db'}")
    audit = ReplayAuditStore(store)
    producer = FakeProducer()
    service = ReplayService(producer, FakeRegistry(), audit_store=audit)
    monkeypatch.setenv("ECHOSENSE_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setattr(operations_api, "storage", store)
    monkeypatch.setattr(operations_api, "replay_audit_store", audit)
    monkeypatch.setattr(operations_api, "replay_service", service)
    return TestClient(operations_api.app), producer


def test_replay_admin_requires_authentication(client: tuple[TestClient, FakeProducer]) -> None:
    http, _ = client
    response = http.post("/admin/replays", json={"records": [{"event": envelope()}]})
    assert response.status_code == 401


def test_dry_run_is_audited_without_producing(client: tuple[TestClient, FakeProducer]) -> None:
    http, producer = client
    response = http.post(
        "/admin/replays",
        headers={"X-EchoSense-Admin-Key": "test-admin-key"},
        json={"records": [{"event": envelope()}], "dry_run": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["selected"] == 1
    assert body["replayed"] == 1
    assert producer.records == []

    audit = http.get(
        f"/admin/replays/{body['replay_id']}",
        headers={"X-EchoSense-Admin-Key": "test-admin-key"},
    )
    assert audit.status_code == 200
    assert audit.json()["status"] == "completed"
    assert audit.json()["events"][0]["result"] == "dry_run"


def test_published_and_rejected_records_are_audited(client: tuple[TestClient, FakeProducer]) -> None:
    http, producer = client
    response = http.post(
        "/admin/replays",
        headers={"X-EchoSense-Admin-Key": "test-admin-key"},
        json={
            "records": [
                {"event": envelope("evt-ok")},
                {"event": envelope("evt-bad", "invalid.event")},
                {"event": envelope("evt-loop"), "replay_count": 1},
            ],
            "dry_run": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["selected"] == 2
    assert body["replayed"] == 1
    assert body["rejected"] == 2
    assert len(producer.records) == 1
    headers = dict(producer.records[0]["headers"])
    assert headers["replay_id"].decode() == body["replay_id"]

    audit = http.get(
        f"/admin/replays/{body['replay_id']}",
        headers={"X-EchoSense-Admin-Key": "test-admin-key"},
    ).json()
    assert {event["result"] for event in audit["events"]} == {
        "published",
        "rejected",
        "loop_rejected",
    }


def test_replay_request_is_bounded(client: tuple[TestClient, FakeProducer]) -> None:
    http, _ = client
    response = http.post(
        "/admin/replays",
        headers={"X-EchoSense-Admin-Key": "test-admin-key"},
        json={"records": [{"event": envelope(str(index))} for index in range(101)]},
    )
    assert response.status_code == 422
