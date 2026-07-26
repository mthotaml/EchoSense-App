from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from echosense.memory import PreferenceMemory
from echosense.storage import Storage, utc_now


@dataclass(frozen=True)
class DeletionResult:
    deletion_id: str
    status: str
    counts: dict[str, int]
    subject_hash: str


class DeletionCoordinator:
    """Coordinates resumable deletion across SQL storage and graph memory."""

    def __init__(self, storage: Storage, memory: PreferenceMemory) -> None:
        self.storage = storage
        self.memory = memory
        self._initialize()

    def _initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS deletion_requests (
                deletion_id TEXT PRIMARY KEY,
                user_id TEXT,
                subject_hash TEXT NOT NULL,
                purpose_id TEXT NOT NULL,
                status TEXT NOT NULL,
                counts_json TEXT,
                requested_at TEXT NOT NULL,
                completed_at TEXT,
                last_error TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS attributed_outcomes (
                outcome_id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reward REAL NOT NULL,
                observed_at TEXT NOT NULL,
                playback_seconds REAL,
                completion_ratio REAL,
                attribution_window_seconds INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS counterfactual_reports (
                outcome_id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                report_json TEXT NOT NULL,
                evaluated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS recommendation_exposures (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                item_id TEXT NOT NULL,
                exposure_count INTEGER NOT NULL DEFAULT 0,
                first_selected_at TEXT NOT NULL,
                last_selected_at TEXT NOT NULL,
                PRIMARY KEY (user_id, provider, item_id)
            )
            """,
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
        ]
        with self.storage.connect() as connection:
            for statement in statements:
                self.storage._execute(connection, statement)

    def _subject_hash(self, user_id: str) -> str:
        salt = os.getenv("ECHOSENSE_DELETION_HASH_SALT", "echosense-development-salt")
        return hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()

    def delete_user(self, user_id: str, purpose_id: str) -> DeletionResult:
        deletion_id = f"del_{uuid4().hex}"
        subject_hash = self._subject_hash(user_id)
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                INSERT INTO deletion_requests
                    (deletion_id, user_id, subject_hash, purpose_id, status, requested_at)
                VALUES (%s, %s, %s, %s, 'processing', %s)
                """,
                (deletion_id, user_id, subject_hash, purpose_id, utc_now().isoformat()),
            )
        return self._process(deletion_id, user_id, purpose_id, subject_hash)

    def retry_request(self, deletion_id: str) -> DeletionResult:
        with self.storage.connect() as connection:
            row = self.storage._execute(
                connection,
                """
                SELECT deletion_id, user_id, subject_hash, purpose_id, status, counts_json
                FROM deletion_requests WHERE deletion_id = %s
                """,
                (deletion_id,),
            ).fetchone()
            if row is None:
                raise LookupError("Deletion request not found")
            request = dict(row)
            if request["status"] == "completed":
                return DeletionResult(
                    deletion_id=request["deletion_id"],
                    status="completed",
                    counts=json.loads(request["counts_json"] or "{}"),
                    subject_hash=request["subject_hash"],
                )
            if request["user_id"] is None:
                raise RuntimeError(
                    "Incomplete deletion request no longer contains a resumable subject"
                )
            self.storage._execute(
                connection,
                """
                UPDATE deletion_requests SET status = 'processing', last_error = NULL
                WHERE deletion_id = %s
                """,
                (deletion_id,),
            )
        return self._process(
            deletion_id,
            request["user_id"],
            request["purpose_id"],
            request["subject_hash"],
        )

    def retry_pending(self, limit: int = 100) -> list[DeletionResult]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with self.storage.connect() as connection:
            rows = self.storage._execute(
                connection,
                """
                SELECT deletion_id FROM deletion_requests
                WHERE status = 'retry_required'
                ORDER BY requested_at LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [self.retry_request(dict(row)["deletion_id"]) for row in rows]

    def _process(
        self, deletion_id: str, user_id: str, purpose_id: str, subject_hash: str
    ) -> DeletionResult:
        try:
            graph_counts = self.memory.delete_user(user_id)
            counts = self._delete_sql_data(user_id)
            counts.update(graph_counts)
            completed_at = utc_now().isoformat()
            with self.storage.connect() as connection:
                self.storage._execute(
                    connection,
                    """
                    UPDATE deletion_requests
                    SET user_id = NULL, status = 'completed', counts_json = %s,
                        completed_at = %s, last_error = NULL
                    WHERE deletion_id = %s
                    """,
                    (json.dumps(counts), completed_at, deletion_id),
                )
            self.storage.append_event(
                event_id=f"evt_{uuid4().hex}",
                event_type="privacy.user_data.deleted",
                user_id=f"deleted:{subject_hash[:16]}",
                trace_id=f"trc_{uuid4().hex}",
                payload={
                    "deletion_id": deletion_id,
                    "purpose_id": purpose_id,
                    "subject_hash": subject_hash,
                    "counts": counts,
                },
            )
            return DeletionResult(deletion_id, "completed", counts, subject_hash)
        except Exception as exc:
            with self.storage.connect() as connection:
                self.storage._execute(
                    connection,
                    """
                    UPDATE deletion_requests SET status = 'retry_required', last_error = %s
                    WHERE deletion_id = %s
                    """,
                    (str(exc)[:1000], deletion_id),
                )
            raise

    def _delete_sql_data(self, user_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self.storage.connect() as connection:
            decision_rows = self.storage._execute(
                connection,
                "SELECT decision_id FROM decision_traces WHERE user_id = %s",
                (user_id,),
            ).fetchall()
            decision_ids = [dict(row)["decision_id"] for row in decision_rows]

            counts["attributed_outcomes"] = 0
            counts["counterfactual_reports"] = 0
            for decision_id in decision_ids:
                for name, table in (
                    ("counterfactual_reports", "counterfactual_reports"),
                    ("attributed_outcomes", "attributed_outcomes"),
                ):
                    row = self.storage._execute(
                        connection,
                        f"SELECT COUNT(*) AS count FROM {table} WHERE decision_id = %s",
                        (decision_id,),
                    ).fetchone()
                    counts[name] += int(dict(row)["count"])
                    self.storage._execute(
                        connection,
                        f"DELETE FROM {table} WHERE decision_id = %s",
                        (decision_id,),
                    )

            for name, table in (
                ("cognitive_memories", "cognitive_memories"),
                ("memory_lifecycle_runs", "memory_lifecycle_runs"),
                ("recommendation_exposures", "recommendation_exposures"),
                ("music_data_imports", "music_data_imports"),
                ("decision_traces", "decision_traces"),
                ("provider_tokens", "apple_music_user_tokens"),
                ("outbox_events", "event_outbox"),
                ("consent_grants", "consent_grants"),
            ):
                row = self.storage._execute(
                    connection,
                    f"SELECT COUNT(*) AS count FROM {table} WHERE user_id = %s",
                    (user_id,),
                ).fetchone()
                counts[name] = int(dict(row)["count"])
                self.storage._execute(
                    connection,
                    f"DELETE FROM {table} WHERE user_id = %s",
                    (user_id,),
                )
        return counts

    def get_request(self, deletion_id: str) -> dict[str, Any] | None:
        with self.storage.connect() as connection:
            row = self.storage._execute(
                connection,
                """
                SELECT deletion_id, subject_hash, purpose_id, status, counts_json,
                       requested_at, completed_at
                FROM deletion_requests WHERE deletion_id = %s
                """,
                (deletion_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["counts"] = json.loads(result.pop("counts_json")) if result["counts_json"] else {}
        return result
