from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime, timezone
from typing import Any, Protocol

from jsonschema import ValidationError

from echosense.event_schema import SchemaRegistry, registry_from_environment
from echosense.operations import (
    DEAD_LETTERED,
    PUBLISH_LATENCY,
    PUBLISHED,
    RETRIES,
    VALIDATION_FAILURES,
)
from echosense.storage import Storage


class Producer(Protocol):
    def produce(
        self, topic: str, key: str, value: bytes, headers: list[tuple[str, bytes]]
    ) -> None: ...

    def flush(self, timeout: float | None = None) -> int: ...


class RedpandaProducer:
    def __init__(self, bootstrap_servers: str) -> None:
        from confluent_kafka import Producer as KafkaProducer

        self._producer = KafkaProducer(
            {
                "bootstrap.servers": bootstrap_servers,
                "enable.idempotence": True,
                "acks": "all",
                "compression.type": "zstd",
                "client.id": "echosense-outbox-publisher",
            }
        )

    def produce(self, topic: str, key: str, value: bytes, headers: list[tuple[str, bytes]]) -> None:
        self._producer.produce(topic=topic, key=key, value=value, headers=headers)

    def flush(self, timeout: float | None = None) -> int:
        return self._producer.flush(timeout)


class OutboxPublisher:
    def __init__(
        self,
        storage: Storage,
        producer: Producer,
        registry: SchemaRegistry,
        topic: str = "echosense.events.v1",
        dead_letter_topic: str = "echosense.events.dlq.v1",
        worker_id: str | None = None,
        max_attempts: int = 5,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.storage = storage
        self.producer = producer
        self.registry = registry
        self.topic = topic
        self.dead_letter_topic = dead_letter_topic
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.max_attempts = max_attempts
        self.subject = f"{topic}-value"

    @staticmethod
    def _envelope(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "schema_version": "1.0",
            "occurred_at": event["occurred_at"],
            "user_id": event["user_id"],
            "trace_id": event["trace_id"],
            "payload": event["payload"],
        }

    def _produce_and_ack(
        self,
        *,
        topic: str,
        key: str,
        value: dict[str, Any],
        headers: list[tuple[str, bytes]],
    ) -> None:
        started = time.monotonic()
        try:
            self.producer.produce(
                topic=topic,
                key=key,
                value=json.dumps(value, separators=(",", ":")).encode(),
                headers=headers,
            )
            if self.producer.flush(10.0) != 0:
                raise RuntimeError("producer flush timed out")
        finally:
            PUBLISH_LATENCY.observe(time.monotonic() - started)

    def _dead_letter(self, event: dict[str, Any], envelope: dict[str, Any], exc: Exception) -> bool:
        failure_type = (
            "schema_validation" if isinstance(exc, ValidationError) else "publish_exhausted"
        )
        dead_letter = {
            "dead_lettered_at": datetime.now(timezone.utc).isoformat(),
            "failure_type": failure_type,
            "failure_message": str(exc)[:1000],
            "original_topic": self.topic,
            "publish_attempts": int(event["publish_attempts"]),
            "replay_count": 0,
            "event": envelope,
        }
        self._produce_and_ack(
            topic=self.dead_letter_topic,
            key=event["event_id"],
            value=dead_letter,
            headers=[
                ("dead_letter", b"true"),
                ("failure_type", failure_type.encode()),
                ("original_topic", self.topic.encode()),
                ("event_type", event["event_type"].encode()),
            ],
        )
        DEAD_LETTERED.labels(failure_type=failure_type).inc()
        return self.storage.mark_event_published(event["event_id"], self.worker_id)

    def publish_batch(self, limit: int = 100) -> int:
        published = 0
        events = self.storage.claim_outbox(self.worker_id, limit=limit)
        for event in events:
            envelope = self._envelope(event)
            try:
                schema_id = self.registry.validate(self.subject, envelope)
                self._produce_and_ack(
                    topic=self.topic,
                    key=event["event_id"],
                    value=envelope,
                    headers=[
                        ("event_type", event["event_type"].encode()),
                        ("schema_version", b"1.0"),
                        ("schema_id", str(schema_id).encode()),
                        ("schema_subject", self.subject.encode()),
                    ],
                )
                if self.storage.mark_event_published(event["event_id"], self.worker_id):
                    published += 1
                    PUBLISHED.inc()
            except Exception as exc:
                if isinstance(exc, ValidationError):
                    VALIDATION_FAILURES.inc()
                should_dead_letter = (
                    isinstance(exc, ValidationError)
                    or int(event["publish_attempts"]) >= self.max_attempts
                )
                if should_dead_letter:
                    try:
                        if self._dead_letter(event, envelope, exc):
                            published += 1
                    except Exception as dlq_exc:
                        RETRIES.inc()
                        self.storage.release_event_claim(
                            event["event_id"], self.worker_id, f"DLQ publish failed: {dlq_exc}"
                        )
                else:
                    RETRIES.inc()
                    self.storage.release_event_claim(event["event_id"], self.worker_id, str(exc))
        return published


def main() -> None:
    database_url = os.getenv(
        "ECHOSENSE_DATABASE_URL",
        "postgresql://echosense:echosense@localhost:5432/echosense",
    )
    bootstrap_servers = os.getenv("ECHOSENSE_KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    poll_seconds = float(os.getenv("ECHOSENSE_OUTBOX_POLL_SECONDS", "1"))
    publisher = OutboxPublisher(
        Storage(database_url),
        RedpandaProducer(bootstrap_servers),
        registry_from_environment(),
        topic=os.getenv("ECHOSENSE_EVENT_TOPIC", "echosense.events.v1"),
        dead_letter_topic=os.getenv("ECHOSENSE_EVENT_DLQ_TOPIC", "echosense.events.dlq.v1"),
        max_attempts=int(os.getenv("ECHOSENSE_OUTBOX_MAX_ATTEMPTS", "5")),
    )
    while True:
        published = publisher.publish_batch()
        if published == 0:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
