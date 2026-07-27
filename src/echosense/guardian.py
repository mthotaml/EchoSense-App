from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def _repository_file(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    if ROOT not in path.parents:
        raise ValueError(f"Guardian evidence leaves repository: {relative_path}")
    if not path.is_file():
        raise FileNotFoundError(f"Guardian evidence does not exist: {path}")
    return path


def validate_guardian_configuration() -> dict:
    schema = json.loads((ROOT / "guardian/schema.json").read_text())
    configuration = json.loads((ROOT / "guardian/guardian.json").read_text())
    Draft202012Validator(schema).validate(configuration)
    invariant_ids = [item["id"] for item in configuration["invariants"]]
    if len(invariant_ids) != len(set(invariant_ids)):
        raise ValueError("Guardian invariant ids must be unique")

    certified_states = {
        state for journey in configuration["journeys"] for state in journey["states"]
    }
    for invariant in configuration["invariants"]:
        unknown = set(invariant["covers"]) - certified_states
        if unknown:
            raise ValueError(
                f"Guardian invariant {invariant['id']} covers unknown states: "
                + ", ".join(sorted(unknown))
            )
        for evidence in invariant["evidence"]:
            source = _repository_file(evidence["source"])
            if evidence["pattern"] not in source.read_text():
                raise ValueError(
                    f"Guardian invariant {invariant['id']} has stale evidence: "
                    f"{evidence['pattern']!r} not found in {evidence['source']}"
                )

    for journey in configuration["journeys"]:
        overlap = set(journey["states"]) & set(journey.get("planned_states", ()))
        if overlap:
            raise ValueError(
                "Guardian states cannot be both certified and planned: "
                + ", ".join(sorted(overlap))
            )
        _repository_file(journey["spec"])
    return configuration


def release_identity() -> dict[str, object]:
    configuration = validate_guardian_configuration()
    tracked_files = {
        "guardian_configuration": ROOT / "guardian/guardian.json",
        "guardian_schema": ROOT / "guardian/schema.json",
        "product_ui": ROOT / "src/echosense/product_ui.py",
        "player_lifecycle": ROOT / "src/echosense/web/player-lifecycle.js",
    }
    return {
        "guardian_version": configuration["version"],
        "files": {
            name: sha256(path.read_bytes()).hexdigest() for name, path in tracked_files.items()
        },
    }
