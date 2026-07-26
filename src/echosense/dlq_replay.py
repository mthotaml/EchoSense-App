from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable, Protocol

from echosense.event_schema import SchemaRegistry
from echosense.operations import REPLAYED
from echosense.outbox_publisher import Producer
from echosense.replay_audit import ReplayAuditStore


class DeadLetterSource(Protocol):
    def records(self, limit: int = 100) -> Iterable[dict[str, Any]]: ...


@dataclass(frozen=True)
class ReplayFilter:
    event_id: str | None = None
    failure_type: str | None = None
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None

    def matches(self, record: dict[str, Any]) -> bool:
        event = record["event"]
        if self.event_id and event["event_id"] != self.event_id:
            return False
        if self.failure_type and record.get("failure_type") != self.failure_type:
            return False
        occurred = datetime.fromisoformat(event["occurred_at"])
        if self.occurred_after and occurred < self.occurred_after:
            return False
        if self.occurred_before and occurred >= self.occurred_before:
            return False
        return True

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("occurred_after", "occurred_before"):
            if payload[key] is not None:
                payload[key] = payload[key].isoformat()
        return payload


class ReplayService:
    def __init__(
        self,
        producer: Producer,
        registry: SchemaRegistry,
        topic: str = "echosense.events.v1",
        audit_store: ReplayAuditStore | None = None,
    ) -> None:
        self.producer = producer
        self.registry = registry
        self.topic = topic
        self.subject = f"{topic}-value"
        self.audit_store = audit_store

    def replay(
        self,
        records: Iterable[dict[str, Any]],
        *,
        selection: ReplayFilter | None = None,
        dry_run: bool = False,
        actor: str = "system",
    ) -> dict[str, int | str]:
        chosen_filter = selection or ReplayFilter()
        replay_id = (
            self.audit_store.start(actor=actor, dry_run=dry_run, selection=chosen_filter.as_dict())
            if self.audit_store
            else None
        )
        selected = replayed = rejected = 0
        try:
            for record in records:
                event = record.get("event", {})
                event_id = str(event.get("event_id", "unknown"))
                if int(record.get("replay_count", 0)) > 0:
                    rejected += 1
                    REPLAYED.labels(result="loop_rejected").inc()
                    if replay_id:
                        self.audit_store.record_event(
                            replay_id, event_id, "loop_rejected", "record was previously replayed"
                        )
                    continue
                if not chosen_filter.matches(record):
                    continue
                selected += 1
                try:
                    schema_id = self.registry.validate(self.subject, event)
                    if not dry_run:
                        self.producer.produce(
                            topic=self.topic,
                            key=event["event_id"],
                            value=json.dumps(event, separators=(",", ":")).encode(),
                            headers=[
                                ("event_type", event["event_type"].encode()),
                                ("schema_version", event["schema_version"].encode()),
                                ("schema_id", str(schema_id).encode()),
                                ("schema_subject", self.subject.encode()),
                                ("replayed", b"true"),
                                ("replay_id", replay_id.encode() if replay_id else b"untracked"),
                            ],
                        )
                        if self.producer.flush(10.0) != 0:
                            raise RuntimeError("producer flush timed out")
                    replayed += 1
                    result = "dry_run" if dry_run else "published"
                    REPLAYED.labels(result=result).inc()
                    if replay_id:
                        self.audit_store.record_event(replay_id, event_id, result)
                except Exception as exc:
                    rejected += 1
                    REPLAYED.labels(result="rejected").inc()
                    if replay_id:
                        self.audit_store.record_event(replay_id, event_id, "rejected", str(exc))
            summary: dict[str, int | str] = {
                "selected": selected,
                "replayed": replayed,
                "rejected": rejected,
            }
            if replay_id:
                self.audit_store.complete(
                    replay_id,
                    {"selected": selected, "replayed": replayed, "rejected": rejected},
                )
                summary["replay_id"] = replay_id
            return summary
        except Exception:
            if replay_id:
                self.audit_store.complete(
                    replay_id,
                    {"selected": selected, "replayed": replayed, "rejected": rejected},
                    status="failed",
                )
            raise


def main() -> None:
    raise SystemExit(
        "DLQ replay is a controlled operation. Instantiate ReplayService with a bounded source "
        "or use the administration API when enabled."
    )


if __name__ == "__main__":
    main()
