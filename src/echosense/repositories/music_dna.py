from __future__ import annotations

import json
from dataclasses import asdict

from echosense.providers.models import MusicDataImport
from echosense.storage import Storage


class MusicDNARepository:
    """Persists normalized provider observations, never raw provider payloads."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def save(self, user_id: str, imported: MusicDataImport) -> None:
        payload = json.dumps(asdict(imported), default=str, separators=(",", ":"))
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                INSERT INTO music_data_imports
                    (user_id, provider, imported_at, normalized_json)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(user_id, provider) DO UPDATE SET
                    imported_at = excluded.imported_at,
                    normalized_json = excluded.normalized_json
                """,
                (user_id, imported.provider, imported.imported_at.isoformat(), payload),
            )

    def raw_snapshot(self, user_id: str, provider: str) -> dict[str, object] | None:
        with self.storage.connect() as connection:
            row = self.storage._execute(
                connection,
                """
                SELECT normalized_json FROM music_data_imports
                WHERE user_id = %s AND provider = %s
                """,
                (user_id, provider),
            ).fetchone()
        return None if row is None else json.loads(dict(row)["normalized_json"])
