from pathlib import Path

import pytest

from echosense.deletion import DeletionCoordinator
from echosense.memory import InMemoryPreferenceMemory
from echosense.storage import Storage


class FailOnceMemory(InMemoryPreferenceMemory):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    def delete_user(self, user_id: str) -> dict[str, int]:
        if not self.failed:
            self.failed = True
            raise RuntimeError("temporary graph outage")
        return super().delete_user(user_id)


def test_retry_resumes_original_deletion_request(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'retry.db'}")
    storage.upsert_consent("user-retry", "contextual_recommendation", "2026-07-20")
    memory = FailOnceMemory()
    coordinator = DeletionCoordinator(storage, memory)

    with pytest.raises(RuntimeError, match="temporary graph outage"):
        coordinator.delete_user("user-retry", "contextual_recommendation")

    with storage.connect() as connection:
        row = storage._execute(
            connection,
            "SELECT deletion_id, status, user_id FROM deletion_requests",
        ).fetchone()
    request = dict(row)
    assert request["status"] == "retry_required"
    assert request["user_id"] == "user-retry"

    result = coordinator.retry_request(request["deletion_id"])

    assert result.deletion_id == request["deletion_id"]
    assert result.status == "completed"
    assert storage.has_active_consent("user-retry", "contextual_recommendation") is False
    status = coordinator.get_request(request["deletion_id"])
    assert status is not None
    assert status["status"] == "completed"


def test_retry_pending_processes_only_retry_required_requests(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'pending.db'}")
    memory = FailOnceMemory()
    coordinator = DeletionCoordinator(storage, memory)
    storage.upsert_consent("user-pending", "contextual_recommendation", "2026-07-20")

    with pytest.raises(RuntimeError):
        coordinator.delete_user("user-pending", "contextual_recommendation")

    results = coordinator.retry_pending(limit=10)

    assert len(results) == 1
    assert results[0].status == "completed"
    assert coordinator.retry_pending(limit=10) == []
