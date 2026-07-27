import json

import pytest

from echosense import guardian
from echosense.guardian import release_identity, validate_guardian_configuration


def test_guardian_configuration_contract() -> None:
    configuration = validate_guardian_configuration()
    assert configuration["version"] == 2
    assert {item["severity"] for item in configuration["invariants"]} >= {
        "severity-1",
        "severity-2",
    }


def test_guardian_rejects_stale_executable_evidence(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "guardian").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/journey.js").write_text("test('real assertion', () => {})")
    (tmp_path / "guardian/schema.json").write_text(
        (guardian.ROOT / "guardian/schema.json").read_text()
    )
    configuration = {
        "version": 2,
        "release_gate": {"required_checks": ["evidence"]},
        "invariants": [
            {
                "id": "runtime-proof",
                "severity": "severity-1",
                "description": "Runtime behavior is asserted.",
                "covers": ["ready"],
                "evidence": [
                    {
                        "source": "tests/journey.js",
                        "pattern": "missing assertion",
                    }
                ],
            }
        ],
        "journeys": [
            {
                "id": "journey",
                "spec": "tests/journey.js",
                "states": ["ready", "complete"],
            }
        ],
    }
    (tmp_path / "guardian/guardian.json").write_text(json.dumps(configuration))
    monkeypatch.setattr(guardian, "ROOT", tmp_path)

    with pytest.raises(ValueError, match="stale evidence"):
        validate_guardian_configuration()


def test_release_identity_hashes_guardian_and_player_contracts() -> None:
    identity = release_identity()

    assert identity["guardian_version"] == 2
    assert set(identity["files"]) == {
        "guardian_configuration",
        "guardian_schema",
        "product_ui",
        "player_lifecycle",
    }
    assert all(len(digest) == 64 for digest in identity["files"].values())


def test_temporal_mood_contracts_promote_only_with_executable_guards() -> None:
    configuration = json.loads((guardian.ROOT / "guardian/guardian.json").read_text())
    journey = next(item for item in configuration["journeys"] if item["id"] == "spotify-reference")
    planned = set(journey["planned_states"])
    certified = set(journey["states"])

    assert {
        "temporal-pattern-evidence-threshold",
        "recent-mood-shift-bounded",
        "single-track-mood-inference-rejected",
        "temporal-mood-factor-explained",
        "temporal-mood-memory-reset",
        "sensitive-mood-inference-prohibited",
    } <= certified
    assert {
        "mood-dna-compatibility-floor",
        "mood-ranking-influence-bounded",
        "cross-provider-mood-evidence-deduplicated",
    } <= planned
    assert planned.isdisjoint(certified)
