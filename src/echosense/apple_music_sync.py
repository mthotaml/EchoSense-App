from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from echosense.app import get_music_provider, get_storage
from echosense.providers import MusicProvider, ProviderSignal
from echosense.storage import Storage

router = APIRouter(prefix="/v1/users/{user_id}/providers/apple-music", tags=["apple-music-sync"])


class AppleMusicSyncResponse(BaseModel):
    sync_id: str | None = None
    status: Literal["not_started", "syncing", "completed", "failed"]
    library_songs: int = 0
    recent_plays: int = 0
    playlists: int = 0
    total_signals: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class AppleMusicSyncStore:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.initialize()

    def initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS provider_syncs (
                sync_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                status TEXT NOT NULL,
                library_songs INTEGER NOT NULL DEFAULT 0,
                recent_plays INTEGER NOT NULL DEFAULT 0,
                playlists INTEGER NOT NULL DEFAULT 0,
                total_signals INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                error TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS provider_signals (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                item_id TEXT NOT NULL,
                name TEXT NOT NULL,
                artist TEXT,
                album TEXT,
                storefront TEXT,
                source_path TEXT NOT NULL,
                synced_at TEXT NOT NULL,
                PRIMARY KEY (user_id, provider, signal_type, item_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_provider_syncs_user ON provider_syncs (user_id, provider, started_at)",
        ]
        with self.storage.connect() as connection:
            for statement in statements:
                self.storage._execute(connection, statement)

    def start(self, user_id: str) -> str:
        sync_id = f"sync_{uuid4().hex}"
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                INSERT INTO provider_syncs
                    (sync_id, user_id, provider, status, started_at)
                VALUES (%s, %s, 'apple_music', 'syncing', %s)
                """,
                (sync_id, user_id, datetime.now(timezone.utc).isoformat()),
            )
        return sync_id

    def save_signals(self, user_id: str, signals: list[ProviderSignal]) -> None:
        synced_at = datetime.now(timezone.utc).isoformat()
        with self.storage.connect() as connection:
            for signal in signals:
                self.storage._execute(
                    connection,
                    """
                    INSERT INTO provider_signals
                        (user_id, provider, signal_type, item_id, name, artist, album,
                         storefront, source_path, synced_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(user_id, provider, signal_type, item_id) DO UPDATE SET
                        name = excluded.name,
                        artist = excluded.artist,
                        album = excluded.album,
                        storefront = excluded.storefront,
                        source_path = excluded.source_path,
                        synced_at = excluded.synced_at
                    """,
                    (
                        user_id,
                        signal.provider,
                        signal.signal_type,
                        signal.item_id,
                        signal.name,
                        signal.artist,
                        signal.album,
                        signal.storefront,
                        signal.source_path,
                        synced_at,
                    ),
                )

    def complete(
        self, sync_id: str, *, library_songs: int, recent_plays: int, playlists: int = 0
    ) -> None:
        total = library_songs + recent_plays + playlists
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                UPDATE provider_syncs SET status = 'completed', library_songs = %s,
                    recent_plays = %s, playlists = %s, total_signals = %s,
                    completed_at = %s, error = NULL
                WHERE sync_id = %s
                """,
                (
                    library_songs,
                    recent_plays,
                    playlists,
                    total,
                    datetime.now(timezone.utc).isoformat(),
                    sync_id,
                ),
            )

    def fail(self, sync_id: str, error: str) -> None:
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                UPDATE provider_syncs SET status = 'failed', completed_at = %s, error = %s
                WHERE sync_id = %s
                """,
                (datetime.now(timezone.utc).isoformat(), error[:1000], sync_id),
            )

    def latest(self, user_id: str) -> dict[str, Any] | None:
        with self.storage.connect() as connection:
            row = self.storage._execute(
                connection,
                """
                SELECT * FROM provider_syncs
                WHERE user_id = %s AND provider = 'apple_music'
                ORDER BY started_at DESC LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return None if row is None else dict(row)


class AppleMusicSyncService:
    def __init__(self, provider: MusicProvider, store: AppleMusicSyncStore) -> None:
        self.provider = provider
        self.store = store

    def run(
        self, user_id: str, *, library_limit: int = 100, recent_limit: int = 30
    ) -> dict[str, Any]:
        sync_id = self.store.start(user_id)
        try:
            library = self.provider.sync_library(user_id, limit=library_limit)
            recent = self.provider.sync_recent_plays(user_id, limit=recent_limit)
            self.store.save_signals(user_id, [*library, *recent])
            self.store.complete(sync_id, library_songs=len(library), recent_plays=len(recent))
        except Exception as exc:
            self.store.fail(sync_id, str(exc))
            raise
        return self.store.latest(user_id) or {}


def _response(row: dict[str, Any] | None) -> AppleMusicSyncResponse:
    if row is None:
        return AppleMusicSyncResponse(status="not_started")
    return AppleMusicSyncResponse.model_validate(row)


@router.get("/sync", response_model=AppleMusicSyncResponse)
def get_sync_status(user_id: str) -> AppleMusicSyncResponse:
    return _response(AppleMusicSyncStore(get_storage()).latest(user_id))


@router.post("/sync", response_model=AppleMusicSyncResponse)
def start_sync(user_id: str) -> AppleMusicSyncResponse:
    store = AppleMusicSyncStore(get_storage())
    try:
        row = AppleMusicSyncService(get_music_provider(), store).run(user_id)
    except (PermissionError, RuntimeError, ValueError, OSError) as exc:
        raise HTTPException(
            status_code=503, detail={"code": "apple_music_sync_failed", "message": str(exc)}
        ) from exc
    get_storage().append_event(
        event_id=f"evt_{uuid4().hex}",
        event_type="provider.sync.completed",
        user_id=user_id,
        trace_id=f"trc_{uuid4().hex}",
        payload={"provider": "apple_music", "total_signals": row.get("total_signals", 0)},
    )
    return _response(row)
