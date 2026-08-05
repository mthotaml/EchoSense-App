from datetime import datetime, timezone

import pytest

from echosense.evaluation import (
    AttributedOutcome,
    evaluate_counterfactual,
    normalize_reward,
    snapshot_candidates,
)


def test_reward_normalization_uses_bounded_behavioral_evidence() -> None:
    assert normalize_reward("liked") == 1.0
    assert normalize_reward("completed", completion_ratio=0.95) == 0.95
    assert normalize_reward("skipped", completion_ratio=0.5) == -0.15
    with pytest.raises(ValueError):
        normalize_reward("completed", completion_ratio=1.2)


def test_counterfactual_report_is_read_only_and_deterministic() -> None:
    slate = snapshot_candidates(
        [
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
                "provider_base_score": 0.8,
                "preference_weight": 0.1,
                "ranking_score": 0.825,
            },
            {
                "provider": "apple_music",
                "item_id": "alternative",
                "canonical_track_id": "es_recording_alternative",
                "provider_base_score": 0.79,
                "preference_weight": 0.3,
                "ranking_score": 0.865,
            },
            {
                "provider": "apple_music",
                "item_id": "third",
                "canonical_track_id": "es_recording_third",
                "provider_base_score": 0.7,
                "preference_weight": 0.0,
                "ranking_score": 0.7,
            },
        ],
        selected_item_id="es_recording_selected",
    )
    outcome = AttributedOutcome(
        outcome_id="out_01",
        decision_id="dec_01",
        outcome="skipped",
        reward=normalize_reward("skipped", playback_seconds=20, completion_ratio=0.1),
        observed_at=datetime.now(timezone.utc),
        playback_seconds=20,
        completion_ratio=0.1,
    )

    report = evaluate_counterfactual(decision_id="dec_01", outcome=outcome, candidates=slate)

    assert report.selected_canonical_track_id == "es_recording_selected"
    assert report.selected_item_id == "selected"
    assert report.selected_provider_binding is not None
    assert report.selected_provider_binding["provider_track_id"] == "selected"
    assert report.best_alternative is not None
    assert report.best_alternative.canonical_track_id == "es_recording_alternative"
    assert report.best_alternative.item_id == "alternative"
    assert report.best_alternative.estimated_lift == 0.04
    assert report.estimated_regret == 0.04
    assert report.confidence == "medium"


def test_slate_requires_exactly_one_selected_candidate() -> None:
    with pytest.raises(ValueError):
        snapshot_candidates(
            [
                {
                    "provider": "apple_music",
                    "item_id": "one",
                    "canonical_track_id": "es_recording_one",
                    "provider_base_score": 0.8,
                    "ranking_score": 0.8,
                }
            ],
            selected_item_id="es_recording_missing",
        )


def test_snapshot_selection_is_provider_neutral_when_bindings_differ() -> None:
    slate = snapshot_candidates(
        [
            {
                "provider": "spotify",
                "item_id": "spotify-track-1",
                "canonical_track_id": "es_recording_shared",
                "provider_binding": {
                    "provider": "spotify",
                    "provider_track_id": "spotify-track-1",
                    "canonical_track_id": "es_recording_shared",
                    "playable": True,
                    "uri": "spotify:track:spotify-track-1",
                    "external_url": None,
                },
                "provider_base_score": 0.9,
                "ranking_score": 0.9,
            },
            {
                "provider": "apple_music",
                "item_id": "apple-song-1",
                "canonical_track_id": "es_recording_other",
                "provider_base_score": 0.8,
                "ranking_score": 0.8,
            },
        ],
        selected_item_id="es_recording_shared",
    )

    assert slate[0].selected is True
    assert slate[0].provider == "spotify"
    assert slate[0].item_id == "spotify-track-1"
    assert slate[0].canonical_track_id == "es_recording_shared"
    assert slate[0].provider_binding is not None
    assert slate[0].provider_binding["provider"] == "spotify"
