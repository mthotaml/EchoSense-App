from echosense.listening_intelligence import ListeningIntelligenceService
from echosense.playback_learning import PlaybackLearningService
from echosense.storage import Storage


def _decision(storage: Storage, decision_id: str, item_id: str, title: str, moment: str) -> None:
    storage.save_decision_trace(
        decision_id=decision_id,
        user_id="listener",
        context=moment,
        context_confidence=0.8,
        provider="spotify",
        item_id=item_id,
        factors={
            "track_snapshot": {"title": title, "artist": "Echo Artist"},
            "listening_moment": moment,
            "recommendation_score": 88,
            "context_statement": f"Selected for {moment}.",
        },
    )


def test_listening_intelligence_aggregates_truthful_persisted_outcomes(tmp_path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'intelligence.db'}")
    _decision(storage, "decision-complete", "track-one", "Open Road", "driving")
    _decision(storage, "decision-skip", "track-two", "Quiet Desk", "working")
    learning = PlaybackLearningService(storage)
    learning.record(
        outcome_id="outcome-complete",
        user_id="listener",
        decision_id="decision-complete",
        signal="completed",
        completion_ratio=0.95,
        playback_seconds=180,
    )
    learning.record(
        outcome_id="outcome-skip",
        user_id="listener",
        decision_id="decision-skip",
        signal="skipped",
        completion_ratio=0.1,
        playback_seconds=12,
    )

    snapshot = ListeningIntelligenceService(storage).snapshot("listener")

    assert snapshot["data_status"] == "ready"
    assert snapshot["summary"] == {
        "total_listen_seconds": 192.0,
        "tracks_observed": 2,
        "completed": 1,
        "skipped": 1,
        "saved": 0,
        "loved": 0,
        "disliked": 0,
        "early_skips": 1,
        "completion_rate": 50,
        "recommendation_acceptance_rate": 50,
        "recommendations_with_outcomes": 2,
    }
    assert snapshot["history"][0]["title"] == "Quiet Desk"
    assert snapshot["history"][1]["provider_track_id"] == "track-one"
    assert {item["moment"] for item in snapshot["moments"]} == {"driving", "working"}


def test_listening_intelligence_has_honest_empty_state(tmp_path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'empty.db'}")

    snapshot = ListeningIntelligenceService(storage).snapshot("new-listener")

    assert snapshot["data_status"] == "learning"
    assert snapshot["history"] == []
    assert snapshot["summary"]["completion_rate"] is None
    assert snapshot["capabilities"]["verified_deletion"] is False
