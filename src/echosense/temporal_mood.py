from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from math import exp, log
from typing import Literal

from echosense.providers.models import Track
from echosense.storage import Storage

Mood = Literal["romantic", "melancholy", "calm", "reflective", "energetic", "uplifting"]


@dataclass(frozen=True)
class MoodEvidence:
    mood: Mood
    source: str
    confidence: float


@dataclass(frozen=True)
class TemporalMoodProfile:
    daypart: str
    mood: Mood | None
    pattern_type: str
    evidence_count: int
    distinct_days: int
    confidence: float
    enabled: bool
    explanation: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class TemporalMoodLearningService:
    """Learns bounded mood-by-daypart patterns from qualified playback outcomes."""

    POLICY_VERSION = "temporal-mood-v1"
    POSITIVE_SIGNALS = {"completed", "saved", "liked"}
    NEGATIVE_SIGNALS = {"skipped", "disliked"}
    ROMANTIC_WORDS = {"love", "lover", "romance", "romantic", "kiss", "heart"}
    MELANCHOLY_WORDS = {
        "alone",
        "blue",
        "broken",
        "cry",
        "goodbye",
        "lonely",
        "miss",
        "rain",
        "sad",
        "tears",
    }

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def infer_track(
        self,
        track: Track,
        context_evidence: tuple[str, ...] | list[str] = (),
    ) -> MoodEvidence | None:
        evidence = " ".join(context_evidence).lower()
        if "rainy weather" in evidence:
            return MoodEvidence("melancholy", "live weather context", 0.72)
        if "mountain drive" in evidence:
            return MoodEvidence("reflective", "mountain-drive context", 0.72)
        if "coastal drive" in evidence:
            return MoodEvidence("uplifting", "coastal-drive context", 0.72)
        if "higher-energy driving" in evidence:
            return MoodEvidence("energetic", "driving-energy context", 0.72)

        words = {
            word.strip(".,!?()[]{}'\"").lower()
            for word in f"{track.title} {track.album or ''}".split()
        }
        if words & self.ROMANTIC_WORDS:
            return MoodEvidence("romantic", "explainable title/album rule", 0.45)
        if words & self.MELANCHOLY_WORDS:
            return MoodEvidence("melancholy", "explainable title/album rule", 0.4)
        return None

    def record(
        self,
        *,
        outcome_id: str,
        user_id: str,
        signal: str,
        trace: dict[str, object],
        completion_ratio: float | None = None,
        rating: int | None = None,
        observed_at: datetime | None = None,
    ) -> bool:
        factors = trace.get("factors")
        temporal = factors.get("temporal_mood") if isinstance(factors, dict) else None
        if (
            not isinstance(temporal, dict)
            or not temporal.get("mood")
            or not temporal.get("daypart")
        ):
            return False
        weight = self._evidence_weight(signal, completion_ratio, rating)
        if weight == 0:
            return False
        instant = observed_at or datetime.now(UTC)
        with self.storage.connect() as connection:
            cursor = self.storage._execute(
                connection,
                """
                INSERT INTO temporal_mood_observations (
                    outcome_id, user_id, recording_key, daypart, mood, signal,
                    evidence_weight, evidence_source, confidence, observed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(outcome_id) DO NOTHING
                """,
                (
                    outcome_id,
                    user_id,
                    str(temporal.get("recording_key") or trace["item_id"]),
                    str(temporal["daypart"]),
                    str(temporal["mood"]),
                    signal,
                    weight,
                    str(temporal.get("source") or "decision evidence"),
                    float(temporal.get("confidence") or 0.0),
                    instant.isoformat(),
                ),
            )
            return cursor.rowcount > 0

    def profile(
        self,
        *,
        user_id: str,
        daypart: str,
        now: datetime | None = None,
    ) -> TemporalMoodProfile:
        if not self.is_enabled(user_id):
            return self._empty(
                daypart, enabled=False, explanation="Temporal mood learning is disabled."
            )
        instant = now or datetime.now(UTC)
        since = instant - timedelta(days=28)
        with self.storage.connect() as connection:
            rows = self.storage._execute(
                connection,
                """
                SELECT mood, evidence_weight, confidence, observed_at
                FROM temporal_mood_observations
                WHERE user_id = %s AND daypart = %s AND observed_at >= %s
                ORDER BY observed_at DESC
                """,
                (user_id, daypart, since.isoformat()),
            ).fetchall()
        observations = [dict(row) for row in rows]
        if not observations:
            return self._empty(
                daypart,
                enabled=True,
                explanation=f"Still learning your {daypart.replace('_', ' ')} listening pattern.",
            )

        scores: dict[str, float] = {}
        positive_counts: dict[str, int] = {}
        days: dict[str, set[str]] = {}
        for item in observations:
            observed_at = datetime.fromisoformat(str(item["observed_at"]))
            age_days = max(0.0, (instant - observed_at).total_seconds() / 86400)
            decayed = float(item["evidence_weight"]) * exp(-log(2) * age_days / 7)
            mood = str(item["mood"])
            scores[mood] = scores.get(mood, 0.0) + decayed * float(item["confidence"])
            if float(item["evidence_weight"]) > 0:
                positive_counts[mood] = positive_counts.get(mood, 0) + 1
                days.setdefault(mood, set()).add(observed_at.date().isoformat())
        mood = max(scores, key=scores.get)
        evidence_count = positive_counts.get(mood, 0)
        distinct_days = len(days.get(mood, set()))
        recent = [item for item in observations[:5] if float(item["evidence_weight"]) > 0]
        recent_agreement = sum(str(item["mood"]) == mood for item in recent)
        stable = evidence_count >= 3 and distinct_days >= 2
        shift = recent_agreement >= 3
        if scores[mood] <= 0:
            return self._empty(
                daypart,
                enabled=True,
                explanation=f"Still learning your {daypart.replace('_', ' ')} listening pattern.",
                evidence_count=evidence_count,
                distinct_days=distinct_days,
            )
        if not stable and not shift:
            return self._empty(
                daypart,
                enabled=True,
                explanation=f"Still learning your {daypart.replace('_', ' ')} listening pattern.",
                evidence_count=evidence_count,
                distinct_days=distinct_days,
            )
        pattern_type = "stable_pattern" if stable else "recent_shift"
        confidence = min(
            0.95,
            round(0.45 + 0.08 * evidence_count + 0.06 * distinct_days, 3),
        )
        phrase = "often choose" if stable else "recently shifted toward"
        return TemporalMoodProfile(
            daypart,
            mood,  # type: ignore[arg-type]
            pattern_type,
            evidence_count,
            distinct_days,
            confidence,
            True,
            (
                f"You {phrase} {mood} music during {daypart.replace('_', ' ')}. "
                "EchoSense keeps this signal bounded by your Music DNA and feedback."
            ),
        )

    def correct(self, *, user_id: str, daypart: str, mood: str) -> int:
        with self.storage.connect() as connection:
            cursor = self.storage._execute(
                connection,
                """
                DELETE FROM temporal_mood_observations
                WHERE user_id = %s AND daypart = %s AND mood = %s
                """,
                (user_id, daypart, mood),
            )
            return cursor.rowcount

    def reset(self, user_id: str) -> int:
        with self.storage.connect() as connection:
            cursor = self.storage._execute(
                connection,
                "DELETE FROM temporal_mood_observations WHERE user_id = %s",
                (user_id,),
            )
            return cursor.rowcount

    def set_enabled(self, user_id: str, enabled: bool) -> None:
        with self.storage.connect() as connection:
            self.storage._execute(
                connection,
                """
                INSERT INTO temporal_mood_settings (user_id, enabled, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT(user_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (user_id, int(enabled), datetime.now(UTC).isoformat()),
            )

    def is_enabled(self, user_id: str) -> bool:
        with self.storage.connect() as connection:
            row = self.storage._execute(
                connection,
                "SELECT enabled FROM temporal_mood_settings WHERE user_id = %s",
                (user_id,),
            ).fetchone()
        return row is None or bool(dict(row)["enabled"])

    @staticmethod
    def _evidence_weight(
        signal: str,
        completion_ratio: float | None,
        rating: int | None,
    ) -> float:
        if signal == "completed":
            return 1.0 if completion_ratio is not None and completion_ratio >= 0.6 else 0.0
        if signal in {"saved", "liked"}:
            return 1.0
        if signal in {"skipped", "disliked"}:
            return -1.0
        if signal == "rated" and rating is not None:
            return 1.0 if rating >= 4 else -1.0 if rating <= 2 else 0.0
        return 0.0

    @staticmethod
    def _empty(
        daypart: str,
        *,
        enabled: bool,
        explanation: str,
        evidence_count: int = 0,
        distinct_days: int = 0,
    ) -> TemporalMoodProfile:
        return TemporalMoodProfile(
            daypart,
            None,
            "learning",
            evidence_count,
            distinct_days,
            0.0,
            enabled,
            explanation,
        )
