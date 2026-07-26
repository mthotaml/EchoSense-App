from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol


def utc_now() -> datetime:
    return datetime.now(UTC)


class CursorLike(Protocol):
    rowcount: int

    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Any]: ...


class Storage:
    """Persistence adapter supporting SQLite tests and PostgreSQL runtime."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv(
            "ECHOSENSE_DATABASE_URL",
            "postgresql://echosense:echosense@localhost:5432/echosense",
        )
        self.is_sqlite = self.database_url.startswith("sqlite:///")
        self.is_postgres = self.database_url.startswith(("postgresql://", "postgres://"))
        if not (self.is_sqlite or self.is_postgres):
            raise ValueError("ECHOSENSE_DATABASE_URL must use sqlite:/// or postgresql://")
        if self.is_sqlite:
            self.path = Path(self.database_url.removeprefix("sqlite:///"))
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[Any]:
        if self.is_sqlite:
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
        else:
            from psycopg import connect
            from psycopg.rows import dict_row

            connection = connect(self.database_url, row_factory=dict_row)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _execute(self, connection: Any, sql: str, params: tuple[Any, ...] = ()) -> CursorLike:
        if self.is_sqlite:
            sql = sql.replace("%s", "?")
        return connection.execute(sql, params)

    def initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS consent_grants (
                user_id TEXT NOT NULL,
                purpose_id TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                status TEXT NOT NULL,
                granted_at TEXT NOT NULL,
                revoked_at TEXT,
                PRIMARY KEY (user_id, purpose_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS event_outbox (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                user_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                published_at TEXT,
                claimed_by TEXT,
                claim_until TEXT,
                publish_attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS decision_traces (
                decision_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                context TEXT NOT NULL,
                context_confidence REAL NOT NULL,
                provider TEXT NOT NULL,
                item_id TEXT NOT NULL,
                factors_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS apple_music_user_tokens (
                user_id TEXT PRIMARY KEY,
                encrypted_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revoked_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS provider_connections (
                session_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                provider_user_id TEXT NOT NULL,
                encrypted_access_token TEXT NOT NULL,
                encrypted_refresh_token TEXT,
                expires_at TEXT NOT NULL,
                profile_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revoked_at TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS music_data_imports (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                normalized_json TEXT NOT NULL,
                PRIMARY KEY (user_id, provider)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS music_dna_profiles (
                user_id TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL,
                profile_json TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS music_item_preferences (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                item_id TEXT NOT NULL,
                context TEXT NOT NULL,
                weight REAL NOT NULL,
                evidence_count INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, provider, item_id, context)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS playback_learning_outcomes (
                outcome_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                signal TEXT NOT NULL,
                provider TEXT NOT NULL,
                item_id TEXT NOT NULL,
                context TEXT NOT NULL,
                delta REAL NOT NULL,
                completion_ratio REAL,
                playback_seconds REAL,
                rating INTEGER,
                observed_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_outbox_pending ON event_outbox (published_at, claim_until, occurred_at)",
            """
            CREATE INDEX IF NOT EXISTS idx_provider_connections_account
            ON provider_connections (provider, provider_user_id, revoked_at)
            """,
        ]
        with self.connect() as connection:
            for statement in statements:
                self._execute(connection, statement)

    def upsert_consent(self, user_id: str, purpose_id: str, policy_version: str) -> None:
        now = utc_now().isoformat()
        with self.connect() as connection:
            self._execute(
                connection,
                """
                INSERT INTO consent_grants
                    (user_id, purpose_id, policy_version, status, granted_at, revoked_at)
                VALUES (%s, %s, %s, 'active', %s, NULL)
                ON CONFLICT(user_id, purpose_id) DO UPDATE SET
                    policy_version = excluded.policy_version,
                    status = 'active',
                    granted_at = excluded.granted_at,
                    revoked_at = NULL
                """,
                (user_id, purpose_id, policy_version, now),
            )

    def revoke_consent(self, user_id: str, purpose_id: str) -> bool:
        with self.connect() as connection:
            cursor = self._execute(
                connection,
                """
                UPDATE consent_grants SET status = 'revoked', revoked_at = %s
                WHERE user_id = %s AND purpose_id = %s AND status = 'active'
                """,
                (utc_now().isoformat(), user_id, purpose_id),
            )
            return cursor.rowcount > 0

    def has_active_consent(self, user_id: str, purpose_id: str) -> bool:
        with self.connect() as connection:
            row = self._execute(
                connection,
                "SELECT 1 FROM consent_grants WHERE user_id = %s AND purpose_id = %s AND status = 'active'",
                (user_id, purpose_id),
            ).fetchone()
            return row is not None

    def upsert_apple_music_user_token(self, user_id: str, encrypted_token: str) -> None:
        now = utc_now().isoformat()
        with self.connect() as connection:
            self._execute(
                connection,
                """
                INSERT INTO apple_music_user_tokens
                    (user_id, encrypted_token, created_at, updated_at, revoked_at)
                VALUES (%s, %s, %s, %s, NULL)
                ON CONFLICT(user_id) DO UPDATE SET
                    encrypted_token = excluded.encrypted_token,
                    updated_at = excluded.updated_at,
                    revoked_at = NULL
                """,
                (user_id, encrypted_token, now, now),
            )

    def get_apple_music_user_token(self, user_id: str) -> str | None:
        with self.connect() as connection:
            row = self._execute(
                connection,
                """
                SELECT encrypted_token FROM apple_music_user_tokens
                WHERE user_id = %s AND revoked_at IS NULL
                """,
                (user_id,),
            ).fetchone()
        return None if row is None else dict(row)["encrypted_token"]

    def revoke_apple_music_user_token(self, user_id: str) -> bool:
        with self.connect() as connection:
            cursor = self._execute(
                connection,
                """
                UPDATE apple_music_user_tokens SET revoked_at = %s
                WHERE user_id = %s AND revoked_at IS NULL
                """,
                (utc_now().isoformat(), user_id),
            )
            return cursor.rowcount > 0

    def upsert_provider_connection(
        self,
        *,
        session_id: str,
        provider: str,
        provider_user_id: str,
        encrypted_access_token: str,
        encrypted_refresh_token: str | None,
        expires_at: datetime,
        profile: dict[str, Any],
    ) -> None:
        now = utc_now().isoformat()
        with self.connect() as connection:
            self._execute(
                connection,
                """
                INSERT INTO provider_connections (
                    session_id, provider, provider_user_id,
                    encrypted_access_token, encrypted_refresh_token,
                    expires_at, profile_json, created_at, updated_at, revoked_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                ON CONFLICT(session_id) DO UPDATE SET
                    provider = excluded.provider,
                    provider_user_id = excluded.provider_user_id,
                    encrypted_access_token = excluded.encrypted_access_token,
                    encrypted_refresh_token = excluded.encrypted_refresh_token,
                    expires_at = excluded.expires_at,
                    profile_json = excluded.profile_json,
                    updated_at = excluded.updated_at,
                    revoked_at = NULL
                """,
                (
                    session_id,
                    provider,
                    provider_user_id,
                    encrypted_access_token,
                    encrypted_refresh_token,
                    expires_at.isoformat(),
                    json.dumps(profile),
                    now,
                    now,
                ),
            )

    def get_provider_connection(self, session_id: str, provider: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = self._execute(
                connection,
                """
                SELECT session_id, provider, provider_user_id,
                       encrypted_access_token, encrypted_refresh_token,
                       expires_at, profile_json
                FROM provider_connections
                WHERE session_id = %s AND provider = %s AND revoked_at IS NULL
                """,
                (session_id, provider),
            ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["profile"] = json.loads(payload.pop("profile_json"))
        return payload

    def revoke_provider_connection(self, session_id: str, provider: str) -> bool:
        with self.connect() as connection:
            cursor = self._execute(
                connection,
                """
                UPDATE provider_connections SET revoked_at = %s, updated_at = %s
                WHERE session_id = %s AND provider = %s AND revoked_at IS NULL
                """,
                (utc_now().isoformat(), utc_now().isoformat(), session_id, provider),
            )
            return cursor.rowcount > 0

    def append_event(
        self,
        event_id: str,
        event_type: str,
        user_id: str,
        trace_id: str,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as connection:
            self._execute(
                connection,
                """
                INSERT INTO event_outbox
                    (event_id, event_type, user_id, occurred_at, trace_id, payload_json)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(event_id) DO NOTHING
                """,
                (
                    event_id,
                    event_type,
                    user_id,
                    utc_now().isoformat(),
                    trace_id,
                    json.dumps(payload),
                ),
            )

    def claim_outbox(
        self, worker_id: str, limit: int = 100, lease_seconds: int = 30
    ) -> list[dict[str, Any]]:
        now = utc_now()
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
        with self.connect() as connection:
            if self.is_postgres:
                rows = self._execute(
                    connection,
                    """
                    SELECT event_id FROM event_outbox
                    WHERE published_at IS NULL AND (claim_until IS NULL OR claim_until < %s)
                    ORDER BY occurred_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                    """,
                    (now.isoformat(), limit),
                ).fetchall()
            else:
                rows = self._execute(
                    connection,
                    """
                    SELECT event_id FROM event_outbox
                    WHERE published_at IS NULL AND (claim_until IS NULL OR claim_until < %s)
                    ORDER BY occurred_at LIMIT %s
                    """,
                    (now.isoformat(), limit),
                ).fetchall()
            event_ids = [dict(row)["event_id"] for row in rows]
            for event_id in event_ids:
                self._execute(
                    connection,
                    """
                    UPDATE event_outbox SET claimed_by = %s, claim_until = %s,
                        publish_attempts = publish_attempts + 1, last_error = NULL
                    WHERE event_id = %s AND published_at IS NULL
                    """,
                    (worker_id, lease_until, event_id),
                )
            claimed = []
            for event_id in event_ids:
                row = self._execute(
                    connection, "SELECT * FROM event_outbox WHERE event_id = %s", (event_id,)
                ).fetchone()
                item = dict(row)
                item["payload"] = json.loads(item.pop("payload_json"))
                claimed.append(item)
            return claimed

    def mark_event_published(self, event_id: str, worker_id: str) -> bool:
        with self.connect() as connection:
            cursor = self._execute(
                connection,
                """
                UPDATE event_outbox SET published_at = %s, claimed_by = NULL, claim_until = NULL
                WHERE event_id = %s AND claimed_by = %s AND published_at IS NULL
                """,
                (utc_now().isoformat(), event_id, worker_id),
            )
            return cursor.rowcount > 0

    def release_event_claim(self, event_id: str, worker_id: str, error: str) -> None:
        with self.connect() as connection:
            self._execute(
                connection,
                """
                UPDATE event_outbox SET claimed_by = NULL, claim_until = NULL, last_error = %s
                WHERE event_id = %s AND claimed_by = %s AND published_at IS NULL
                """,
                (error[:1000], event_id, worker_id),
            )

    def save_decision_trace(
        self,
        decision_id: str,
        user_id: str,
        context: str,
        context_confidence: float,
        provider: str,
        item_id: str,
        factors: dict[str, Any],
    ) -> None:
        with self.connect() as connection:
            self._execute(
                connection,
                """
                INSERT INTO decision_traces
                    (decision_id, user_id, context, context_confidence, provider,
                     item_id, factors_json, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    decision_id,
                    user_id,
                    context,
                    context_confidence,
                    provider,
                    item_id,
                    json.dumps(factors),
                    utc_now().isoformat(),
                ),
            )

    def get_decision_trace(self, decision_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = self._execute(
                connection, "SELECT * FROM decision_traces WHERE decision_id = %s", (decision_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["factors"] = json.loads(result.pop("factors_json"))
        return result
