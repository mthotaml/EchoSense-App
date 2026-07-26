from __future__ import annotations

import hmac
import os
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator

from echosense.dlq_consumer import BoundedDLQConsumer
from echosense.dlq_replay import ReplayFilter, ReplayService
from echosense.memory import memory_from_environment
from echosense.operations import metrics_payload, readiness
from echosense.replay_audit import ReplayAuditStore
from echosense.storage import Storage

app = FastAPI(title="EchoSense Operations", version="0.17.0")
replay_service: ReplayService | None = None
replay_audit_store: ReplayAuditStore | None = None
dlq_consumer: BoundedDLQConsumer | None = None
storage: Storage | None = None


class ReplayRequest(BaseModel):
    records: list[dict[str, Any]] | None = Field(default=None, min_length=1, max_length=100)
    topic: str | None = None
    partition: int | None = Field(default=None, ge=0)
    offset: int | None = Field(default=None, ge=0)
    limit: int = Field(default=100, ge=1, le=100)
    commit_offsets: bool = False
    dry_run: bool = True
    event_id: str | None = None
    failure_type: str | None = None
    occurred_after: datetime | None = None
    occurred_before: datetime | None = None

    @model_validator(mode="after")
    def validate_source(self) -> "ReplayRequest":
        broker_fields = (self.topic, self.partition, self.offset)
        has_broker_source = all(value is not None for value in broker_fields)
        if self.records is None and not has_broker_source:
            raise ValueError("provide records or topic, partition, and offset")
        if self.records is not None and any(value is not None for value in broker_fields):
            raise ValueError("records and broker coordinates are mutually exclusive")
        if self.commit_offsets and self.dry_run:
            raise ValueError("dry runs cannot commit offsets")
        return self


def get_storage() -> Storage:
    global storage
    if storage is None:
        storage = Storage()
    return storage


def get_replay_audit_store() -> ReplayAuditStore:
    global replay_audit_store
    if replay_audit_store is None:
        replay_audit_store = ReplayAuditStore(get_storage())
    return replay_audit_store


def require_admin_key(provided: str | None) -> str:
    expected = os.getenv("ECHOSENSE_ADMIN_API_KEY")
    if not expected:
        raise HTTPException(status_code=404, detail="Replay administration is disabled")
    if provided is None or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid administration credentials")
    return "admin-key"


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready")
def readiness_check(response: Response) -> dict[str, object]:
    result = readiness(get_storage(), memory_from_environment())
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if result.ready else "not_ready", "checks": result.checks}


@app.get("/metrics")
def metrics() -> Response:
    payload, content_type = metrics_payload()
    return Response(content=payload, media_type=content_type)


@app.post("/admin/replays")
def create_replay(
    request: ReplayRequest,
    x_echosense_admin_key: str | None = Header(default=None),
) -> dict[str, int | str]:
    actor = require_admin_key(x_echosense_admin_key)
    if replay_service is None:
        raise HTTPException(status_code=503, detail="Replay service is not configured")
    batch = None
    records = request.records
    if records is None:
        if dlq_consumer is None:
            raise HTTPException(status_code=503, detail="DLQ consumer is not configured")
        batch = dlq_consumer.fetch(
            topic=request.topic or "",
            partition=request.partition or 0,
            offset=request.offset or 0,
            limit=request.limit,
        )
        records = [record.value for record in batch.records]
    selection = ReplayFilter(
        event_id=request.event_id,
        failure_type=request.failure_type,
        occurred_after=request.occurred_after,
        occurred_before=request.occurred_before,
    )
    try:
        summary = replay_service.replay(
            records,
            selection=selection,
            dry_run=request.dry_run,
            actor=actor,
        )
        if batch is not None and request.commit_offsets:
            if int(summary["rejected"]) > 0:
                raise HTTPException(status_code=409, detail="Offsets not committed because records were rejected")
            dlq_consumer.commit(batch)
        return summary
    except HTTPException:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "replay_rejected", "message": str(exc)},
        ) from exc


@app.get("/admin/replays/{replay_id}")
def get_replay(
    replay_id: str,
    x_echosense_admin_key: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin_key(x_echosense_admin_key)
    result = get_replay_audit_store().get(replay_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Replay audit not found")
    return result
