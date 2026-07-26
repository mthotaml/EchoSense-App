import json

from echosense import guardian
from echosense.guardian import validate_guardian_configuration


def test_guardian_configuration_contract() -> None:
    validate_guardian_configuration()


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
