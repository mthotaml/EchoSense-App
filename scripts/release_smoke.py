from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from echosense.app import create_app


def main() -> None:
    checks = {}
    for profile in ("api", "legacy", "product"):
        response = TestClient(create_app(profile)).get("/healthz")
        checks[f"{profile}_health"] = response.status_code == 200 and response.json() == {
            "status": "ok",
            "profile": profile,
            "version": "0.24.0",
        }
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": os.getenv("GITHUB_SHA", "local"),
        "checks": checks,
        "release_ready": all(checks.values()),
        "blocking_severities": ["severity-1", "severity-2"],
    }
    output = Path("artifacts/guardian/release-evidence.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    if not report["release_ready"]:
        raise SystemExit("Release smoke failed")


if __name__ == "__main__":
    main()
