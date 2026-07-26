from datetime import datetime, timedelta, timezone
from pathlib import Path

from echosense.cognitive_memory import CognitiveMemoryStore
from echosense.memory_lifecycle import LifecyclePolicy, MemoryLifecyclePlanner
from echosense.memory_lifecycle_service import MemoryLifecycleService
from echosense.storage import Storage


def remember_episode(store: CognitiveMemoryStore, memory_id: str, provenance: str) -> None:
    store.remember(
        memory_id=memory_id,
        user_id="user_1",
        memory_type="episodic",
        subject="user_1",
        predicate="prefers",
        object="calm music",
        context="rainy_commute",
        confidence=0.8,
        provenance_type="outcome",
        provenance_ref=provenance,
    )


def test_dry_run_is_deterministic_and_non_mutating(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'dry.db'}")
    memory_store = CognitiveMemoryStore(storage)
    for index in range(3):
        remember_episode(memory_store, f"mem_{index}", f"outcome_{index}")
    service = MemoryLifecycleService(storage, memory_store)

    first = service.execute(run_id="run_dry", user_id="user_1", mode="dry_run")
    second = service.execute(run_id="run_dry", user_id="user_1", mode="dry_run")

    assert first == second
    assert len(first.plan.consolidations) == 1
    assert first.consolidated_memory_ids == ()
    semantic_id = f"mem_{first.plan.consolidations[0].consolidation_key}"
    assert memory_store.get(semantic_id) is None


def test_apply_creates_one_semantic_memory_and_is_idempotent(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'apply.db'}")
    memory_store = CognitiveMemoryStore(storage)
    for index in range(3):
        remember_episode(memory_store, f"mem_{index}", f"outcome_{index}")
    service = MemoryLifecycleService(storage, memory_store)

    first = service.execute(run_id="run_apply", user_id="user_1", mode="apply")
    second = service.execute(run_id="run_apply", user_id="user_1", mode="apply")

    assert first == second
    assert len(first.consolidated_memory_ids) == 1
    consolidated = memory_store.get(first.consolidated_memory_ids[0])
    assert consolidated is not None
    assert consolidated.memory_type == "semantic"
    assert consolidated.provenance_type == "consolidation"
    assert all(memory_id in consolidated.provenance_ref for memory_id in ("mem_0", "mem_1", "mem_2"))


def test_apply_forgets_only_stale_weak_unprotected_memory(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'forget.db'}")
    memory_store = CognitiveMemoryStore(storage)
    old = datetime.now(timezone.utc) - timedelta(days=200)
    memory_store.remember(
        memory_id="mem_weak",
        user_id="user_1",
        memory_type="episodic",
        subject="user_1",
        predicate="liked",
        object="old item",
        context="general",
        confidence=0.1,
        provenance_type="outcome",
        provenance_ref="old",
        observed_at=old,
    )
    with storage.connect() as connection:
        storage._execute(
            connection,
            "UPDATE cognitive_memories SET created_at = %s WHERE memory_id = %s",
            (old.isoformat(), "mem_weak"),
        )
    service = MemoryLifecycleService(
        storage,
        memory_store,
        MemoryLifecyclePlanner(LifecyclePolicy(retention_days=90)),
    )

    result = service.execute(run_id="run_forget", user_id="user_1", mode="apply")

    assert result.forgotten_memory_ids == ("mem_weak",)
    assert memory_store.get("mem_weak") is None


def test_delete_user_removes_lifecycle_audit(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'delete.db'}")
    service = MemoryLifecycleService(storage)
    service.execute(run_id="run_delete", user_id="user_1", mode="dry_run")

    assert service.delete_user("user_1") == 1
    assert service.get("run_delete") is None
