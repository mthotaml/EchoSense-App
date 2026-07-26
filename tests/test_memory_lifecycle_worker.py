from pathlib import Path

from echosense.cognitive_memory import CognitiveMemoryStore
from echosense.memory_lifecycle_worker import build_parser, run_once
from echosense.storage import Storage


def test_worker_parser_defaults_to_dry_run() -> None:
    args = build_parser().parse_args(["user_1"])

    assert args.user_id == "user_1"
    assert args.mode == "dry_run"
    assert args.run_id is None
    assert args.protected_memory_ids == []


def test_worker_run_once_is_idempotent_for_explicit_run_id(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'worker.db'}")
    memory_store = CognitiveMemoryStore(storage)
    for index in range(3):
        memory_store.remember(
            memory_id=f"mem_{index}",
            user_id="user_1",
            memory_type="episodic",
            subject="user_1",
            predicate="prefers",
            object="calm music",
            context="rainy_commute",
            confidence=0.8,
            provenance_type="outcome",
            provenance_ref=f"outcome_{index}",
        )

    first = run_once(
        user_id="user_1",
        mode="apply",
        run_id="run_worker_1",
        storage=storage,
    )
    second = run_once(
        user_id="user_1",
        mode="apply",
        run_id="run_worker_1",
        storage=storage,
    )

    assert first == second
    assert first["status"] == "completed"
    assert len(first["consolidated_memory_ids"]) == 1


def test_worker_passes_protected_memory_ids(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'protected.db'}")
    result = run_once(
        user_id="user_1",
        run_id="run_protected",
        protected_memory_ids=("mem_a", "mem_a", "mem_b"),
        storage=storage,
    )

    assert result["plan"]["protected_memory_ids"] == ("mem_a", "mem_b")
