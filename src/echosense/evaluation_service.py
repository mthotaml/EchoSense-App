from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from echosense.evaluation import (
    AttributedOutcome,
    CounterfactualReport,
    evaluate_counterfactual,
    normalize_reward,
    snapshot_candidates,
)
from echosense.evaluation_store import EvaluationStore
from echosense.storage import Storage


class EvaluationService:
    """Read-only evaluator over persisted decision traces and attributed outcomes."""

    def __init__(self, storage: Storage, store: EvaluationStore | None = None) -> None:
        self.storage = storage
        self.store = store or EvaluationStore(storage)

    def attribute_and_evaluate(
        self,
        *,
        outcome_id: str,
        decision_id: str,
        outcome: str,
        observed_at: datetime | None = None,
        playback_seconds: float | None = None,
        completion_ratio: float | None = None,
        attribution_window_seconds: int = 3600,
    ) -> CounterfactualReport:
        trace = self.storage.get_decision_trace(decision_id)
        if trace is None:
            raise LookupError("Decision trace not found")
        if attribution_window_seconds < 1:
            raise ValueError("attribution_window_seconds must be positive")

        instant = observed_at or datetime.now(timezone.utc)
        decision_time = datetime.fromisoformat(trace["created_at"])
        if instant - decision_time > timedelta(seconds=attribution_window_seconds):
            raise ValueError("Outcome falls outside the attribution window")

        candidate_slate: list[dict[str, Any]] | None = trace["factors"].get("candidate_slate")
        if not candidate_slate:
            raise ValueError("Decision trace does not contain a candidate slate")

        attributed = AttributedOutcome(
            outcome_id=outcome_id,
            decision_id=decision_id,
            outcome=outcome,
            reward=normalize_reward(
                outcome,
                playback_seconds=playback_seconds,
                completion_ratio=completion_ratio,
            ),
            observed_at=instant,
            playback_seconds=playback_seconds,
            completion_ratio=completion_ratio,
            attribution_window_seconds=attribution_window_seconds,
        )
        inserted = self.store.record_outcome(attributed)
        if not inserted:
            existing = self.store.get_report(outcome_id)
            if existing is None:
                raise RuntimeError("Outcome already exists without an evaluation report")
            return self._report_from_dict(existing)

        selected_canonical_track_id = str(
            trace["factors"].get("canonical_track_id") or trace["item_id"]
        )
        report = evaluate_counterfactual(
            decision_id=decision_id,
            outcome=attributed,
            candidates=snapshot_candidates(candidate_slate, selected_canonical_track_id),
        )
        self.store.save_report(report)
        return report

    @staticmethod
    def _report_from_dict(payload: dict[str, Any]) -> CounterfactualReport:
        from echosense.evaluation import CounterfactualCandidate

        alternative = payload.get("best_alternative")
        return CounterfactualReport(
            decision_id=payload["decision_id"],
            outcome_id=payload["outcome_id"],
            observed_reward=float(payload["observed_reward"]),
            selected_canonical_track_id=payload.get(
                "selected_canonical_track_id", payload["selected_item_id"]
            ),
            selected_item_id=payload["selected_item_id"],
            selected_provider_binding=payload.get("selected_provider_binding"),
            best_alternative=(CounterfactualCandidate(**alternative) if alternative else None),
            estimated_regret=float(payload["estimated_regret"]),
            confidence=payload["confidence"],
            evaluated_at=datetime.fromisoformat(payload["evaluated_at"]),
        )
