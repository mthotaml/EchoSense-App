from datetime import datetime, timedelta, timezone
from pathlib import Path

from echosense.cognitive_memory import CognitiveMemoryStore
from echosense.storage import Storage
from echosense.understanding import ObservationEvidence, UnderstandingEngine


def make_store(tmp_path: Path) -> CognitiveMemoryStore:
    return CognitiveMemoryStore(Storage(f"sqlite:///{tmp_path / 'understanding.db'}"))


def test_understanding_cites_active_memory_and_separates_evidence(tmp_path: Path) -> None:
    memory = make_store(tmp_path)
    memory.remember(
        memory_id="mem-rain-01",
        user_id="user-01",
        memory_type="semantic",
        subject="user",
        predicate="prefers",
        object="calm music while driving in rain",
        context="rainy_commute",
        confidence=0.9,
        provenance_type="outcome",
        provenance_ref="outcome-01",
    )

    result = UnderstandingEngine(memory).understand(
        user_id="user-01",
        context="rainy_commute",
        context_confidence=0.8,
        observations=[
            ObservationEvidence("weather", "rain", 0.9),
            ObservationEvidence("activity", "driving", 0.8),
        ],
        action_type="recommend",
        target_ref="apple_music:track-01",
    )

    assert [item.key for item in result.observations] == ["activity", "weather"]
    assert [item.memory_id for item in result.memories] == ["mem-rain-01"]
    assert result.inferences[0].memory_ids == ("mem-rain-01",)
    assert result.inferences[0].observation_keys == ("activity", "weather")
    assert 0.0 <= result.inferences[0].confidence <= 1.0
    assert result.action.confidence <= 0.8
    trace = result.as_trace_factor()
    assert set(trace) == {"observations", "memories", "inferences", "action"}


def test_understanding_does_not_use_cross_user_memory(tmp_path: Path) -> None:
    memory = make_store(tmp_path)
    memory.remember(
        memory_id="mem-other",
        user_id="other-user",
        memory_type="semantic",
        subject="user",
        predicate="prefers",
        object="jazz",
        context="general_listening",
        confidence=1.0,
        provenance_type="explicit",
        provenance_ref="profile",
    )

    result = UnderstandingEngine(memory).understand(
        user_id="user-01",
        context="general_listening",
        context_confidence=0.7,
        observations=[ObservationEvidence("time", "afternoon", 0.7)],
        action_type="recommend",
        target_ref="provider:item",
    )

    assert result.memories == ()
    assert result.inferences[0].memory_ids == ()


def test_understanding_ignores_superseded_semantic_memory(tmp_path: Path) -> None:
    memory = make_store(tmp_path)
    memory.remember(
        memory_id="mem-old",
        user_id="user-01",
        memory_type="semantic",
        subject="user",
        predicate="preferred_energy",
        object="high",
        context="commute",
        confidence=0.8,
        provenance_type="explicit",
        provenance_ref="profile-v1",
    )
    memory.remember(
        memory_id="mem-new",
        user_id="user-01",
        memory_type="semantic",
        subject="user",
        predicate="preferred_energy",
        object="low",
        context="commute",
        confidence=0.9,
        provenance_type="explicit",
        provenance_ref="profile-v2",
    )

    result = UnderstandingEngine(memory).understand(
        user_id="user-01",
        context="commute",
        context_confidence=0.8,
        observations=[ObservationEvidence("activity", "driving", 0.8)],
        action_type="recommend",
        target_ref="provider:item",
    )

    assert [item.memory_id for item in result.memories] == ["mem-new"]
    assert result.inferences[0].memory_ids == ("mem-new",)


def test_understanding_ignores_expired_working_memory(tmp_path: Path) -> None:
    memory = make_store(tmp_path)
    now = datetime.now(timezone.utc)
    memory.remember(
        memory_id="mem-working",
        user_id="user-01",
        memory_type="working",
        subject="session",
        predicate="mood",
        object="focused",
        context="general_listening",
        confidence=0.9,
        provenance_type="signal",
        provenance_ref="signal-01",
        expires_at=now + timedelta(seconds=1),
    )

    result = UnderstandingEngine(memory).understand(
        user_id="user-01",
        context="general_listening",
        context_confidence=0.9,
        observations=[ObservationEvidence("time", "morning", 0.9)],
        action_type="recommend",
        target_ref="provider:item",
    )
    assert result.memories

    memory.expire_working_memories(now=now + timedelta(seconds=2))
    result_after_expiry = UnderstandingEngine(memory).understand(
        user_id="user-01",
        context="general_listening",
        context_confidence=0.9,
        observations=[ObservationEvidence("time", "morning", 0.9)],
        action_type="recommend",
        target_ref="provider:item",
    )
    assert result_after_expiry.memories == ()


def test_confidence_is_bounded_for_untrusted_inputs(tmp_path: Path) -> None:
    memory = make_store(tmp_path)
    result = UnderstandingEngine(memory).understand(
        user_id="user-01",
        context="general_listening",
        context_confidence=3.0,
        observations=[ObservationEvidence("time", "night", -2.0)],
        action_type="recommend",
        target_ref="provider:item",
    )

    assert result.observations[0].confidence == 0.0
    assert 0.0 <= result.inferences[0].confidence <= 1.0
    assert 0.0 <= result.action.confidence <= 1.0
