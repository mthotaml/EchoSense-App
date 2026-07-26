from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from echosense.evaluation import AttributedOutcome, CounterfactualReport
from echosense.storage import Storage, utc_now


class EvaluationStore:
    """Durable evaluation records isolated from preference-memory writes."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.initialize()

    def initialize(self) -> None:
        statements = [
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
            "CREATE INDEX IF NOT EXISTS idx_attributed_outcomes_decision ON attributed_outcomes (decision_id)",
        ]
        with self.storage.connect() as connection:
            for statement in statements:
                self.storage._execute(connection, statement)

    def record_outcome(self, outcome: AttributedOutcome) -> bool:
        with self.storage.connect() as connection:
            cursor = self.storage._execute(
                connection,
                """
                INSERT INTO attributed_outcomes
                    (outcome_id, decision_id, outcome, reward, observed_at,
                     playback_seconds, completion_ratio, attribution_window_seconds, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(outcome_id) DO NOTHING
                """,
                (
                    outcome.outcome_id,
                    outcome.decision_id,
                    outcome.outcome,
                    outcome.reward,
                    outcome.observed_at.isoformat(),
                    outcome.playback_seconds,
                    outcome.completion_ratio,
                    outcome.attribution_window_seconds,
                    utc_now().isoformat(),
                ),
            )
            return cursor.rowcount > 0

    def save_report(self, report: CounterfactualReport) -> None:
        payload = self._jsonable(asdict(report))
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                INSERT INTO counterfactual_reports
                    (outcome_id, decision_id, report_json, evaluated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(outcome_id) DO UPDATE SET
                    decision_id = excluded.decision_id,
                    report_json = excluded.report_json,
                    evaluated_at = excluded.evaluated_at
                """,
                (
                    report.outcome_id,
                    report.decision_id,
                    json.dumps(payload, separators=(",", ":")),
                    report.evaluated_at.isoformat(),
                ),
            )

    def get_report(self, outcome_id: str) -> dict[str, Any] | None:
        with self.storage.connect() as connection:
            row = self.storage._execute(
                connection,
                "SELECT report_json FROM counterfactual_reports WHERE outcome_id = %s",
                (outcome_id,),
            ).fetchone()
        return None if row is None else json.loads(dict(row)["report_json"])

    @classmethod
    def _jsonable(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: cls._jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._jsonable(item) for item in value]
        return value
