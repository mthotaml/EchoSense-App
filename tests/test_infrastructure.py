import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from confluent_kafka import Consumer

from echosense.event_schema import ConfluentSchemaRegistry
from echosense.outbox_publisher import OutboxPublisher, RedpandaProducer
from echosense.storage import Storage


@pytest.mark.infrastructure
def test_postgres_outbox_reaches_redpanda() -> None:
    database_url = os.environ["ECHOSENSE_DATABASE_URL"]
    bootstrap_servers = os.environ["ECHOSENSE_KAFKA_BOOTSTRAP_SERVERS"]
    schema_registry_url = os.getenv("ECHOSENSE_SCHEMA_REGISTRY_URL", "http://localhost:8081")
    topic = os.getenv("ECHOSENSE_EVENT_TOPIC", "echosense.events.v1")
    subject = f"{topic}-value"
    schema = (Path(__file__).parents[1] / "schemas" / "event-envelope.v1.json").read_text()
    response = httpx.post(
        f"{schema_registry_url}/subjects/{subject}/versions",
        json={"schemaType": "JSON", "schema": schema},
        timeout=10.0,
    )
    response.raise_for_status()

    storage = Storage(database_url)
    event_id = f"evt_{uuid4().hex}"
    storage.append_event(
        event_id=event_id,
        event_type="integration.checked",
        user_id="user_ci",
        trace_id=f"trc_{uuid4().hex}",
        payload={"source": "github-actions"},
    )

    publisher = OutboxPublisher(
        storage,
        RedpandaProducer(bootstrap_servers),
        ConfluentSchemaRegistry(schema_registry_url),
        topic=topic,
    )
    assert publisher.publish_batch(limit=10) >= 1

    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": f"echosense-ci-{uuid4().hex}",
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([topic])
    try:
        for _ in range(20):
            message = consumer.poll(1.0)
            if message is None or message.error():
                continue
            envelope = json.loads(message.value())
            if envelope["event_id"] == event_id:
                assert envelope["payload"]["source"] == "github-actions"
                headers = dict(message.headers() or [])
                assert int(headers["schema_id"]) > 0
                break
        else:
            pytest.fail("Published event was not observed in Redpanda")
    finally:
        consumer.close()
