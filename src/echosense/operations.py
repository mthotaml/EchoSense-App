from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import httpx
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

PUBLISHED = Counter("echosense_events_published_total", "Canonical events published")
RETRIES = Counter("echosense_event_retries_total", "Event publish retries")
VALIDATION_FAILURES = Counter(
    "echosense_event_validation_failures_total", "Schema validation failures"
)
DEAD_LETTERED = Counter(
    "echosense_events_dead_lettered_total", "Events sent to the DLQ", ["failure_type"]
)
REPLAYED = Counter("echosense_events_replayed_total", "DLQ events replayed", ["result"])
PUBLISH_LATENCY = Histogram("echosense_event_publish_seconds", "Event publication latency")
OUTBOX_DEPTH = Gauge("echosense_outbox_depth", "Unpublished outbox rows")
OUTBOX_OLDEST_AGE = Gauge(
    "echosense_outbox_oldest_event_age_seconds", "Age of oldest unpublished event"
)


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    checks: dict[str, str]


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def _database_probe(storage) -> None:
    with storage.connect() as connection:
        storage._execute(connection, "SELECT 1").fetchone()
        row = storage._execute(
            connection,
            "SELECT COUNT(*) AS depth, MIN(occurred_at) AS oldest FROM event_outbox WHERE published_at IS NULL",
        ).fetchone()
    values = dict(row)
    OUTBOX_DEPTH.set(int(values["depth"]))
    oldest = values["oldest"]
    age = 0.0
    if oldest:
        age = max(
            0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(oldest)).total_seconds()
        )
    OUTBOX_OLDEST_AGE.set(age)


def readiness(storage, memory=None, *, schema_registry_url: str | None = None) -> ReadinessResult:
    checks: dict[str, str] = {}
    try:
        _database_probe(storage)
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error:{type(exc).__name__}"

    if memory is not None:
        try:
            probe: Callable[[], None] | None = getattr(memory, "ping", None)
            if probe:
                probe()
            checks["memory"] = "ok"
        except Exception as exc:
            checks["memory"] = f"error:{type(exc).__name__}"

    registry_url = schema_registry_url or os.getenv("ECHOSENSE_SCHEMA_REGISTRY_URL")
    if registry_url:
        try:
            response = httpx.get(f"{registry_url.rstrip('/')}/subjects", timeout=2.0)
            response.raise_for_status()
            checks["schema_registry"] = "ok"
        except Exception as exc:
            checks["schema_registry"] = f"error:{type(exc).__name__}"

    return ReadinessResult(ready=all(value == "ok" for value in checks.values()), checks=checks)
