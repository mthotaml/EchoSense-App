from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from echosense.guardian import ROOT, release_identity  # noqa: E402


def _command(name: str, arguments: list[str]) -> dict[str, object]:
    started_at = datetime.now(UTC)
    environment = os.environ.copy()
    environment.setdefault("ECHOSENSE_PYTHON", sys.executable)
    completed = subprocess.run(
        arguments,
        cwd=ROOT,
        check=False,
        env=environment,
    )
    finished_at = datetime.now(UTC)
    return {
        "name": name,
        "command": arguments,
        "passed": completed.returncode == 0,
        "return_code": completed.returncode,
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the complete Guardian release gate and record artifact-bound evidence."
    )
    parser.add_argument(
        "--without-browser",
        action="store_true",
        help="Developer-only mode; cannot produce release-ready evidence.",
    )
    args = parser.parse_args()

    commands = [
        (
            "configuration",
            [sys.executable, "scripts/validate_guardian.py"],
        ),
        ("ruff", [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"]),
        (
            "ruff-format",
            [
                sys.executable,
                "-m",
                "ruff",
                "format",
                "--check",
                "src",
                "tests",
                "scripts",
            ],
        ),
        (
            "contract-tests",
            [
                sys.executable,
                "-m",
                "pytest",
                "-m",
                "not infrastructure and not postgres and not neo4j",
            ],
        ),
        ("browser-lifecycle", ["node", "tests/player_lifecycle.test.js"]),
        ("application-profile-smoke", [sys.executable, "scripts/release_smoke.py"]),
    ]
    if not args.without_browser:
        commands.append(("spotify-reference-journey", ["npm", "run", "test:e2e"]))

    results = []
    for name, arguments in commands:
        result = _command(name, arguments)
        results.append(result)
        if not result["passed"]:
            break

    report = {
        "schema_version": 2,
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": os.getenv("GITHUB_SHA", "local"),
        "artifact_identity": release_identity(),
        "browser_gate_executed": not args.without_browser,
        "checks": results,
        "release_ready": (
            not args.without_browser
            and len(results) == len(commands)
            and all(result["passed"] for result in results)
        ),
    }
    output = ROOT / "artifacts/guardian/release-gate-evidence.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    if not report["release_ready"]:
        raise SystemExit("Guardian release gate failed")


if __name__ == "__main__":
    main()
