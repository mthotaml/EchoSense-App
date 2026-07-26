from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from echosense.memory_lifecycle_service import LifecycleResult, MemoryLifecycleService
from echosense.storage import Storage

app = FastAPI(title="EchoSense Cognitive Memory Lifecycle", version="0.22.0")
storage: Storage | None = None
lifecycle_service: MemoryLifecycleService | None = None
MEMORY_PURPOSE = "cognitive_memory"


def get_storage() -> Storage:
    global storage
    if storage is None:
        storage = Storage()
    return storage


def get_lifecycle_service() -> MemoryLifecycleService:
    global lifecycle_service
    if lifecycle_service is None:
        lifecycle_service = MemoryLifecycleService(get_storage())
    return lifecycle_service


def require_memory_consent(user_id: str) -> None:
    if not get_storage().has_active_consent(user_id, MEMORY_PURPOSE):
        raise HTTPException(
            status_code=403,
            detail={"code": "consent_required", "missing_purposes": [MEMORY_PURPOSE]},
        )


class LifecycleExecuteRequest(BaseModel):
    run_id: str = Field(min_length=1)
    mode: Literal["dry_run", "apply"] = "dry_run"
    protected_memory_ids: tuple[str, ...] = ()
    now: datetime | None = None


class LifecycleResponse(BaseModel):
    run_id: str
    user_id: str
    mode: str
    status: str
    consolidated_memory_ids: tuple[str, ...]
    forgotten_memory_ids: tuple[str, ...]
    plan: dict[str, object]
    created_at: datetime


def lifecycle_response(result: LifecycleResult) -> LifecycleResponse:
    return LifecycleResponse(
        run_id=result.run_id,
        user_id=result.user_id,
        mode=result.mode,
        status=result.status,
        consolidated_memory_ids=result.consolidated_memory_ids,
        forgotten_memory_ids=result.forgotten_memory_ids,
        plan=asdict(result.plan),
        created_at=result.created_at,
    )


@app.post(
    "/v1/users/{user_id}/memory-lifecycle-runs",
    response_model=LifecycleResponse,
)
def execute_lifecycle(
    user_id: str,
    request: LifecycleExecuteRequest,
) -> LifecycleResponse:
    require_memory_consent(user_id)
    protected = tuple(sorted(set(request.protected_memory_ids)))
    try:
        result = get_lifecycle_service().execute(
            run_id=request.run_id,
            user_id=user_id,
            mode=request.mode,
            now=request.now,
            protected_memory_ids=protected,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "lifecycle_run_conflict", "message": str(exc)},
        ) from exc
    return lifecycle_response(result)


@app.get(
    "/v1/users/{user_id}/memory-lifecycle-runs/{run_id}",
    response_model=LifecycleResponse,
)
def get_lifecycle_run(user_id: str, run_id: str) -> LifecycleResponse:
    require_memory_consent(user_id)
    result = get_lifecycle_service().get(run_id)
    if result is None or result.user_id != user_id:
        raise HTTPException(status_code=404, detail="Lifecycle run not found")
    return lifecycle_response(result)
