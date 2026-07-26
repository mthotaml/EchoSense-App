from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol


class ConsumerLike(Protocol):
    def assign(self, partitions: list[Any]) -> None: ...
    def poll(self, timeout: float) -> Any: ...
    def commit(self, offsets: list[Any], asynchronous: bool = False) -> Any: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class DLQRecord:
    topic: str
    partition: int
    offset: int
    value: dict[str, Any]


@dataclass(frozen=True)
class DLQBatch:
    records: list[DLQRecord]
    topic: str
    partition: int
    start_offset: int
    next_offset: int


class BoundedDLQConsumer:
    """Explicit-offset DLQ reader that never subscribes or commits implicitly."""

    def __init__(self, consumer: ConsumerLike, topic_partition_factory: Any) -> None:
        self.consumer = consumer
        self.topic_partition_factory = topic_partition_factory

    def fetch(
        self,
        *,
        topic: str,
        partition: int,
        offset: int,
        limit: int,
        poll_timeout: float = 1.0,
    ) -> DLQBatch:
        if partition < 0 or offset < 0:
            raise ValueError("partition and offset must be non-negative")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        self.consumer.assign([self.topic_partition_factory(topic, partition, offset)])
        records: list[DLQRecord] = []
        next_offset = offset
        empty_polls = 0
        while len(records) < limit and empty_polls < 2:
            message = self.consumer.poll(poll_timeout)
            if message is None:
                empty_polls += 1
                continue
            if message.error():
                raise RuntimeError(str(message.error()))
            if message.topic() != topic or message.partition() != partition:
                raise RuntimeError("consumer returned a record outside the assigned partition")
            decoded = json.loads(message.value().decode())
            records.append(
                DLQRecord(
                    topic=topic,
                    partition=partition,
                    offset=message.offset(),
                    value=decoded,
                )
            )
            next_offset = message.offset() + 1
            empty_polls = 0
        return DLQBatch(records, topic, partition, offset, next_offset)

    def commit(self, batch: DLQBatch) -> None:
        if not batch.records:
            return
        offset = self.topic_partition_factory(batch.topic, batch.partition, batch.next_offset)
        self.consumer.commit(offsets=[offset], asynchronous=False)

    def close(self) -> None:
        self.consumer.close()


def confluent_consumer_from_environment() -> BoundedDLQConsumer:
    import os

    from confluent_kafka import Consumer, TopicPartition

    servers = os.getenv("ECHOSENSE_KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    group_id = os.getenv("ECHOSENSE_DLQ_ADMIN_GROUP_ID", "echosense-dlq-admin")
    consumer = Consumer(
        {
            "bootstrap.servers": servers,
            "group.id": group_id,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        }
    )
    return BoundedDLQConsumer(consumer, TopicPartition)
