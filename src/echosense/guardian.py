from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def validate_guardian_configuration() -> None:
    schema = json.loads((ROOT / "guardian/schema.json").read_text())
    configuration = json.loads((ROOT / "guardian/guardian.json").read_text())
    Draft202012Validator(schema).validate(configuration)
    for journey in configuration["journeys"]:
        spec = ROOT / journey["spec"]
        if not spec.is_file():
            raise FileNotFoundError(f"Guardian journey spec does not exist: {spec}")
