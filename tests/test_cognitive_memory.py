from datetime import timedelta
from pathlib import Path

import pytest

from echosense.cognitive_memory import CognitiveMemoryStore, utc_now
from echosense.storage import Storage


@pytest.fixture()
def memory(tmp_path: Path) -> CognitiveMemoryStore:
    return CognitiveMemoryStore(Storage(f"sqlite:///{tmp_path / 'memory.db'}"))


def test_semantic_conflict_is_superseded_not_overwritten(memory: CognitiveMemoryStore) -> None:
    first = memory.remember(
        memory_id="mem-1",
        user_id="u1",
        memory_type="semantic",
        subject="user",
        predicate="preferred_temperature",
        object="68F",
        context="home",
        confidence=0.7,
        provenance_type="explicit_statement",
        provenance_ref="signal-1",
    )
    second = memory.remember(
        memory_id="mem-2",
        user_id="u1",
        memory_type="semantic",
        subject="user",
        predicate="preferred_temperature",
        object="70F",
        context="home",
        confidence=0.9,
        provenance_type="explicit_statement",
        provenance_ref="signal-2",
    )

    assert memory.get(first.memory_id).status == "superseded"  # type: ignore[union-attr]
    assert second.supersedes_memory_id == first.memory_id
    results = memory.retrieve(user_id="u1", query="preferred temperature home")
    assert [item.memory.memory_id for item in results] == ["mem-2"]


def test_same_semantic_fact_is_idempotent(memory: CognitiveMemoryStore) -> None:
    first = memory.remember(
        memory_id="mem-1",
        user_id="u1",
        memory_type="semantic",
        subject="commute",
        predicate="usual_mode",
        object="train",
        context="weekday",
        confidence=0.8,
        provenance_type="observation",
        provenance_ref="obs-1",
    )
    duplicate_fact = memory.remember(
        memory_id="mem-2",
        user_id="u1",
        memory_type="semantic",
        subject="commute",
        predicate="usual_mode",
        object="train",
        context="weekday",
        confidence=0.9,
        provenance_type="observation",
        provenance_ref="obs-2",
    )
    assert duplicate_fact.memory_id == first.memory_id


def test_memory_id_cannot_be_reused_for_different_content(memory: CognitiveMemoryStore) -> None:
    memory.remember(
        memory_id="mem-1",
        user_id="u1",
        memory_type="episodic",
        subject="drive",
        predicate="weather",
        object="rain",
        context="commute",
        confidence=0.8,
        provenance_type="sensor",
        provenance_ref="weather-1",
    )
    with pytest.raises(ValueError, match="different content"):
        memory.remember(
            memory_id="mem-1",
            user_id="u1",
            memory_type="episodic",
            subject="drive",
            predicate="weather",
            object="sun",
            context="commute",
            confidence=0.8,
            provenance_type="sensor",
            provenance_ref="weather-2",
        )


def test_working_memory_expires_and_is_not_retrieved(memory: CognitiveMemoryStore) -> None:
    now = utc_now()
    memory.remember(
        memory_id="working-1",
        user_id="u1",
        memory_type="working",
        subject="current_task",
        predicate="goal",
        object="choose a playlist",
        context="session",
        confidence=1.0,
        provenance_type="reasoning",
        provenance_ref="trace-1",
        expires_at=now + timedelta(minutes=5),
    )
    assert memory.retrieve(user_id="u1", query="choose playlist", now=now)
    assert (
        memory.retrieve(user_id="u1", query="choose playlist", now=now + timedelta(minutes=6)) == []
    )
    assert memory.expire_working_memories(now + timedelta(minutes=6)) == 1
    assert memory.get("working-1").status == "expired"  # type: ignore[union-attr]


def test_retrieval_is_user_scoped_bounded_and_relevance_ranked(
    memory: CognitiveMemoryStore,
) -> None:
    for index, value in enumerate(("rainy commute", "evening cooking", "morning workout")):
        memory.remember(
            memory_id=f"mem-{index}",
            user_id="u1",
            memory_type="episodic",
            subject=value,
            predicate="activity",
            object=value,
            context="daily",
            confidence=0.8,
            provenance_type="observation",
            provenance_ref=f"obs-{index}",
        )
    memory.remember(
        memory_id="other-user",
        user_id="u2",
        memory_type="episodic",
        subject="rainy commute",
        predicate="activity",
        object="rainy commute",
        context="daily",
        confidence=1.0,
        provenance_type="observation",
        provenance_ref="obs-other",
    )

    results = memory.retrieve(user_id="u1", query="rainy commute", limit=2)
    assert len(results) == 2
    assert results[0].memory.memory_id == "mem-0"
    assert all(item.memory.user_id == "u1" for item in results)


def test_delete_user_removes_active_and_historical_memory(memory: CognitiveMemoryStore) -> None:
    for memory_id, value in (("mem-1", "old"), ("mem-2", "new")):
        memory.remember(
            memory_id=memory_id,
            user_id="u1",
            memory_type="semantic",
            subject="preference",
            predicate="value",
            object=value,
            context="general",
            confidence=0.8,
            provenance_type="explicit_statement",
            provenance_ref=memory_id,
        )
    assert memory.delete_user("u1") == 2
    assert memory.get("mem-1") is None
    assert memory.get("mem-2") is None
