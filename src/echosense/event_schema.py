from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from jsonschema import Draft202012Validator


class SchemaRegistry(Protocol):
    def validate(self, subject: str, envelope: dict[str, Any]) -> int: ...


@dataclass(frozen=True)
class LocalSchemaRegistry:
    schema_path: Path
    schema_id: int = 1

    def validate(self, subject: str, envelope: dict[str, Any]) -> int:
        del subject
        schema = json.loads(self.schema_path.read_text())
        Draft202012Validator(schema).validate(envelope)
        return self.schema_id


class ConfluentSchemaRegistry:
    """Confluent-compatible JSON Schema registry adapter."""

    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._validators: dict[str, tuple[int, Draft202012Validator]] = {}

    def validate(self, subject: str, envelope: dict[str, Any]) -> int:
        cached = self._validators.get(subject)
        if cached is None:
            response = httpx.get(
                f"{self.base_url}/subjects/{subject}/versions/latest",
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            schema = json.loads(body["schema"])
            cached = (int(body["id"]), Draft202012Validator(schema))
            self._validators[subject] = cached
        schema_id, validator = cached
        validator.validate(envelope)
        return schema_id


def registry_from_environment() -> SchemaRegistry:
    backend = os.getenv("ECHOSENSE_SCHEMA_REGISTRY_BACKEND", "local").lower()
    if backend == "local":
        configured = os.getenv("ECHOSENSE_EVENT_SCHEMA_PATH")
        schema_path = Path(configured) if configured else Path(__file__).parents[2] / "schemas" / "event-envelope.v1.json"
        return LocalSchemaRegistry(schema_path=schema_path)
    if backend in {"confluent", "redpanda"}:
        return ConfluentSchemaRegistry(
            os.getenv("ECHOSENSE_SCHEMA_REGISTRY_URL", "http://localhost:8081")
        )
    raise ValueError(f"Unsupported schema registry backend: {backend}")
