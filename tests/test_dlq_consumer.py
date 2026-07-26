import json

import pytest

from echosense.dlq_consumer import BoundedDLQConsumer


class FakeMessage:
    def __init__(self, topic: str, partition: int, offset: int, value: dict[str, object]) -> None:
        self._topic = topic
        self._partition = partition
        self._offset = offset
        self._value = json.dumps(value).encode()

    def error(self) -> None:
        return None

    def topic(self) -> str:
        return self._topic

    def partition(self) -> int:
        return self._partition

    def offset(self) -> int:
        return self._offset

    def value(self) -> bytes:
        return self._value


class FakeConsumer:
    def __init__(self, messages: list[FakeMessage]) -> None:
        self.messages = list(messages)
        self.assigned: list[tuple[str, int, int]] = []
        self.committed: list[tuple[str, int, int]] = []
        self.closed = False

    def assign(self, partitions: list[tuple[str, int, int]]) -> None:
        self.assigned = partitions

    def poll(self, timeout: float) -> FakeMessage | None:
        return self.messages.pop(0) if self.messages else None

    def commit(self, offsets: list[tuple[str, int, int]], asynchronous: bool = False) -> None:
        assert asynchronous is False
        self.committed = offsets

    def close(self) -> None:
        self.closed = True


def tp(topic: str, partition: int, offset: int) -> tuple[str, int, int]:
    return topic, partition, offset


def test_fetch_is_bounded_and_does_not_commit() -> None:
    consumer = FakeConsumer(
        [
            FakeMessage("dlq", 0, 5, {"event": {"event_id": "evt-1"}}),
            FakeMessage("dlq", 0, 6, {"event": {"event_id": "evt-2"}}),
            FakeMessage("dlq", 0, 7, {"event": {"event_id": "evt-3"}}),
        ]
    )
    source = BoundedDLQConsumer(consumer, tp)

    batch = source.fetch(topic="dlq", partition=0, offset=5, limit=2)

    assert consumer.assigned == [("dlq", 0, 5)]
    assert [record.offset for record in batch.records] == [5, 6]
    assert batch.next_offset == 7
    assert consumer.committed == []


def test_commit_advances_to_next_offset_only_when_explicit() -> None:
    consumer = FakeConsumer([FakeMessage("dlq", 2, 10, {"event": {"event_id": "evt-1"}})])
    source = BoundedDLQConsumer(consumer, tp)
    batch = source.fetch(topic="dlq", partition=2, offset=10, limit=1)

    source.commit(batch)

    assert consumer.committed == [("dlq", 2, 11)]


def test_bounds_and_partition_integrity_are_enforced() -> None:
    source = BoundedDLQConsumer(FakeConsumer([]), tp)
    with pytest.raises(ValueError):
        source.fetch(topic="dlq", partition=0, offset=0, limit=101)

    mismatched = BoundedDLQConsumer(
        FakeConsumer([FakeMessage("dlq", 1, 0, {"event": {"event_id": "evt"}})]), tp
    )
    with pytest.raises(RuntimeError):
        mismatched.fetch(topic="dlq", partition=0, offset=0, limit=1)
