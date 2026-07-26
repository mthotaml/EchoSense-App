from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from echosense.storage import Storage


@dataclass(frozen=True)
class PlaybackSnapshot:
    revision: int
    state: dict[str, object]
    observed_at: datetime


class PlaybackContinuityStore:
    """Durable last-known provider state used only when live state is unavailable."""

    def __init__(self, storage: Storage, *, max_age: timedelta = timedelta(minutes=15)) -> None:
        self.storage = storage
        self.max_age = max_age
        with storage.connect() as database:
            storage._execute(
                database,
                """
                CREATE TABLE IF NOT EXISTS playback_continuity (
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, provider)
                )
                """,
            )

    def observe(
        self,
        user_id: str,
        provider: str,
        state: dict[str, object],
        *,
        now: datetime | None = None,
    ) -> PlaybackSnapshot:
        observed_at = now or datetime.now(UTC)
        with self.storage.connect() as database:
            row = self.storage._execute(
                database,
                """
                SELECT revision FROM playback_continuity
                WHERE user_id = %s AND provider = %s
                """,
                (user_id, provider),
            ).fetchone()
            revision = int(dict(row)["revision"]) + 1 if row else 1
            self.storage._execute(
                database,
                """
                INSERT INTO playback_continuity
                    (user_id, provider, revision, state_json, observed_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(user_id, provider) DO UPDATE SET
                    revision = excluded.revision,
                    state_json = excluded.state_json,
                    observed_at = excluded.observed_at
                """,
                (
                    user_id,
                    provider,
                    revision,
                    json.dumps(state),
                    observed_at.isoformat(),
                ),
            )
        return PlaybackSnapshot(revision, state, observed_at)

    def latest(
        self, user_id: str, provider: str, *, now: datetime | None = None
    ) -> PlaybackSnapshot | None:
        with self.storage.connect() as database:
            row = self.storage._execute(
                database,
                """
                SELECT revision, state_json, observed_at FROM playback_continuity
                WHERE user_id = %s AND provider = %s
                """,
                (user_id, provider),
            ).fetchone()
        if row is None:
            return None
        values = dict(row)
        observed_at = datetime.fromisoformat(values["observed_at"])
        if (now or datetime.now(UTC)) - observed_at > self.max_age:
            return None
        return PlaybackSnapshot(
            int(values["revision"]),
            json.loads(values["state_json"]),
            observed_at,
        )
