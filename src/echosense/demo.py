from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import echosense.app as app_module
from echosense.memory import InMemoryPreferenceMemory
from echosense.providers import FixtureMusicProvider
from echosense.storage import Storage

USER_ID = "demo_user"
PURPOSE_ID = "contextual_recommendation"


def _check(response, expected: int = 200):
    if response.status_code != expected:
        raise RuntimeError(f"Unexpected response {response.status_code}: {response.text}")
    return response


def _reset_demo_state(database_path: Path) -> TestClient:
    os.environ["ECHOSENSE_EXPLORATION_RATE"] = "0"
    app_module.storage = Storage(f"sqlite:///{database_path}")
    app_module.music_provider = FixtureMusicProvider()
    app_module.preference_memory = InMemoryPreferenceMemory()
    app_module.deletion_coordinator = None
    app_module.evaluation_service = None
    app_module.exposure_store = None
    return TestClient(app_module.app)


def run_demo() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="echosense-demo-") as temporary_directory:
        client = _reset_demo_state(Path(temporary_directory) / "demo.db")

        _check(
            client.put(
                "/v1/consents",
                json={
                    "user_id": USER_ID,
                    "purpose_id": PURPOSE_ID,
                    "policy_version": "mvp-1",
                },
            ),
            204,
        )

        recommendation_request = {
            "user_id": USER_ID,
            "signals": [
                {
                    "type": "activity",
                    "value": "driving",
                    "confidence": 0.95,
                    "purpose_id": PURPOSE_ID,
                },
                {
                    "type": "weather",
                    "value": "rain",
                    "confidence": 0.90,
                    "purpose_id": PURPOSE_ID,
                },
            ],
        }

        first = _check(client.post("/v1/recommendations", json=recommendation_request)).json()
        first_trace = _check(client.get(f"/v1/decision-traces/{first['decision_id']}")).json()

        learned = _check(
            client.post(
                "/v1/outcomes",
                json={
                    "outcome_id": "demo-liked-1",
                    "user_id": USER_ID,
                    "decision_id": first["decision_id"],
                    "outcome": "liked",
                },
            )
        ).json()

        second = _check(client.post("/v1/recommendations", json=recommendation_request)).json()
        second_trace = _check(client.get(f"/v1/decision-traces/{second['decision_id']}")).json()

        deletion = _check(
            client.post(
                f"/v1/users/{USER_ID}/deletions",
                json={"purpose_id": PURPOSE_ID, "confirmation": "delete"},
            )
        ).json()

        blocked_after_deletion = client.post("/v1/recommendations", json=recommendation_request)
        if blocked_after_deletion.status_code != 403:
            raise RuntimeError("Deletion verification failed: processing was not blocked")

        return {
            "first": first,
            "first_trace": first_trace,
            "learned": learned,
            "second": second,
            "second_trace": second_trace,
            "deletion": deletion,
        }


def main() -> None:
    result = run_demo()
    first = result["first"]
    first_trace = result["first_trace"]
    learned = result["learned"]
    second = result["second"]
    second_trace = result["second_trace"]
    deletion = result["deletion"]

    first_selected = first_trace["factors"]["candidate_slate"][0]
    second_candidates = {
        item["item_id"]: item for item in second_trace["factors"]["candidate_slate"]
    }
    repeated = second_candidates[first["item_id"]]

    print("=" * 56)
    print("EchoSense Cognitive Platform — MVP Demo")
    print("=" * 56)
    print("✓ Consent granted")
    print("\nObservation")
    print("  activity: driving (0.95)")
    print("  weather: rain (0.90)")
    print("\nUnderstanding")
    print(f"  context: {first['context']} ({first['context_confidence']:.3f})")
    print("\nReasoning")
    print(f"  candidates evaluated: {first_trace['factors']['candidate_count']}")
    print(f"  selected score: {first_selected['ranking_score']:.3f}")
    print("\nRecommendation")
    print(f"  {first['provider']} / {first['item_id']}")
    print(f"  why: {first['explanation']}")
    print("\nOutcome and learning")
    print("  user response: liked")
    print(f"  preference weight: 0.000 → {learned['weight']:.3f}")
    print("\nSecond decision")
    print(f"  selected: {second['provider']} / {second['item_id']}")
    print(
        "  prior selected-item novelty: "
        f"{first_selected['novelty_score']:.3f} → {repeated['novelty_score']:.3f}"
    )
    print(f"  learned preference used: {repeated['preference_weight']:.3f}")
    print("\nDeletion")
    print(f"  status: {deletion['status']}")
    print(f"  removed records: {sum(deletion['counts'].values())}")
    print("  ✓ Future processing blocked")
    print("\nDemo complete.")


if __name__ == "__main__":
    main()
