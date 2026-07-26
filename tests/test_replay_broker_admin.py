from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import echosense.operations_api as operations_api
from echosense.dlq_consumer import DLQBatch, DLQRecord
from echosense.dlq_replay import ReplayService
from echosense.replay_audit import ReplayAuditStore
from echosense.storage import Storage


class Producer:
    def produce(self, **kwargs: object) -> None:
        pass

    def flush(self, timeout: float) -> int:
        return 0


class Registry:
    def validate(self, subject: str, event: dict[str, object]) -> int:
        return 1


class Source:
    def __init__(self) -> None:
        self.committed = False

    def fetch(self, *, topic: str, partition: int, offset: int, limit: int) -> DLQBatch:
        record = DLQRecord(
            topic=topic,
            partition=partition,
            offset=offset,
            value={
                "event": {
                    "event_id": "evt-broker",
                    "event_type": "recommendation.ranked",
                    "schema_version": "1.0.0",
                    "occurred_at": "2026-07-20T20:00:00+00:00",
                    "user_id": "user-1",
                    "trace_id": "trace-1",
                    "payload": {},
                }
            },
        )
        return DLQBatch([record], topic, partition, offset, offset + 1)

    def commit(self, batch: DLQBatch) -> None:
        self.committed = True


@pytest.fixture()
def context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Source]:
    store = Storage(f"sqlite:///{tmp_path / 'broker.db'}")
    audit = ReplayAuditStore(store)
    source = Source()
    monkeypatch.setenv("ECHOSENSE_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setattr(operations_api, "storage", store)
    monkeypatch.setattr(operations_api, "replay_audit_store", audit)
    monkeypatch.setattr(
        operations_api, "replay_service", ReplayService(Producer(), Registry(), audit_store=audit)
    )
    monkeypatch.setattr(operations_api, "dlq_consumer", source)
    return TestClient(operations_api.app), source


def test_broker_window_requires_explicit_commit(context: tuple[TestClient, Source]) -> None:
    client, source = context
    response = client.post(
        "/admin/replays",
        headers={"X-EchoSense-Admin-Key": "test-admin-key"},
        json={
            "topic": "echosense.events.dlq.v1",
            "partition": 0,
            "offset": 12,
            "limit": 1,
            "dry_run": False,
            "commit_offsets": False,
        },
    )
    assert response.status_code == 200
    assert source.committed is False

    committed = client.post(
        "/admin/replays",
        headers={"X-EchoSense-Admin-Key": "test-admin-key"},
        json={
            "topic": "echosense.events.dlq.v1",
            "partition": 0,
            "offset": 12,
            "limit": 1,
            "dry_run": False,
            "commit_offsets": True,
        },
    )
    assert committed.status_code == 200
    assert source.committed is True


def test_dry_run_cannot_commit_offsets(context: tuple[TestClient, Source]) -> None:
    client, _ = context
    response = client.post(
        "/admin/replays",
        headers={"X-EchoSense-Admin-Key": "test-admin-key"},
        json={
            "topic": "echosense.events.dlq.v1",
            "partition": 0,
            "offset": 0,
            "dry_run": True,
            "commit_offsets": True,
        },
    )
    assert response.status_code == 422
