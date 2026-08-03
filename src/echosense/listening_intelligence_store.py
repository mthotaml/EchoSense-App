from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from echosense.recording_identity import RecordingIdentityRegistry, RecordingReference
from echosense.storage import Storage, utc_now


@dataclass(frozen=True)
class EchoUserIdentity:
    echo_user_id: str
    provider: str
    provider_user_id: str


@dataclass(frozen=True)
class IntelligenceEventResult:
    event_id: str
    echo_user_id: str
    echo_track_id: str
    applied: bool


class ListeningIntelligenceStore:
    """Provider-neutral source of truth for listening behavior and product KPIs."""

    EVENT_WEIGHTS = {
        "played": 0.01,
        "completed": 0.08,
        "skipped": -0.08,
        "saved": 0.12,
        "unsaved": -0.05,
        "liked": 0.12,
        "disliked": -0.15,
        "rated": 0.0,
        "replayed": 0.1,
    }

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.recordings = RecordingIdentityRegistry(storage)
        self.initialize()

    def initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS echo_users (
                echo_user_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS provider_user_aliases (
                provider TEXT NOT NULL,
                provider_user_id TEXT NOT NULL,
                echo_user_id TEXT NOT NULL,
                display_name TEXT,
                linked_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY (provider, provider_user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS provider_track_catalog (
                provider TEXT NOT NULL,
                provider_track_id TEXT NOT NULL,
                echo_track_id TEXT NOT NULL,
                title TEXT NOT NULL,
                artists_json TEXT NOT NULL,
                album TEXT,
                isrc TEXT,
                duration_ms INTEGER,
                image_url TEXT,
                metadata_json TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                PRIMARY KEY (provider, provider_track_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS listening_sessions (
                listening_session_id TEXT PRIMARY KEY,
                echo_user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_session_id TEXT NOT NULL,
                context_json TEXT NOT NULL,
                started_at TEXT NOT NULL,
                last_event_at TEXT NOT NULL,
                ended_at TEXT,
                UNIQUE (provider, provider_session_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS listening_events (
                event_id TEXT PRIMARY KEY,
                echo_user_id TEXT NOT NULL,
                listening_session_id TEXT,
                echo_track_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_track_id TEXT NOT NULL,
                decision_id TEXT,
                event_type TEXT NOT NULL,
                context TEXT NOT NULL,
                playback_seconds REAL,
                completion_ratio REAL,
                rating INTEGER,
                payload_json TEXT NOT NULL,
                occurred_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS user_track_intelligence (
                echo_user_id TEXT NOT NULL,
                echo_track_id TEXT NOT NULL,
                total_listen_seconds REAL NOT NULL DEFAULT 0,
                play_count INTEGER NOT NULL DEFAULT 0,
                completion_count INTEGER NOT NULL DEFAULT 0,
                skip_count INTEGER NOT NULL DEFAULT 0,
                save_count INTEGER NOT NULL DEFAULT 0,
                unsave_count INTEGER NOT NULL DEFAULT 0,
                like_count INTEGER NOT NULL DEFAULT 0,
                dislike_count INTEGER NOT NULL DEFAULT 0,
                replay_count INTEGER NOT NULL DEFAULT 0,
                preference_score REAL NOT NULL DEFAULT 0,
                first_event_at TEXT NOT NULL,
                last_event_at TEXT NOT NULL,
                PRIMARY KEY (echo_user_id, echo_track_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_listening_events_user_time
            ON listening_events (echo_user_id, occurred_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_listening_events_decision
            ON listening_events (decision_id, event_type)
            """,
        ]
        with self.storage.connect() as connection:
            for statement in statements:
                self.storage._execute(connection, statement)

    def resolve_user(
        self,
        *,
        provider: str,
        provider_user_id: str,
        display_name: str | None = None,
        echo_user_id: str | None = None,
    ) -> EchoUserIdentity:
        provider = provider.strip().casefold()
        provider_user_id = provider_user_id.strip()
        if not provider or not provider_user_id:
            raise ValueError("Provider user identity is required")
        with self.storage.connect() as connection:
            existing = self.storage._execute(
                connection,
                """
                SELECT echo_user_id FROM provider_user_aliases
                WHERE provider = %s AND provider_user_id = %s
                """,
                (provider, provider_user_id),
            ).fetchone()
            if existing is not None:
                resolved_id = str(dict(existing)["echo_user_id"])
                self.storage._execute(
                    connection,
                    """
                    UPDATE provider_user_aliases
                    SET display_name = COALESCE(%s, display_name), last_seen_at = %s
                    WHERE provider = %s AND provider_user_id = %s
                    """,
                    (display_name, utc_now().isoformat(), provider, provider_user_id),
                )
                return EchoUserIdentity(resolved_id, provider, provider_user_id)
            resolved_id = echo_user_id or self._echo_user_id(provider, provider_user_id)
            now = utc_now().isoformat()
            self.storage._execute(
                connection,
                """
                INSERT INTO echo_users (echo_user_id, created_at, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT(echo_user_id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (resolved_id, now, now),
            )
            self.storage._execute(
                connection,
                """
                INSERT INTO provider_user_aliases (
                    provider, provider_user_id, echo_user_id, display_name,
                    linked_at, last_seen_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (provider, provider_user_id, resolved_id, display_name, now, now),
            )
        return EchoUserIdentity(resolved_id, provider, provider_user_id)

    def observe_track(
        self,
        reference: RecordingReference,
        *,
        image_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        resolution = self.recordings.resolve(reference)
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                INSERT INTO provider_track_catalog (
                    provider, provider_track_id, echo_track_id, title, artists_json,
                    album, isrc, duration_ms, image_url, metadata_json, observed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(provider, provider_track_id) DO UPDATE SET
                    echo_track_id = excluded.echo_track_id,
                    title = excluded.title,
                    artists_json = excluded.artists_json,
                    album = excluded.album,
                    isrc = excluded.isrc,
                    duration_ms = excluded.duration_ms,
                    image_url = excluded.image_url,
                    metadata_json = excluded.metadata_json,
                    observed_at = excluded.observed_at
                """,
                (
                    reference.provider.casefold(),
                    reference.provider_id,
                    resolution.canonical_id,
                    reference.title,
                    json.dumps(list(reference.artists)),
                    reference.album,
                    reference.isrc,
                    reference.duration_ms,
                    image_url,
                    json.dumps(metadata or {}),
                    utc_now().isoformat(),
                ),
            )
        return resolution.canonical_id

    def ensure_session(
        self,
        *,
        echo_user_id: str,
        provider: str,
        provider_session_id: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        session_id = f"es_session_{uuid5(NAMESPACE_URL, f'{provider}:{provider_session_id}').hex}"
        now = utc_now().isoformat()
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                INSERT INTO listening_sessions (
                    listening_session_id, echo_user_id, provider, provider_session_id,
                    context_json, started_at, last_event_at, ended_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
                ON CONFLICT(provider, provider_session_id) DO UPDATE SET
                    echo_user_id = excluded.echo_user_id,
                    context_json = excluded.context_json,
                    last_event_at = excluded.last_event_at,
                    ended_at = NULL
                """,
                (
                    session_id,
                    echo_user_id,
                    provider.casefold(),
                    provider_session_id,
                    json.dumps(context or {}),
                    now,
                    now,
                ),
            )
        return session_id

    def record_event(
        self,
        *,
        event_id: str,
        echo_user_id: str,
        echo_track_id: str,
        provider: str,
        provider_track_id: str,
        event_type: str,
        context: str,
        decision_id: str | None = None,
        listening_session_id: str | None = None,
        playback_seconds: float | None = None,
        completion_ratio: float | None = None,
        rating: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> IntelligenceEventResult:
        if event_type not in self.EVENT_WEIGHTS:
            raise ValueError(f"Unsupported listening event: {event_type}")
        now = utc_now().isoformat()
        with self.storage.connect() as connection:
            existing = self.storage._execute(
                connection,
                """
                SELECT echo_user_id, echo_track_id, event_type
                FROM listening_events WHERE event_id = %s
                """,
                (event_id,),
            ).fetchone()
            if existing is not None:
                values = dict(existing)
                if (
                    values["echo_user_id"] != echo_user_id
                    or values["echo_track_id"] != echo_track_id
                    or values["event_type"] != event_type
                ):
                    raise ValueError("event_id is already bound to different evidence")
                return IntelligenceEventResult(event_id, echo_user_id, echo_track_id, False)
            self.storage._execute(
                connection,
                """
                INSERT INTO listening_events (
                    event_id, echo_user_id, listening_session_id, echo_track_id,
                    provider, provider_track_id, decision_id, event_type, context,
                    playback_seconds, completion_ratio, rating, payload_json, occurred_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event_id,
                    echo_user_id,
                    listening_session_id,
                    echo_track_id,
                    provider.casefold(),
                    provider_track_id,
                    decision_id,
                    event_type,
                    context,
                    playback_seconds,
                    completion_ratio,
                    rating,
                    json.dumps(payload or {}),
                    now,
                ),
            )
            self._update_track_intelligence(
                connection,
                echo_user_id=echo_user_id,
                echo_track_id=echo_track_id,
                event_type=event_type,
                playback_seconds=playback_seconds,
                rating=rating,
                observed_at=now,
            )
            if listening_session_id:
                self.storage._execute(
                    connection,
                    """
                    UPDATE listening_sessions SET last_event_at = %s
                    WHERE listening_session_id = %s
                    """,
                    (now, listening_session_id),
                )
        return IntelligenceEventResult(event_id, echo_user_id, echo_track_id, True)

    def listener_snapshot(self, echo_user_id: str) -> dict[str, object]:
        with self.storage.connect() as connection:
            summary_row = self.storage._execute(
                connection,
                """
                SELECT
                    COUNT(*) AS events,
                    COUNT(DISTINCT echo_track_id) AS tracks,
                    COUNT(DISTINCT listening_session_id) AS sessions,
                    COALESCE(SUM(playback_seconds), 0) AS listen_seconds,
                    SUM(CASE WHEN event_type = 'completed' THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN event_type = 'skipped' THEN 1 ELSE 0 END) AS skipped,
                    SUM(CASE WHEN event_type = 'saved' THEN 1 ELSE 0 END) AS saved,
                    SUM(CASE WHEN event_type = 'unsaved' THEN 1 ELSE 0 END) AS unsaved,
                    SUM(CASE WHEN event_type = 'liked' THEN 1 ELSE 0 END) AS liked,
                    SUM(CASE WHEN event_type = 'disliked' THEN 1 ELSE 0 END) AS disliked,
                    SUM(CASE WHEN event_type = 'replayed' THEN 1 ELSE 0 END) AS replayed
                FROM listening_events WHERE echo_user_id = %s
                """,
                (echo_user_id,),
            ).fetchone()
            top_rows = self.storage._execute(
                connection,
                """
                SELECT i.*, c.title, c.artists_json, c.provider, c.provider_track_id
                FROM user_track_intelligence i
                JOIN provider_track_catalog c ON c.echo_track_id = i.echo_track_id
                WHERE i.echo_user_id = %s
                ORDER BY i.preference_score DESC, i.total_listen_seconds DESC
                LIMIT 10
                """,
                (echo_user_id,),
            ).fetchall()
        summary = dict(summary_row)
        completed = int(summary["completed"] or 0)
        skipped = int(summary["skipped"] or 0)
        qualified = completed + skipped
        positive = completed + int(summary["saved"] or 0) + int(summary["liked"] or 0)
        negative = skipped + int(summary["unsaved"] or 0) + int(summary["disliked"] or 0)
        decisions = positive + negative
        return {
            "echo_user_id": echo_user_id,
            "scope": "provider_neutral_listener",
            "summary": {
                **{
                    key: int(value or 0)
                    for key, value in summary.items()
                    if key != "listen_seconds"
                },
                "listen_seconds": round(float(summary["listen_seconds"] or 0), 1),
                "completion_rate": round(completed / qualified * 100) if qualified else None,
                "recommendation_acceptance_rate": round(positive / decisions * 100)
                if decisions
                else None,
            },
            "top_tracks": [self._track_view(dict(row)) for row in top_rows],
        }

    def product_kpis(self) -> dict[str, object]:
        with self.storage.connect() as connection:
            row = self.storage._execute(
                connection,
                """
                SELECT COUNT(DISTINCT echo_user_id) AS listeners,
                       COUNT(DISTINCT listening_session_id) AS sessions,
                       COUNT(*) AS events,
                       COALESCE(SUM(playback_seconds), 0) AS listen_seconds,
                       SUM(CASE WHEN event_type = 'completed' THEN 1 ELSE 0 END) AS completed,
                       SUM(CASE WHEN event_type = 'skipped' THEN 1 ELSE 0 END) AS skipped
                FROM listening_events
                """,
            ).fetchone()
        values = dict(row)
        completed = int(values["completed"] or 0)
        skipped = int(values["skipped"] or 0)
        qualified = completed + skipped
        return {
            "listeners": int(values["listeners"] or 0),
            "sessions": int(values["sessions"] or 0),
            "events": int(values["events"] or 0),
            "listen_seconds": round(float(values["listen_seconds"] or 0), 1),
            "completion_rate": round(completed / qualified * 100) if qualified else None,
            "skip_rate": round(skipped / qualified * 100) if qualified else None,
        }

    def _update_track_intelligence(
        self,
        connection: Any,
        *,
        echo_user_id: str,
        echo_track_id: str,
        event_type: str,
        playback_seconds: float | None,
        rating: int | None,
        observed_at: str,
    ) -> None:
        counters = {
            "played": "play_count",
            "completed": "completion_count",
            "skipped": "skip_count",
            "saved": "save_count",
            "unsaved": "unsave_count",
            "liked": "like_count",
            "disliked": "dislike_count",
            "replayed": "replay_count",
        }
        values = {name: 0 for name in counters.values()}
        if event_type in counters:
            values[counters[event_type]] = 1
        adjustment = self.EVENT_WEIGHTS[event_type]
        if event_type == "rated" and rating is not None:
            adjustment = (rating - 3) * 0.06
        self.storage._execute(
            connection,
            """
            INSERT INTO user_track_intelligence (
                echo_user_id, echo_track_id, total_listen_seconds, play_count,
                completion_count, skip_count, save_count, unsave_count,
                like_count, dislike_count, replay_count, preference_score,
                first_event_at, last_event_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(echo_user_id, echo_track_id) DO UPDATE SET
                total_listen_seconds = user_track_intelligence.total_listen_seconds + excluded.total_listen_seconds,
                play_count = user_track_intelligence.play_count + excluded.play_count,
                completion_count = user_track_intelligence.completion_count + excluded.completion_count,
                skip_count = user_track_intelligence.skip_count + excluded.skip_count,
                save_count = user_track_intelligence.save_count + excluded.save_count,
                unsave_count = user_track_intelligence.unsave_count + excluded.unsave_count,
                like_count = user_track_intelligence.like_count + excluded.like_count,
                dislike_count = user_track_intelligence.dislike_count + excluded.dislike_count,
                replay_count = user_track_intelligence.replay_count + excluded.replay_count,
                preference_score = CASE
                    WHEN user_track_intelligence.preference_score + excluded.preference_score > 1 THEN 1
                    WHEN user_track_intelligence.preference_score + excluded.preference_score < -1 THEN -1
                    ELSE user_track_intelligence.preference_score + excluded.preference_score
                END,
                last_event_at = excluded.last_event_at
            """,
            (
                echo_user_id,
                echo_track_id,
                float(playback_seconds or 0),
                values["play_count"],
                values["completion_count"],
                values["skip_count"],
                values["save_count"],
                values["unsave_count"],
                values["like_count"],
                values["dislike_count"],
                values["replay_count"],
                adjustment,
                observed_at,
                observed_at,
            ),
        )

    @staticmethod
    def _echo_user_id(provider: str, provider_user_id: str) -> str:
        return f"es_user_{uuid5(NAMESPACE_URL, f'{provider}:{provider_user_id}').hex}"

    @staticmethod
    def _track_view(row: dict[str, Any]) -> dict[str, object]:
        return {
            "echo_track_id": row["echo_track_id"],
            "title": row["title"],
            "artists": json.loads(row["artists_json"]),
            "provider": row["provider"],
            "provider_track_id": row["provider_track_id"],
            "preference_score": round(float(row["preference_score"]), 3),
            "total_listen_seconds": round(float(row["total_listen_seconds"]), 1),
            "completed": int(row["completion_count"]),
            "skipped": int(row["skip_count"]),
            "saved": int(row["save_count"]),
            "liked": int(row["like_count"]),
            "disliked": int(row["dislike_count"]),
        }
