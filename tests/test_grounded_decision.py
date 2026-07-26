from datetime import datetime, timedelta, timezone
from pathlib import Path

from echosense.cognitive_memory import CognitiveMemoryStore
from echosense.grounded_decision import GroundedDecisionService, SelectedAction
from echosense.storage import Storage
from echosense.understanding import ObservationEvidence, UnderstandingEngine


def build_service(tmp_path: Path) -> tuple[Storage, CognitiveMemoryStore, GroundedDecisionService]:
    storage = Storage(f"sqlite:///{tmp_path / 'grounded.db'}")
    memories = CognitiveMemoryStore(storage)
    service = GroundedDecisionService(storage, UnderstandingEngine(memories))
    return storage, memories, service


def test_grounded_decision_cites_active_memory_and_persists_explanation(tmp_path: Path) -> None:
    storage, memories, service = build_service(tmp_path)
    memories.remember(
        memory_id="mem-rain-focus",
        user_id="user-1",
        memory_type="semantic",
        subject="user-1",
        predicate="prefers",
        object="instrumental music in rain",
        context="rainy_commute",
        confidence=0.9,
        provenance_type="outcome_summary",
        provenance_ref="outcome-1",
    )

    decision = service.finalize(
        decision_id="dec-grounded-1",
        user_id="user-1",
        context="rainy_commute",
        context_confidence=0.8,
        observations=(
            ObservationEvidence("activity", "driving", 0.9),
            ObservationEvidence("weather", "rain", 0.8),
        ),
        action=SelectedAction("apple_music", "track-1", "a calm instrumental mix"),
        factors={"ranking_score": 0.82},
        preference_applied=True,
    )

    assert decision.explanation.memory_ids == ("mem-rain-focus",)
    assert decision.explanation.confidence <= 0.8
    assert "remembered fact" in decision.explanation.text
    assert "learned preference" in decision.explanation.text

    trace = storage.get_decision_trace("dec-grounded-1")
    assert trace is not None
    understanding = trace["factors"]["understanding"]
    explanation = trace["factors"]["grounded_explanation"]
    assert understanding["memories"][0]["memory_id"] == "mem-rain-focus"
    assert explanation["memory_ids"] == ["mem-rain-focus"]
    assert explanation["confidence"] == decision.explanation.confidence


def test_grounded_decision_ignores_expired_and_cross_user_memory(tmp_path: Path) -> None:
    _, memories, service = build_service(tmp_path)
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    memories.remember(
        memory_id="mem-working",
        user_id="user-1",
        memory_type="working",
        subject="session",
        predicate="mood",
        object="focused",
        context="commute",
        confidence=1.0,
        provenance_type="signal",
        provenance_ref="signal-1",
        expires_at=future,
    )
    memories.remember(
        memory_id="mem-other-user",
        user_id="user-2",
        memory_type="semantic",
        subject="user-2",
        predicate="prefers",
        object="jazz",
        context="commute",
        confidence=1.0,
        provenance_type="outcome_summary",
        provenance_ref="outcome-2",
    )
    memories.expire_working_memories(now=future + timedelta(seconds=1))

    decision = service.finalize(
        decision_id="dec-grounded-2",
        user_id="user-1",
        context="commute",
        context_confidence=0.7,
        observations=(ObservationEvidence("activity", "driving", 0.7),),
        action=SelectedAction("fixture", "track-2", "a commute playlist"),
    )

    assert decision.explanation.memory_ids == ()
    assert "remembered fact" not in decision.explanation.text
    assert decision.understanding.memories == ()


def test_grounded_decision_uses_only_latest_semantic_memory(tmp_path: Path) -> None:
    _, memories, service = build_service(tmp_path)
    memories.remember(
        memory_id="mem-old",
        user_id="user-1",
        memory_type="semantic",
        subject="user-1",
        predicate="prefers",
        object="rock",
        context="evening_wind_down",
        confidence=0.8,
        provenance_type="outcome_summary",
        provenance_ref="old",
    )
    memories.remember(
        memory_id="mem-new",
        user_id="user-1",
        memory_type="semantic",
        subject="user-1",
        predicate="prefers",
        object="ambient",
        context="evening_wind_down",
        confidence=0.9,
        provenance_type="outcome_summary",
        provenance_ref="new",
    )

    decision = service.finalize(
        decision_id="dec-grounded-3",
        user_id="user-1",
        context="evening_wind_down",
        context_confidence=0.9,
        observations=(ObservationEvidence("time", "evening", 0.9),),
        action=SelectedAction("fixture", "track-3", "an ambient set"),
    )

    assert decision.explanation.memory_ids == ("mem-new",)
    assert all(item.memory_id != "mem-old" for item in decision.understanding.memories)
