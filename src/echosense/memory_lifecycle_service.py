from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from echosense.cognitive_memory import CognitiveMemoryStore, MemoryRecord
from echosense.memory_lifecycle import LifecyclePlan, MemoryLifecyclePlanner
from echosense.storage import Storage


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class LifecycleResult:
    run_id: str
    user_id: str
    mode: str
    status: str
    consolidated_memory_ids: tuple[str, ...]
    forgotten_memory_ids: tuple[str, ...]
    plan: LifecyclePlan
    created_at: datetime


class MemoryLifecycleService:
    """Plans and applies memory consolidation and forgetting with durable idempotency."""

    def __init__(
        self,
        storage: Storage,
        memory_store: CognitiveMemoryStore | None = None,
        planner: MemoryLifecyclePlanner | None = None,
    ) -> None:
        self.storage = storage
        self.memory_store = memory_store or CognitiveMemoryStore(storage)
        self.planner = planner or MemoryLifecyclePlanner()
        self.initialize()

    def initialize(self) -> None:
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS memory_lifecycle_runs (
                    run_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    consolidated_json TEXT NOT NULL,
                    forgotten_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """,
            )

    def execute(
        self,
        *,
        run_id: str,
        user_id: str,
        mode: str = "dry_run",
        now: datetime | None = None,
        protected_memory_ids: tuple[str, ...] = (),
    ) -> LifecycleResult:
        if mode not in {"dry_run", "apply"}:
            raise ValueError("mode must be dry_run or apply")
        existing = self.get(run_id)
        if existing is not None:
            if existing.user_id != user_id or existing.mode != mode:
                raise ValueError("run_id already exists with different parameters")
            return existing

        instant = now or utc_now()
        memories = self._active_user_history(user_id)
        plan = self.planner.plan(
            memories,
            now=instant,
            protected_memory_ids=protected_memory_ids,
        )
        consolidated: list[str] = []
        forgotten: list[str] = []

        if mode == "apply":
            for candidate in plan.consolidations:
                memory_id = f"mem_{candidate.consolidation_key}"
                self.memory_store.remember(
                    memory_id=memory_id,
                    user_id=user_id,
                    memory_type="semantic",
                    subject=candidate.subject,
                    predicate=candidate.predicate,
                    object=candidate.object,
                    context=candidate.context,
                    confidence=candidate.confidence,
                    provenance_type="consolidation",
                    provenance_ref=json.dumps(
                        list(candidate.source_memory_ids), separators=(",", ":")
                    ),
                    observed_at=instant,
                )
                consolidated.append(memory_id)
            if plan.forgetting:
                ids = tuple(item.memory_id for item in plan.forgetting)
                placeholders = ", ".join(["%s"] * len(ids))
                with self.storage.connect() as connection:
                    self.storage._execute(
                        connection,
                        f"DELETE FROM cognitive_memories "
                        f"WHERE user_id = %s AND memory_id IN ({placeholders})",
                        (user_id, *ids),
                    )
                forgotten.extend(ids)

        result = LifecycleResult(
            run_id=run_id,
            user_id=user_id,
            mode=mode,
            status="completed",
            consolidated_memory_ids=tuple(consolidated),
            forgotten_memory_ids=tuple(forgotten),
            plan=plan,
            created_at=instant,
        )
        self._save(result)
        self.storage.append_event(
            event_id=f"evt_{run_id}",
            event_type="memory.lifecycle.completed",
            user_id=user_id,
            trace_id=f"trc_{run_id}",
            payload={
                "run_id": run_id,
                "mode": mode,
                "consolidated_count": len(consolidated),
                "forgotten_count": len(forgotten),
            },
        )
        return result

    def get(self, run_id: str) -> LifecycleResult | None:
        with self.storage.connect() as connection:
            row = self.storage._execute(
                connection,
                "SELECT * FROM memory_lifecycle_runs WHERE run_id = %s",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        plan_payload = json.loads(payload["plan_json"])
        from echosense.memory_lifecycle import ConsolidationCandidate, ForgettingCandidate

        consolidations = []
        for item in plan_payload["consolidations"]:
            normalized = dict(item)
            normalized["source_memory_ids"] = tuple(normalized["source_memory_ids"])
            consolidations.append(ConsolidationCandidate(**normalized))
        plan = LifecyclePlan(
            consolidations=tuple(consolidations),
            forgetting=tuple(ForgettingCandidate(**item) for item in plan_payload["forgetting"]),
            protected_memory_ids=tuple(plan_payload["protected_memory_ids"]),
        )
        return LifecycleResult(
            run_id=payload["run_id"],
            user_id=payload["user_id"],
            mode=payload["mode"],
            status=payload["status"],
            consolidated_memory_ids=tuple(json.loads(payload["consolidated_json"])),
            forgotten_memory_ids=tuple(json.loads(payload["forgotten_json"])),
            plan=plan,
            created_at=datetime.fromisoformat(payload["created_at"]),
        )

    def delete_user(self, user_id: str) -> int:
        with self.storage.connect() as connection:
            cursor = self.storage._execute(
                connection,
                "DELETE FROM memory_lifecycle_runs WHERE user_id = %s",
                (user_id,),
            )
            return cursor.rowcount

    def _active_user_history(self, user_id: str) -> list[MemoryRecord]:
        with self.storage.connect() as connection:
            rows = self.storage._execute(
                connection,
                "SELECT * FROM cognitive_memories WHERE user_id = %s ORDER BY memory_id",
                (user_id,),
            ).fetchall()
        return [self.memory_store._from_row(dict(row)) for row in rows]

    def _save(self, result: LifecycleResult) -> None:
        plan_json = json.dumps(
            {
                "consolidations": [asdict(item) for item in result.plan.consolidations],
                "forgetting": [asdict(item) for item in result.plan.forgetting],
                "protected_memory_ids": list(result.plan.protected_memory_ids),
            },
            sort_keys=True,
        )
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                INSERT INTO memory_lifecycle_runs
                    (run_id, user_id, mode, status, plan_json, consolidated_json,
                     forgotten_json, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    result.run_id,
                    result.user_id,
                    result.mode,
                    result.status,
                    plan_json,
                    json.dumps(list(result.consolidated_memory_ids)),
                    json.dumps(list(result.forgotten_memory_ids)),
                    result.created_at.isoformat(),
                ),
            )
