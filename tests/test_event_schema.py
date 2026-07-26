from pathlib import Path

import pytest
from jsonschema import ValidationError

from echosense.event_schema import LocalSchemaRegistry


def registry() -> LocalSchemaRegistry:
    schema_path = Path(__file__).parents[1] / "schemas" / "event-envelope.v1.json"
    return LocalSchemaRegistry(schema_path=schema_path, schema_id=17)


def valid_envelope() -> dict[str, object]:
    return {
        "event_id": "evt_01",
        "event_type": "recommendation.ranked",
        "schema_version": "1.0",
        "occurred_at": "2026-07-20T19:30:00+00:00",
        "user_id": "user_01",
        "trace_id": "trc_01",
        "payload": {"decision_id": "dec_01"},
    }


def test_local_registry_validates_canonical_envelope() -> None:
    assert registry().validate("echosense.events.v1-value", valid_envelope()) == 17


def test_local_registry_rejects_unknown_envelope_fields() -> None:
    envelope = valid_envelope()
    envelope["secret"] = "must-not-pass"

    with pytest.raises(ValidationError):
        registry().validate("echosense.events.v1-value", envelope)


def test_local_registry_rejects_invalid_event_type() -> None:
    envelope = valid_envelope()
    envelope["event_type"] = "Recommendation Ranked"

    with pytest.raises(ValidationError):
        registry().validate("echosense.events.v1-value", envelope)
