from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from echosense.storage import Storage

MemoryType = Literal["episodic", "semantic", "working"]
MemoryStatus = Literal["active", "superseded", "expired"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    user_id: str
    memory_type: MemoryType
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
    status: MemoryStatus


@dataclass(frozen=True)
class RetrievedMemory:
    memory: MemoryRecord
    relevance_score: float


class CognitiveMemoryStore:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.initialize()

    def initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS cognitive_memories (
                memory_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object_value TEXT NOT NULL,
                context TEXT NOT NULL,
                confidence REAL NOT NULL,
                provenance_type TEXT NOT NULL,
                provenance_ref TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                supersedes_memory_id TEXT,
                status TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_cognitive_memory_owner ON cognitive_memories (user_id, status, memory_type)",
            "CREATE INDEX IF NOT EXISTS idx_cognitive_memory_semantic ON cognitive_memories (user_id, subject, predicate, context, status)",
        ]
        with self.storage.connect() as connection:
            for statement in statements:
                self.storage._execute(connection, statement)

    def remember(
        self,
        *,
        memory_id: str,
        user_id: str,
        memory_type: MemoryType,
        subject: str,
        predicate: str,
        object: str,
        context: str,
        confidence: float,
        provenance_type: str,
        provenance_ref: str,
        observed_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> MemoryRecord:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if memory_type == "working" and expires_at is None:
            raise ValueError("working memory requires expires_at")
        now = utc_now()
        observed = observed_at or now
        if expires_at is not None and expires_at <= now:
            raise ValueError("expires_at must be in the future")

        existing = self.get(memory_id)
        if existing is not None:
            expected = (user_id, memory_type, subject, predicate, object, context)
            actual = (
                existing.user_id,
                existing.memory_type,
                existing.subject,
                existing.predicate,
                existing.object,
                existing.context,
            )
            if expected != actual:
                raise ValueError("memory_id already exists with different content")
            return existing

        supersedes: str | None = None
        with self.storage.connect() as connection:
            if memory_type == "semantic":
                row = self.storage._execute(
                    connection,
                    """
                    SELECT memory_id, object_value FROM cognitive_memories
                    WHERE user_id = %s AND subject = %s AND predicate = %s
                      AND context = %s AND memory_type = 'semantic' AND status = 'active'
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (user_id, subject, predicate, context),
                ).fetchone()
                if row is not None:
                    active = dict(row)
                    if active["object_value"] == object:
                        return self.get(active["memory_id"])  # type: ignore[return-value]
                    supersedes = active["memory_id"]
                    self.storage._execute(
                        connection,
                        "UPDATE cognitive_memories SET status = 'superseded' WHERE memory_id = %s",
                        (supersedes,),
                    )
            self.storage._execute(
                connection,
                """
                INSERT INTO cognitive_memories
                    (memory_id, user_id, memory_type, subject, predicate, object_value,
                     context, confidence, provenance_type, provenance_ref, observed_at,
                     created_at, expires_at, supersedes_memory_id, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
                """,
                (
                    memory_id,
                    user_id,
                    memory_type,
                    subject,
                    predicate,
                    object,
                    context,
                    confidence,
                    provenance_type,
                    provenance_ref,
                    observed.isoformat(),
                    now.isoformat(),
                    expires_at.isoformat() if expires_at else None,
                    supersedes,
                ),
            )
        return self.get(memory_id)  # type: ignore[return-value]

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self.storage.connect() as connection:
            row = self.storage._execute(
                connection, "SELECT * FROM cognitive_memories WHERE memory_id = %s", (memory_id,)
            ).fetchone()
        return None if row is None else self._from_row(dict(row))

    def retrieve(
        self,
        *,
        user_id: str,
        query: str,
        memory_type: MemoryType | None = None,
        context: str | None = None,
        limit: int = 10,
        now: datetime | None = None,
    ) -> list[RetrievedMemory]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        instant = now or utc_now()
        clauses = ["user_id = %s", "status = 'active'"]
        params: list[Any] = [user_id]
        if memory_type:
            clauses.append("memory_type = %s")
            params.append(memory_type)
        if context:
            clauses.append("context = %s")
            params.append(context)
        with self.storage.connect() as connection:
            rows = self.storage._execute(
                connection,
                f"SELECT * FROM cognitive_memories WHERE {' AND '.join(clauses)}",
                tuple(params),
            ).fetchall()

        query_tokens = _tokens(query)
        ranked: list[RetrievedMemory] = []
        for row in rows:
            memory = self._from_row(dict(row))
            if memory.expires_at and memory.expires_at <= instant:
                continue
            memory_tokens = _tokens(
                " ".join((memory.subject, memory.predicate, memory.object, memory.context))
            )
            overlap = len(query_tokens & memory_tokens) / max(1, len(query_tokens))
            age_days = max(0.0, (instant - memory.observed_at).total_seconds() / 86400.0)
            recency = math.pow(0.5, age_days / 30.0)
            score = round(0.6 * overlap + 0.25 * memory.confidence + 0.15 * recency, 6)
            ranked.append(RetrievedMemory(memory=memory, relevance_score=score))
        ranked.sort(
            key=lambda item: (
                item.relevance_score,
                item.memory.confidence,
                item.memory.observed_at,
                item.memory.memory_id,
            ),
            reverse=True,
        )
        return ranked[:limit]

    def expire_working_memories(self, now: datetime | None = None) -> int:
        instant = now or utc_now()
        with self.storage.connect() as connection:
            cursor = self.storage._execute(
                connection,
                """
                UPDATE cognitive_memories SET status = 'expired'
                WHERE memory_type = 'working' AND status = 'active'
                  AND expires_at IS NOT NULL AND expires_at <= %s
                """,
                (instant.isoformat(),),
            )
            return cursor.rowcount

    def delete_user(self, user_id: str) -> int:
        with self.storage.connect() as connection:
            cursor = self.storage._execute(
                connection, "DELETE FROM cognitive_memories WHERE user_id = %s", (user_id,)
            )
            return cursor.rowcount

    @staticmethod
    def _from_row(row: dict[str, Any]) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["memory_id"],
            user_id=row["user_id"],
            memory_type=row["memory_type"],
            subject=row["subject"],
            predicate=row["predicate"],
            object=row["object_value"],
            context=row["context"],
            confidence=float(row["confidence"]),
            provenance_type=row["provenance_type"],
            provenance_ref=row["provenance_ref"],
            observed_at=datetime.fromisoformat(row["observed_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            supersedes_memory_id=row["supersedes_memory_id"],
            status=row["status"],
        )
