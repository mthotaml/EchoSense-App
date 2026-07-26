from echosense.playback_learning import PlaybackLearningService
from echosense.providers.models import Track
from echosense.storage import Storage


def save_decision(storage: Storage, decision_id: str, item_id: str = "track-a") -> None:
    storage.save_decision_trace(
        decision_id=decision_id,
        user_id="user-1",
        context="general_listening",
        context_confidence=0.8,
        provider="spotify",
        item_id=item_id,
        factors={"candidate_slate": []},
    )


def test_feedback_is_idempotent_and_reorders_the_next_recommendation(tmp_path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'learning.db'}")
    service = PlaybackLearningService(storage)
    tracks = [
        Track("spotify", "track-a", "A", ("Artist A",)),
        Track("spotify", "track-b", "B", ("Artist B",)),
    ]
    selected, _ = service.rank(
        user_id="user-1",
        provider="spotify",
        context="general_listening",
        tracks=tracks,
    )
    assert selected == tracks[0]

    save_decision(storage, "decision-1")
    first = service.record(
        outcome_id="outcome-1",
        user_id="user-1",
        decision_id="decision-1",
        signal="disliked",
    )
    duplicate = service.record(
        outcome_id="outcome-1",
        user_id="user-1",
        decision_id="decision-1",
        signal="disliked",
    )
    service.record(
        outcome_id="outcome-2",
        user_id="user-1",
        decision_id="decision-1",
        signal="disliked",
    )
    selected, slate = service.rank(
        user_id="user-1",
        provider="spotify",
        context="general_listening",
        tracks=tracks,
    )

    assert first.applied is True
    assert duplicate.applied is False
    assert duplicate.weight == first.weight
    assert selected == tracks[1]
    assert slate[0]["item_id"] == "track-b"
    assert slate[1]["preference_weight"] == -0.3


def test_completion_and_rating_strength_are_bounded(tmp_path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'signals.db'}")
    service = PlaybackLearningService(storage)
    save_decision(storage, "decision-1")

    completion = service.record(
        outcome_id="completion",
        user_id="user-1",
        decision_id="decision-1",
        signal="completed",
        completion_ratio=0.5,
        playback_seconds=120,
    )
    rating = service.record(
        outcome_id="rating",
        user_id="user-1",
        decision_id="decision-1",
        signal="rated",
        rating=5,
    )

    assert completion.delta == 0.04
    assert rating.delta == 0.12
    assert rating.weight == 0.16
    assert rating.evidence_count == 2
