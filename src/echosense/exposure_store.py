from __future__ import annotations

from typing import Iterable

from echosense.storage import Storage, utc_now


class ExposureStore:
    """Consent-derived selection exposure counts used only for novelty scoring."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.initialize()

    def initialize(self) -> None:
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
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
            )

    def counts_for(
        self, user_id: str, candidates: Iterable[tuple[str, str]]
    ) -> dict[tuple[str, str], int]:
        keys = list(candidates)
        counts = {key: 0 for key in keys}
        if not keys:
            return counts
        with self.storage.connect() as connection:
            rows = self.storage._execute(
                connection,
                """
                SELECT provider, item_id, exposure_count
                FROM recommendation_exposures WHERE user_id = %s
                """,
                (user_id,),
            ).fetchall()
        for row in rows:
            item = dict(row)
            key = (item["provider"], item["item_id"])
            if key in counts:
                counts[key] = int(item["exposure_count"])
        return counts

    def record_selection(self, user_id: str, provider: str, item_id: str) -> int:
        now = utc_now().isoformat()
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                INSERT INTO recommendation_exposures
                    (user_id, provider, item_id, exposure_count, first_selected_at, last_selected_at)
                VALUES (%s, %s, %s, 1, %s, %s)
                ON CONFLICT(user_id, provider, item_id) DO UPDATE SET
                    exposure_count = recommendation_exposures.exposure_count + 1,
                    last_selected_at = excluded.last_selected_at
                """,
                (user_id, provider, item_id, now, now),
            )
            row = self.storage._execute(
                connection,
                """
                SELECT exposure_count FROM recommendation_exposures
                WHERE user_id = %s AND provider = %s AND item_id = %s
                """,
                (user_id, provider, item_id),
            ).fetchone()
        return int(dict(row)["exposure_count"])
