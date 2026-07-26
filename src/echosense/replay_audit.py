from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from echosense.storage import Storage, utc_now


@dataclass(frozen=True)
class ReplayAudit:
    replay_id: str
    actor: str
    dry_run: bool
    status: str
    selected: int
    replayed: int
    rejected: int
    created_at: datetime
    completed_at: datetime | None


class ReplayAuditStore:
    """Durable operator audit history for bounded DLQ replay attempts."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.initialize()

    def initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS replay_audits (
                replay_id TEXT PRIMARY KEY,
                actor TEXT NOT NULL,
                dry_run INTEGER NOT NULL,
                status TEXT NOT NULL,
                filter_json TEXT NOT NULL,
                selected INTEGER NOT NULL DEFAULT 0,
                replayed INTEGER NOT NULL DEFAULT 0,
                rejected INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS replay_audit_events (
                replay_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                result TEXT NOT NULL,
                error TEXT,
                recorded_at TEXT NOT NULL,
                PRIMARY KEY (replay_id, event_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_replay_audits_created ON replay_audits (created_at)",
        ]
        with self.storage.connect() as connection:
            for statement in statements:
                self.storage._execute(connection, statement)

    def start(self, *, actor: str, dry_run: bool, selection: dict[str, Any]) -> str:
        replay_id = f"rpl_{uuid4().hex}"
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                INSERT INTO replay_audits
                    (replay_id, actor, dry_run, status, filter_json, created_at)
                VALUES (%s, %s, %s, 'processing', %s, %s)
                """,
                (replay_id, actor, int(dry_run), json.dumps(selection), utc_now().isoformat()),
            )
        return replay_id

    def record_event(self, replay_id: str, event_id: str, result: str, error: str | None = None) -> None:
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                INSERT INTO replay_audit_events
                    (replay_id, event_id, result, error, recorded_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(replay_id, event_id) DO UPDATE SET
                    result = excluded.result,
                    error = excluded.error,
                    recorded_at = excluded.recorded_at
                """,
                (replay_id, event_id, result, error[:1000] if error else None, utc_now().isoformat()),
            )

    def complete(self, replay_id: str, summary: dict[str, int], *, status: str = "completed") -> None:
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                UPDATE replay_audits
                SET status = %s, selected = %s, replayed = %s, rejected = %s, completed_at = %s
                WHERE replay_id = %s
                """,
                (
                    status,
                    summary["selected"],
                    summary["replayed"],
                    summary["rejected"],
                    utc_now().isoformat(),
                    replay_id,
                ),
            )

    def get(self, replay_id: str) -> dict[str, Any] | None:
        with self.storage.connect() as connection:
            row = self.storage._execute(
                connection, "SELECT * FROM replay_audits WHERE replay_id = %s", (replay_id,)
            ).fetchone()
            events = self.storage._execute(
                connection,
                "SELECT event_id, result, error, recorded_at FROM replay_audit_events WHERE replay_id = %s ORDER BY recorded_at",
                (replay_id,),
            ).fetchall()
        if row is None:
            return None
        result = dict(row)
        result["dry_run"] = bool(result["dry_run"])
        result["selection"] = json.loads(result.pop("filter_json"))
        result["events"] = [dict(event) for event in events]
        return result
