from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from echosense.music_dna import MusicDNAProfile, TasteDimension
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

    def save_profile(self, profile: MusicDNAProfile) -> None:
        payload = json.dumps(asdict(profile), default=str, separators=(",", ":"))
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                INSERT INTO music_dna_profiles (user_id, generated_at, profile_json)
                VALUES (%s, %s, %s)
                ON CONFLICT(user_id) DO UPDATE SET
                    generated_at = excluded.generated_at,
                    profile_json = excluded.profile_json
                """,
                (profile.user_id, profile.generated_at.isoformat(), payload),
            )

    def get_profile(self, user_id: str) -> MusicDNAProfile | None:
        with self.storage.connect() as connection:
            row = self.storage._execute(
                connection,
                "SELECT profile_json FROM music_dna_profiles WHERE user_id = %s",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(dict(row)["profile_json"])
        payload["genres"] = tuple(TasteDimension(**item) for item in payload["genres"])
        payload["top_artists"] = tuple(TasteDimension(**item) for item in payload["top_artists"])
        payload["source_paths"] = tuple(payload["source_paths"])
        payload["generated_at"] = datetime.fromisoformat(payload["generated_at"])
        return MusicDNAProfile(**payload)
