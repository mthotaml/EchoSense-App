from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from fastapi.testclient import TestClient  # noqa: E402

from echosense.app import create_app  # noqa: E402
from echosense.guardian import release_identity  # noqa: E402


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
        "artifact_identity": release_identity(),
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
