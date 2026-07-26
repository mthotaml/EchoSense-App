from pathlib import Path

from echosense.cognitive_memory import CognitiveMemoryStore
from echosense.decision_evidence import DecisionAction, DecisionEvidenceService
from echosense.storage import Storage
from echosense.understanding import ObservationEvidence, UnderstandingEngine


def test_decision_trace_persists_observation_memory_inference_and_action(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'decision-evidence.db'}")
    memory = CognitiveMemoryStore(storage)
    memory.remember(
        memory_id="mem-01",
        user_id="user-01",
        memory_type="semantic",
        subject="user",
        predicate="prefers",
        object="calm music",
        context="evening_wind_down",
        confidence=0.9,
        provenance_type="explicit",
        provenance_ref="profile",
    )
    service = DecisionEvidenceService(storage, UnderstandingEngine(memory))

    service.record(
        decision_id="dec-01",
        user_id="user-01",
        context="evening_wind_down",
        context_confidence=0.85,
        observations=[ObservationEvidence("time", "evening", 0.9)],
        action=DecisionAction(provider="fixture", item_id="track-01"),
        factors={"ranking_score": 0.8},
    )

    trace = storage.get_decision_trace("dec-01")
    assert trace is not None
    assert trace["user_id"] == "user-01"
    understanding = trace["factors"]["understanding"]
    assert understanding["observations"][0]["key"] == "time"
    assert understanding["memories"][0]["memory_id"] == "mem-01"
    assert understanding["inferences"][0]["memory_ids"] == ["mem-01"]
    assert understanding["action"]["target_ref"] == "fixture:track-01"
    assert trace["factors"]["ranking_score"] == 0.8
