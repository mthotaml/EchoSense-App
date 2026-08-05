from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from echosense.evaluation_service import EvaluationService
from echosense.storage import Storage


def save_trace(storage: Storage) -> None:
    storage.save_decision_trace(
        decision_id="dec_eval_01",
        user_id="user_01",
        context="commute",
        context_confidence=0.9,
        provider="apple_music",
        item_id="selected",
        factors={
            "canonical_track_id": "es_recording_selected",
            "candidate_slate": [
                {
                    "provider": "apple_music",
                    "item_id": "selected",
                    "canonical_track_id": "es_recording_selected",
                    "provider_binding": {
                        "provider": "apple_music",
                        "provider_track_id": "selected",
                        "canonical_track_id": "es_recording_selected",
                        "playable": True,
                        "uri": None,
                        "external_url": None,
                    },
                    "rank": 1,
                    "provider_base_score": 0.8,
                    "preference_weight": 0.1,
                    "ranking_score": 0.825,
                },
                {
                    "provider": "apple_music",
                    "item_id": "alternative",
                    "canonical_track_id": "es_recording_alternative",
                    "rank": 2,
                    "provider_base_score": 0.79,
                    "preference_weight": 0.3,
                    "ranking_score": 0.865,
                },
                {
                    "provider": "apple_music",
                    "item_id": "third",
                    "canonical_track_id": "es_recording_third",
                    "rank": 3,
                    "provider_base_score": 0.7,
                    "preference_weight": 0.0,
                    "ranking_score": 0.7,
                },
            ],
        },
    )


def test_attribution_and_report_are_persisted_idempotently(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'evaluation.db'}")
    save_trace(storage)
    service = EvaluationService(storage)

    report = service.attribute_and_evaluate(
        outcome_id="out_eval_01",
        decision_id="dec_eval_01",
        outcome="skipped",
        playback_seconds=20,
        completion_ratio=0.1,
    )
    duplicate = service.attribute_and_evaluate(
        outcome_id="out_eval_01",
        decision_id="dec_eval_01",
        outcome="skipped",
        playback_seconds=20,
        completion_ratio=0.1,
    )

    assert report.best_alternative is not None
    assert report.selected_canonical_track_id == "es_recording_selected"
    assert report.selected_item_id == "selected"
    assert report.selected_provider_binding is not None
    assert report.selected_provider_binding["provider_track_id"] == "selected"
    assert report.best_alternative.canonical_track_id == "es_recording_alternative"
    assert report.best_alternative.item_id == "alternative"
    assert duplicate == report
    assert service.store.get_report("out_eval_01") is not None


def test_outcome_outside_attribution_window_is_rejected(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'window.db'}")
    save_trace(storage)
    trace = storage.get_decision_trace("dec_eval_01")
    assert trace is not None
    observed_at = datetime.fromisoformat(trace["created_at"]) + timedelta(hours=2)

    with pytest.raises(ValueError, match="outside the attribution window"):
        EvaluationService(storage).attribute_and_evaluate(
            outcome_id="out_late",
            decision_id="dec_eval_01",
            outcome="liked",
            observed_at=observed_at,
            attribution_window_seconds=3600,
        )


def test_evaluation_requires_historical_candidate_slate(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'missing-slate.db'}")
    storage.save_decision_trace(
        decision_id="dec_without_slate",
        user_id="user_01",
        context="commute",
        context_confidence=0.9,
        provider="apple_music",
        item_id="selected",
        factors={},
    )

    with pytest.raises(ValueError, match="candidate slate"):
        EvaluationService(storage).attribute_and_evaluate(
            outcome_id="out_01",
            decision_id="dec_without_slate",
            outcome="liked",
            observed_at=datetime.now(timezone.utc),
        )
