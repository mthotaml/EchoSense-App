from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from echosense.providers.models import Track
from echosense.storage import Storage

PlaybackSignal = Literal["played", "completed", "skipped", "saved", "liked", "disliked", "rated"]


@dataclass(frozen=True)
class LearningResult:
    outcome_id: str
    decision_id: str
    signal: PlaybackSignal
    delta: float
    weight: float
    evidence_count: int
    applied: bool


class PlaybackLearningService:
    """Correlates playback evidence to decisions and updates durable ranking weights."""

    DELTAS = {
        "played": 0.01,
        "completed": 0.08,
        "skipped": -0.08,
        "saved": 0.12,
        "liked": 0.12,
        "disliked": -0.15,
    }

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def rank(
        self,
        *,
        user_id: str,
        provider: str,
        context: str,
        tracks: list[Track],
        context_scores: dict[str, float] | None = None,
    ) -> tuple[Track | None, list[dict[str, object]]]:
        weights = self._weights(user_id, provider, context, [track.provider_id for track in tracks])
        slate = []
        for rank, track in enumerate(tracks, start=1):
            base_score = round(1.0 - (rank - 1) * 0.05, 3)
            preference_weight = weights.get(track.provider_id, 0.0)
            context_fit = (context_scores or {}).get(track.provider_id, 0.0)
            ranking_score = round(base_score + 0.15 * context_fit + 0.25 * preference_weight, 6)
            slate.append(
                {
                    "provider": provider,
                    "item_id": track.provider_id,
                    "rank": rank,
                    "provider_base_score": base_score,
                    "preference_weight": preference_weight,
                    "context_fit": context_fit,
                    "ranking_score": ranking_score,
                }
            )
        slate.sort(key=lambda item: (-float(item["ranking_score"]), int(item["rank"])))
        for final_rank, item in enumerate(slate, start=1):
            item["final_rank"] = final_rank
            item["selected"] = final_rank == 1
        selected_id = str(slate[0]["item_id"]) if slate else None
        return next((track for track in tracks if track.provider_id == selected_id), None), slate

    def record(
        self,
        *,
        outcome_id: str,
        user_id: str,
        decision_id: str,
        signal: PlaybackSignal,
        completion_ratio: float | None = None,
        playback_seconds: float | None = None,
        rating: int | None = None,
    ) -> LearningResult:
        trace = self.storage.get_decision_trace(decision_id)
        if trace is None or trace["user_id"] != user_id:
            raise LookupError("Decision trace not found")
        delta = self._delta(signal, completion_ratio, rating)
        now = datetime.now(UTC).isoformat()
        with self.storage.connect() as connection:
            existing = self.storage._execute(
                connection,
                """
                SELECT user_id, decision_id, signal, delta
                FROM playback_learning_outcomes
                WHERE outcome_id = %s
                """,
                (outcome_id,),
            ).fetchone()
            if existing is not None and (
                dict(existing)["user_id"] != user_id
                or dict(existing)["decision_id"] != decision_id
                or dict(existing)["signal"] != signal
            ):
                raise ValueError("outcome_id is already bound to different evidence")
            if existing is None:
                self.storage._execute(
                    connection,
                    """
                    INSERT INTO playback_learning_outcomes (
                        outcome_id, user_id, decision_id, signal, provider, item_id,
                        context, delta, completion_ratio, playback_seconds, rating, observed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        outcome_id,
                        user_id,
                        decision_id,
                        signal,
                        trace["provider"],
                        trace["item_id"],
                        trace["context"],
                        delta,
                        completion_ratio,
                        playback_seconds,
                        rating,
                        now,
                    ),
                )
                self.storage._execute(
                    connection,
                    """
                    INSERT INTO music_item_preferences (
                        user_id, provider, item_id, context, weight,
                        evidence_count, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, 1, %s)
                    ON CONFLICT(user_id, provider, item_id, context) DO UPDATE SET
                        weight = CASE
                            WHEN music_item_preferences.weight + excluded.weight > 1.0 THEN 1.0
                            WHEN music_item_preferences.weight + excluded.weight < -1.0 THEN -1.0
                            ELSE music_item_preferences.weight + excluded.weight
                        END,
                        evidence_count = music_item_preferences.evidence_count + 1,
                        updated_at = excluded.updated_at
                    """,
                    (
                        user_id,
                        trace["provider"],
                        trace["item_id"],
                        trace["context"],
                        delta,
                        now,
                    ),
                )
                applied = True
            else:
                applied = False
            preference = self.storage._execute(
                connection,
                """
                SELECT weight, evidence_count FROM music_item_preferences
                WHERE user_id = %s AND provider = %s AND item_id = %s AND context = %s
                """,
                (user_id, trace["provider"], trace["item_id"], trace["context"]),
            ).fetchone()
        if preference is None:
            raise RuntimeError("Learning preference was not persisted")
        values = dict(preference)
        return LearningResult(
            outcome_id,
            decision_id,
            signal,
            delta,
            round(float(values["weight"]), 6),
            int(values["evidence_count"]),
            applied,
        )

    def _weights(
        self,
        user_id: str,
        provider: str,
        context: str,
        item_ids: list[str],
    ) -> dict[str, float]:
        if not item_ids:
            return {}
        placeholders = ",".join("%s" for _ in item_ids)
        with self.storage.connect() as connection:
            rows = self.storage._execute(
                connection,
                f"""
                SELECT item_id, weight FROM music_item_preferences
                WHERE user_id = %s AND provider = %s AND context = %s
                  AND item_id IN ({placeholders})
                """,
                (user_id, provider, context, *item_ids),
            ).fetchall()
        return {str(dict(row)["item_id"]): float(dict(row)["weight"]) for row in rows}

    def _delta(
        self, signal: PlaybackSignal, completion_ratio: float | None, rating: int | None
    ) -> float:
        if completion_ratio is not None and not 0.0 <= completion_ratio <= 1.0:
            raise ValueError("completion_ratio must be between 0 and 1")
        if signal == "rated":
            if rating is None or not 1 <= rating <= 5:
                raise ValueError("rating must be between 1 and 5")
            return round((rating - 3) * 0.06, 6)
        if rating is not None:
            raise ValueError("rating is only valid for rated outcomes")
        delta = self.DELTAS[signal]
        if signal == "completed" and completion_ratio is not None:
            delta *= completion_ratio
        if signal == "skipped" and completion_ratio is not None:
            delta *= 1.0 - completion_ratio
        return round(delta, 6)
