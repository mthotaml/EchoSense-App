import json
from pathlib import Path

from jsonschema import ValidationError

from echosense.outbox_publisher import OutboxPublisher
from echosense.storage import Storage


class FakeRegistry:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.envelopes: list[dict[str, object]] = []

    def validate(self, subject: str, envelope: dict[str, object]) -> int:
        assert subject == "echosense.events.v1-value"
        self.envelopes.append(envelope)
        if self.error:
            raise self.error
        return 42


class FakeProducer:
    def __init__(self, fail_topics: set[str] | None = None) -> None:
        self.messages: list[tuple[str, str, bytes, list[tuple[str, bytes]]]] = []
        self.fail_topics = fail_topics or set()

    def produce(self, topic: str, key: str, value: bytes, headers: list[tuple[str, bytes]]) -> None:
        if topic in self.fail_topics:
            raise RuntimeError(f"unavailable topic: {topic}")
        self.messages.append((topic, key, value, headers))

    def flush(self, timeout: float | None = None) -> int:
        return 0


def append_fixture_event(storage: Storage, event_id: str = "evt_01") -> None:
    storage.append_event(
        event_id=event_id,
        event_type="consent.granted",
        user_id="user_01",
        trace_id="trc_01",
        payload={"purpose_id": "contextual_recommendation"},
    )


def test_outbox_event_is_validated_and_published_once(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'outbox.db'}")
    append_fixture_event(storage)
    producer = FakeProducer()
    registry = FakeRegistry()
    publisher = OutboxPublisher(storage, producer, registry, worker_id="worker-test")

    assert publisher.publish_batch() == 1
    assert publisher.publish_batch() == 0
    assert len(producer.messages) == 1
    topic, key, value, headers = producer.messages[0]
    assert topic == "echosense.events.v1"
    assert key == "evt_01"
    assert json.loads(value)["schema_version"] == "1.0"
    assert ("schema_id", b"42") in headers
    assert len(registry.envelopes) == 1


def test_schema_validation_failure_is_dead_lettered_immediately(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'invalid.db'}")
    append_fixture_event(storage, "evt_invalid")
    producer = FakeProducer()
    publisher = OutboxPublisher(
        storage,
        producer,
        FakeRegistry(ValidationError("payload violates schema")),
        worker_id="worker-test",
    )

    assert publisher.publish_batch() == 1
    assert publisher.publish_batch() == 0
    topic, key, value, headers = producer.messages[0]
    body = json.loads(value)
    assert topic == "echosense.events.dlq.v1"
    assert key == "evt_invalid"
    assert body["failure_type"] == "schema_validation"
    assert body["event"]["event_id"] == "evt_invalid"
    assert ("dead_letter", b"true") in headers


def test_publish_failure_is_dead_lettered_after_retry_limit(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'retry.db'}")
    append_fixture_event(storage, "evt_retry")
    producer = FakeProducer(fail_topics={"echosense.events.v1"})
    publisher = OutboxPublisher(
        storage,
        producer,
        FakeRegistry(),
        worker_id="worker-test",
        max_attempts=2,
    )

    assert publisher.publish_batch() == 0
    assert publisher.publish_batch() == 1
    assert len(producer.messages) == 1
    topic, _, value, _ = producer.messages[0]
    body = json.loads(value)
    assert topic == "echosense.events.dlq.v1"
    assert body["failure_type"] == "publish_exhausted"
    assert body["publish_attempts"] == 2
