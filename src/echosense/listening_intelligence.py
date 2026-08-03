from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from echosense.storage import Storage


class ListeningIntelligenceService:
    """Builds truthful listener-facing intelligence from persisted decision outcomes."""

    POSITIVE = {"completed", "saved", "liked"}
    NEGATIVE = {"skipped", "disliked"}

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def snapshot(self, user_id: str, *, history_limit: int = 30) -> dict[str, object]:
        with self.storage.connect() as connection:
            rows = self.storage._execute(
                connection,
                """
                SELECT o.*, d.factors_json
                FROM playback_learning_outcomes o
                LEFT JOIN decision_traces d ON d.decision_id = o.decision_id
                WHERE o.user_id = %s
                ORDER BY o.observed_at DESC
                LIMIT %s
                """,
                (user_id, max(1, min(history_limit, 100))),
            ).fetchall()

        history = [self._history_item(dict(row)) for row in rows]
        total_seconds = round(sum(float(item["playback_seconds"] or 0.0) for item in history), 1)
        signal_counts = Counter(str(item["signal"]) for item in history)
        contexts = Counter(str(item["moment"]) for item in history if item["moment"])
        unique_tracks = len({str(item["provider_track_id"]) for item in history})
        completed = signal_counts["completed"]
        skipped = signal_counts["skipped"]
        positive = sum(signal_counts[signal] for signal in self.POSITIVE)
        qualified = completed + skipped
        completion_rate = round(completed / qualified * 100) if qualified else None
        early_skips = sum(
            1
            for item in history
            if item["signal"] == "skipped" and float(item["completion_ratio"] or 0.0) < 0.2
        )
        recommendations = len({str(item["decision_id"]) for item in history})
        acceptance_rate = round(positive / recommendations * 100) if recommendations else None
        moment_rows = [
            {"moment": moment, "signals": count} for moment, count in contexts.most_common(6)
        ]
        trend = self._daily_trend(history)
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "scope": "connected_listener",
            "data_status": "ready" if history else "learning",
            "summary": {
                "total_listen_seconds": total_seconds,
                "tracks_observed": unique_tracks,
                "completed": completed,
                "skipped": skipped,
                "saved": signal_counts["saved"],
                "loved": signal_counts["liked"],
                "disliked": signal_counts["disliked"],
                "early_skips": early_skips,
                "completion_rate": completion_rate,
                "recommendation_acceptance_rate": acceptance_rate,
                "recommendations_with_outcomes": recommendations,
            },
            "moments": moment_rows,
            "trend": trend,
            "history": history,
            "capabilities": {
                "history_correction": True,
                "personalization_reset": False,
                "data_export": False,
                "verified_deletion": False,
            },
        }

    @staticmethod
    def _history_item(row: dict[str, Any]) -> dict[str, object]:
        factors = json.loads(row.get("factors_json") or "{}")
        track = factors.get("track_snapshot") or {}
        moment = factors.get("listening_moment") or row.get("context")
        return {
            "outcome_id": row["outcome_id"],
            "decision_id": row["decision_id"],
            "echo_track_id": factors.get("echo_track_id"),
            "provider": row["provider"],
            "provider_track_id": row["item_id"],
            "title": track.get("title") or "Previously recommended track",
            "artist": track.get("artist") or "Provider metadata not retained",
            "signal": row["signal"],
            "moment": moment,
            "playback_seconds": row.get("playback_seconds"),
            "completion_ratio": row.get("completion_ratio"),
            "observed_at": row["observed_at"],
            "recommendation_score": factors.get("recommendation_score"),
            "explanation": factors.get("context_statement"),
        }

    @staticmethod
    def _daily_trend(history: list[dict[str, object]]) -> list[dict[str, object]]:
        days: dict[str, dict[str, float]] = {}
        for item in reversed(history):
            day = str(item["observed_at"])[:10]
            bucket = days.setdefault(day, {"listen_seconds": 0.0, "positive": 0, "skips": 0})
            bucket["listen_seconds"] += float(item["playback_seconds"] or 0.0)
            if item["signal"] in ListeningIntelligenceService.POSITIVE:
                bucket["positive"] += 1
            if item["signal"] == "skipped":
                bucket["skips"] += 1
        return [{"date": day, **values} for day, values in list(days.items())[-14:]]
