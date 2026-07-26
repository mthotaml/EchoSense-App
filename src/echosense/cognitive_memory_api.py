from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from echosense.cognitive_memory import CognitiveMemoryStore, MemoryRecord
from echosense.storage import Storage

app = FastAPI(title="EchoSense Cognitive Memory", version="0.19.0")
storage: Storage | None = None
memory_store: CognitiveMemoryStore | None = None
MEMORY_PURPOSE = "cognitive_memory"


def get_storage() -> Storage:
    global storage
    if storage is None:
        storage = Storage()
    return storage


def get_memory_store() -> CognitiveMemoryStore:
    global memory_store
    if memory_store is None:
        memory_store = CognitiveMemoryStore(get_storage())
    return memory_store


def require_memory_consent(user_id: str) -> None:
    if not get_storage().has_active_consent(user_id, MEMORY_PURPOSE):
        raise HTTPException(
            status_code=403,
            detail={"code": "consent_required", "missing_purposes": [MEMORY_PURPOSE]},
        )


class MemoryWriteRequest(BaseModel):
    memory_id: str = Field(min_length=1)
    memory_type: Literal["episodic", "semantic", "working"]
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    context: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    provenance_type: str = Field(min_length=1)
    provenance_ref: str = Field(min_length=1)
    observed_at: datetime | None = None
    expires_at: datetime | None = None


class MemoryResponse(BaseModel):
    memory_id: str
    user_id: str
    memory_type: str
    subject: str
    predicate: str
    object: str
    context: str
    confidence: float
    provenance_type: str
    provenance_ref: str
    observed_at: datetime
    created_at: datetime
    expires_at: datetime | None
    supersedes_memory_id: str | None
    status: str


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1)
    memory_type: Literal["episodic", "semantic", "working"] | None = None
    context: str | None = None
    limit: int = Field(default=10, ge=1, le=100)


class RetrievedMemoryResponse(BaseModel):
    memory: MemoryResponse
    relevance_score: float


def memory_response(memory: MemoryRecord) -> MemoryResponse:
    return MemoryResponse.model_validate(memory, from_attributes=True)


@app.put(
    "/v1/users/{user_id}/memories/{memory_id}",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def remember(user_id: str, memory_id: str, request: MemoryWriteRequest) -> MemoryResponse:
    require_memory_consent(user_id)
    if request.memory_id != memory_id:
        raise HTTPException(status_code=422, detail="Path and body memory IDs must match")
    try:
        memory = get_memory_store().remember(user_id=user_id, **request.model_dump())
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "memory_rejected", "message": str(exc)},
        ) from exc
    get_storage().append_event(
        event_id=f"evt_{uuid4().hex}",
        event_type="memory.recorded",
        user_id=user_id,
        trace_id=f"trc_{uuid4().hex}",
        payload={
            "memory_id": memory.memory_id,
            "memory_type": memory.memory_type,
            "subject": memory.subject,
            "predicate": memory.predicate,
            "context": memory.context,
            "confidence": memory.confidence,
            "supersedes_memory_id": memory.supersedes_memory_id,
        },
    )
    return memory_response(memory)


@app.get("/v1/users/{user_id}/memories/{memory_id}", response_model=MemoryResponse)
def get_memory(user_id: str, memory_id: str) -> MemoryResponse:
    require_memory_consent(user_id)
    memory = get_memory_store().get(memory_id)
    if memory is None or memory.user_id != user_id:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory_response(memory)


@app.post(
    "/v1/users/{user_id}/memories:search",
    response_model=list[RetrievedMemoryResponse],
)
def search_memories(user_id: str, request: MemorySearchRequest) -> list[RetrievedMemoryResponse]:
    require_memory_consent(user_id)
    results = get_memory_store().retrieve(
        user_id=user_id,
        query=request.query,
        memory_type=request.memory_type,
        context=request.context,
        limit=request.limit,
    )
    return [
        RetrievedMemoryResponse(
            memory=memory_response(item.memory),
            relevance_score=item.relevance_score,
        )
        for item in results
    ]
