from datetime import UTC, datetime, timedelta

from echosense.providers.models import Track
from echosense.storage import Storage
from echosense.temporal_mood import TemporalMoodLearningService


def service(tmp_path) -> tuple[Storage, TemporalMoodLearningService]:
    storage = Storage(f"sqlite:///{tmp_path / 'temporal.db'}")
    return storage, TemporalMoodLearningService(storage)


def trace(
    *,
    mood: str = "romantic",
    daypart: str = "evening",
    item_id: str = "track-1",
) -> dict[str, object]:
    return {
        "item_id": item_id,
        "factors": {
            "temporal_mood": {
                "mood": mood,
                "daypart": daypart,
                "source": "synthetic test evidence",
                "confidence": 0.8,
                "recording_key": f"spotify:{item_id}",
            }
        },
    }


def test_pattern_requires_three_positive_events_across_two_days(tmp_path) -> None:
    _, learning = service(tmp_path)
    now = datetime(2026, 7, 26, 20, tzinfo=UTC)

    for index, days_ago in enumerate((2, 1), start=1):
        assert learning.record(
            outcome_id=f"out-{index}",
            user_id="listener",
            signal="completed",
            trace=trace(item_id=f"track-{index}"),
            completion_ratio=0.8,
            observed_at=now - timedelta(days=days_ago),
        )

    learning_profile = learning.profile(user_id="listener", daypart="evening", now=now)
    assert learning_profile.pattern_type == "learning"
    assert learning_profile.mood is None

    assert learning.record(
        outcome_id="out-3",
        user_id="listener",
        signal="liked",
        trace=trace(item_id="track-3"),
        observed_at=now,
    )
    profile = learning.profile(user_id="listener", daypart="evening", now=now)
    assert profile.pattern_type == "stable_pattern"
    assert profile.mood == "romantic"
    assert profile.evidence_count == 3
    assert profile.distinct_days == 3
    assert "often choose romantic music" in profile.explanation


def test_single_track_and_short_completion_do_not_infer_pattern(tmp_path) -> None:
    _, learning = service(tmp_path)
    now = datetime(2026, 7, 26, 8, tzinfo=UTC)

    assert not learning.record(
        outcome_id="short",
        user_id="listener",
        signal="completed",
        trace=trace(mood="melancholy", daypart="morning"),
        completion_ratio=0.59,
        observed_at=now,
    )
    assert learning.record(
        outcome_id="one",
        user_id="listener",
        signal="saved",
        trace=trace(mood="melancholy", daypart="morning"),
        observed_at=now,
    )

    profile = learning.profile(user_id="listener", daypart="morning", now=now)
    assert profile.pattern_type == "learning"
    assert profile.mood is None
    assert "Still learning" in profile.explanation


def test_daypart_patterns_are_isolated_and_outcomes_are_idempotent(tmp_path) -> None:
    _, learning = service(tmp_path)
    now = datetime(2026, 7, 26, 20, tzinfo=UTC)
    for index in range(3):
        kwargs = {
            "outcome_id": f"evening-{index}",
            "user_id": "listener",
            "signal": "saved",
            "trace": trace(daypart="evening", item_id=f"track-{index}"),
            "observed_at": now - timedelta(days=index),
        }
        assert learning.record(**kwargs)
        assert not learning.record(**kwargs)

    assert learning.profile(user_id="listener", daypart="evening", now=now).mood == "romantic"
    assert learning.profile(user_id="listener", daypart="morning", now=now).mood is None


def test_recent_shift_is_bounded_to_three_of_last_five(tmp_path) -> None:
    _, learning = service(tmp_path)
    now = datetime(2026, 7, 26, 18, tzinfo=UTC)
    moods = ("melancholy", "melancholy", "melancholy", "uplifting", "uplifting")
    for index, mood in enumerate(moods):
        assert learning.record(
            outcome_id=f"shift-{index}",
            user_id="listener",
            signal="liked",
            trace=trace(mood=mood, item_id=f"track-{index}"),
            observed_at=now - timedelta(minutes=index),
        )

    profile = learning.profile(user_id="listener", daypart="evening", now=now)
    assert profile.mood == "melancholy"
    assert profile.pattern_type == "recent_shift"
    assert "recently shifted toward melancholy" in profile.explanation


def test_negative_feedback_and_decay_prevent_a_permanent_pattern(tmp_path) -> None:
    _, learning = service(tmp_path)
    now = datetime(2026, 7, 26, 20, tzinfo=UTC)
    for index in range(3):
        assert learning.record(
            outcome_id=f"positive-{index}",
            user_id="listener",
            signal="liked",
            trace=trace(item_id=f"track-{index}"),
            observed_at=now - timedelta(days=index),
        )
    for index in range(3):
        assert learning.record(
            outcome_id=f"negative-{index}",
            user_id="listener",
            signal="disliked",
            trace=trace(item_id=f"negative-track-{index}"),
            observed_at=now - timedelta(minutes=index),
        )

    suppressed = learning.profile(user_id="listener", daypart="evening", now=now)
    assert suppressed.mood is None
    assert suppressed.pattern_type == "learning"

    profile = learning.profile(
        user_id="listener",
        daypart="evening",
        now=now + timedelta(days=29),
    )
    assert profile.mood is None
    assert profile.pattern_type == "learning"


def test_correction_disable_and_reset_are_scoped(tmp_path) -> None:
    _, learning = service(tmp_path)
    now = datetime(2026, 7, 26, 20, tzinfo=UTC)
    for index in range(3):
        learning.record(
            outcome_id=f"out-{index}",
            user_id="listener",
            signal="saved",
            trace=trace(item_id=f"track-{index}"),
            observed_at=now - timedelta(days=index),
        )

    assert learning.correct(user_id="listener", daypart="evening", mood="romantic") == 3
    assert learning.profile(user_id="listener", daypart="evening", now=now).mood is None

    learning.set_enabled("listener", False)
    disabled = learning.profile(user_id="listener", daypart="evening", now=now)
    assert disabled.enabled is False
    learning.set_enabled("listener", True)
    assert learning.reset("listener") == 0


def test_mood_evidence_is_explainable_and_not_diagnostic(tmp_path) -> None:
    _, learning = service(tmp_path)
    romantic = Track("spotify", "1", "Love Story", ("Artist",), album="Heart")
    melancholy = Track("spotify", "2", "Blue Tears", ("Artist",))

    romantic_evidence = learning.infer_track(romantic)
    melancholy_evidence = learning.infer_track(melancholy)
    assert romantic_evidence is not None
    assert romantic_evidence.mood == "romantic"
    assert romantic_evidence.confidence < 0.5
    assert melancholy_evidence is not None
    assert melancholy_evidence.mood == "melancholy"
    assert "depress" not in melancholy_evidence.source
