from datetime import datetime, timedelta, timezone

from echosense.cognitive_memory import MemoryRecord
from echosense.memory_lifecycle import LifecyclePolicy, MemoryLifecyclePlanner

NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def memory(
    memory_id: str,
    *,
    memory_type: str = "episodic",
    confidence: float = 0.8,
    status: str = "active",
    object_value: str = "calm music",
    provenance_ref: str | None = None,
    age_days: int = 120,
) -> MemoryRecord:
    observed = NOW - timedelta(days=age_days)
    return MemoryRecord(
        memory_id=memory_id,
        user_id="user_1",
        memory_type=memory_type,  # type: ignore[arg-type]
        subject="user_1",
        predicate="prefers",
        object=object_value,
        context="rainy_commute",
        confidence=confidence,
        provenance_type="outcome",
        provenance_ref=provenance_ref or f"outcome_{memory_id}",
        observed_at=observed,
        created_at=observed,
        expires_at=None,
        supersedes_memory_id=None,
        status=status,  # type: ignore[arg-type]
    )


def test_repeated_evidence_produces_stable_consolidation() -> None:
    planner = MemoryLifecyclePlanner()
    memories = [memory("m3"), memory("m1"), memory("m2")]

    first = planner.plan(memories, now=NOW)
    second = planner.plan(reversed(memories), now=NOW)

    assert first == second
    assert len(first.consolidations) == 1
    candidate = first.consolidations[0]
    assert candidate.source_memory_ids == ("m1", "m2", "m3")
    assert candidate.consolidation_key.startswith("con_")
    assert 0.0 <= candidate.confidence <= 0.95
    assert set(candidate.source_memory_ids) <= set(first.protected_memory_ids)


def test_duplicate_provenance_does_not_consolidate() -> None:
    planner = MemoryLifecyclePlanner()
    memories = [
        memory("m1", provenance_ref="same"),
        memory("m2", provenance_ref="same"),
        memory("m3", provenance_ref="same"),
    ]

    plan = planner.plan(memories, now=NOW)

    assert plan.consolidations == ()


def test_weak_stale_memory_is_forgotten_but_recent_memory_is_protected() -> None:
    planner = MemoryLifecyclePlanner(LifecyclePolicy(retention_days=90))
    weak_old = memory("weak_old", confidence=0.2, age_days=120)
    weak_recent = memory("weak_recent", confidence=0.2, age_days=10)

    plan = planner.plan([weak_old, weak_recent], now=NOW)

    assert [item.memory_id for item in plan.forgetting] == ["weak_old"]
    assert "weak_recent" in plan.protected_memory_ids


def test_explicit_protection_prevents_forgetting() -> None:
    planner = MemoryLifecyclePlanner()
    weak_old = memory("cited_memory", confidence=0.1, age_days=365)

    plan = planner.plan([weak_old], now=NOW, protected_memory_ids=["cited_memory"])

    assert plan.forgetting == ()
    assert plan.protected_memory_ids == ("cited_memory",)


def test_working_memory_is_never_selected_for_lifecycle_forgetting() -> None:
    planner = MemoryLifecyclePlanner()
    working = memory("working", memory_type="working", confidence=0.0, age_days=365)

    plan = planner.plan([working], now=NOW)

    assert plan.forgetting == ()
