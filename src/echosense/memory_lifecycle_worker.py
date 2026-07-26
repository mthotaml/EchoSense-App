from __future__ import annotations

import argparse
import os
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from echosense.memory_lifecycle_service import MemoryLifecycleService
from echosense.storage import Storage


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run EchoSense cognitive memory lifecycle")
    parser.add_argument("user_id")
    parser.add_argument("--mode", choices=("dry_run", "apply"), default="dry_run")
    parser.add_argument("--run-id")
    parser.add_argument(
        "--protected-memory-id",
        action="append",
        default=[],
        dest="protected_memory_ids",
    )
    return parser


def run_once(
    *,
    user_id: str,
    mode: str = "dry_run",
    run_id: str | None = None,
    protected_memory_ids: tuple[str, ...] = (),
    storage: Storage | None = None,
) -> dict[str, object]:
    generated_run_id = (
        f"lifecycle_{utc_now().strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:12]}"
    )
    resolved_run_id = run_id or generated_run_id
    service = MemoryLifecycleService(storage or Storage())
    result = service.execute(
        run_id=resolved_run_id,
        user_id=user_id,
        mode=mode,
        protected_memory_ids=protected_memory_ids,
    )
    return {
        "run_id": result.run_id,
        "user_id": result.user_id,
        "mode": result.mode,
        "status": result.status,
        "consolidated_memory_ids": list(result.consolidated_memory_ids),
        "forgotten_memory_ids": list(result.forgotten_memory_ids),
        "plan": asdict(result.plan),
        "created_at": result.created_at.isoformat(),
    }


def main() -> None:
    args = build_parser().parse_args()
    result = run_once(
        user_id=args.user_id,
        mode=args.mode,
        run_id=args.run_id,
        protected_memory_ids=tuple(sorted(set(args.protected_memory_ids))),
    )
    if os.getenv("ECHOSENSE_WORKER_QUIET", "0") != "1":
        import json

        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
