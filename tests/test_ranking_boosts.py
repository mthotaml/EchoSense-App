import pytest

from echosense.playback_learning import PlaybackLearningService
from echosense.providers.models import Track
from echosense.ranking_boosts import RecommendationBoosts, build_context_statement
from echosense.storage import Storage


def test_effective_boost_weights_are_bounded_and_normalized() -> None:
    boosts = RecommendationBoosts(
        music_dna=20,
        live_context=60,
        learned_preference=40,
        diversity=100,
    )

    weights = boosts.effective_weights(live_context_available=True)

    assert sum(weights.values()) == pytest.approx(1.0, abs=0.00001)
    assert all(0 < value < 1 for value in weights.values())
    assert (
        weights["diversity"]
        > RecommendationBoosts().effective_weights(live_context_available=True)["diversity"]
    )


def test_invalid_boost_is_rejected() -> None:
    with pytest.raises(ValueError, match="diversity boost"):
        RecommendationBoosts(diversity=101)


def test_diversity_boost_can_promote_less_fatigued_artist(tmp_path) -> None:
    service = PlaybackLearningService(Storage(f"sqlite:///{tmp_path / 'boosts.db'}"))
    tracks = [
        Track("spotify", "familiar", "Familiar", ("Repeated Artist",)),
        Track("spotify", "fresh", "Fresh", ("Fresh Artist",)),
    ]
    common = {
        "user_id": "listener",
        "provider": "spotify",
        "context": "general_listening",
        "tracks": tracks,
        "diversity_scores": {"familiar": 0.8, "fresh": 1.0},
    }

    selected, _ = service.rank(**common)
    boosted, slate = service.rank(**common, boosts=RecommendationBoosts(diversity=100))

    assert selected == tracks[0]
    assert boosted == tracks[1]
    assert slate[0]["effective_weights"]["diversity"] == pytest.approx(0.2)


def test_context_statement_reports_observations_and_requested_emphasis() -> None:
    boosts = RecommendationBoosts(live_context=80, diversity=100)
    weights = boosts.effective_weights(live_context_available=True)

    statement = build_context_statement(
        moment="driving",
        weather="partly_cloudy",
        region="Southern California",
        road_setting="coastal",
        activity="driving",
        daypart="morning",
        boosts=boosts,
        effective_weights=weights,
    )

    assert "partly cloudy weather" in statement
    assert "a coastal setting" in statement
    assert "live context" in statement
    assert "artist diversity" in statement
    assert "next track is ranked from the same evidence" in statement
