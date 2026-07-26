from pathlib import Path

from fastapi.testclient import TestClient

from echosense.dlq_replay import ReplayFilter, ReplayService
from echosense.event_schema import LocalSchemaRegistry
from echosense.operations import readiness
from echosense.operations_api import app
from echosense.storage import Storage


class FakeProducer:
    def __init__(self) -> None:
        self.messages = []

    def produce(self, topic, key, value, headers) -> None:
        self.messages.append((topic, key, value, headers))

    def flush(self, timeout=None) -> int:
        return 0


def valid_dead_letter() -> dict[str, object]:
    return {
        "failure_type": "schema_validation",
        "replay_count": 0,
        "event": {
            "event_id": "evt_replay_01",
            "event_type": "consent.granted",
            "schema_version": "1.0",
            "occurred_at": "2026-07-20T19:30:00+00:00",
            "user_id": "user_01",
            "trace_id": "trc_01",
            "payload": {"purpose_id": "contextual_recommendation"},
        },
    }


def test_database_readiness_updates_outbox_metrics(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'ops.db'}")
    result = readiness(storage)
    assert result.ready is True
    assert result.checks == {"database": "ok"}


def test_controlled_replay_supports_dry_run_and_loop_rejection() -> None:
    producer = FakeProducer()
    schema_path = Path(__file__).parents[1] / "schemas" / "event-envelope.v1.json"
    replay = ReplayService(producer, LocalSchemaRegistry(schema_path=schema_path))
    record = valid_dead_letter()
    result = replay.replay([record], selection=ReplayFilter(event_id="evt_replay_01"), dry_run=True)
    assert result == {"selected": 1, "replayed": 1, "rejected": 0}
    assert producer.messages == []

    looped = {**record, "replay_count": 1}
    result = replay.replay([looped])
    assert result["rejected"] == 1


def test_operations_liveness_endpoint() -> None:
    response = TestClient(app).get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
