from __future__ import annotations

import argparse
import json

from echosense.deletion import DeletionCoordinator
from echosense.memory import memory_from_environment
from echosense.storage import Storage


def run(limit: int = 100) -> list[dict[str, object]]:
    coordinator = DeletionCoordinator(Storage(), memory_from_environment())
    return [result.__dict__ for result in coordinator.retry_pending(limit=limit)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry incomplete EchoSense deletion requests")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(run(limit=args.limit), separators=(",", ":")))


if __name__ == "__main__":
    main()
