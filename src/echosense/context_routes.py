from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from echosense.context_fusion import ContextFusionService

router = APIRouter(prefix="/v1/context", tags=["context"])


class ContextRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    local_hour: int = Field(ge=0, le=23)
    speed_mps: float | None = Field(default=None, ge=0)
    baseline_speed_mps: float | None = Field(default=None, ge=0)


@router.post("/resolve")
def resolve_context(request: ContextRequest) -> dict[str, object]:
    return (
        ContextFusionService()
        .resolve(
            latitude=request.latitude,
            longitude=request.longitude,
            local_hour=request.local_hour,
            speed_mps=request.speed_mps,
            baseline_speed_mps=request.baseline_speed_mps,
        )
        .as_dict()
    )
