from echosense.ranking_policy import (
    PolicyCandidate,
    RankingPolicy,
    diversify,
    rank_with_policy,
)


def candidates() -> list[PolicyCandidate]:
    return [
        PolicyCandidate("provider_a", "a1", 0.90, 0.0, exposure_count=20, group="artist_a"),
        PolicyCandidate("provider_a", "a2", 0.88, 0.0, exposure_count=0, group="artist_a"),
        PolicyCandidate("provider_b", "b1", 0.84, 0.1, exposure_count=0, group="artist_b"),
    ]


def test_novelty_can_lift_unexposed_candidate_within_bound() -> None:
    ranked = rank_with_policy(
        candidates(),
        preference_influence=0.25,
        policy=RankingPolicy(novelty_weight=0.10, exploration_rate=0.0),
        seed_material="decision-1",
    )
    assert ranked[0].item_id == "a2"
    assert ranked[0].novelty_score == 1.0
    assert ranked[0].explored is False


def test_exploration_is_deterministic_and_bounded() -> None:
    policy = RankingPolicy(novelty_weight=0.0, exploration_rate=0.2, exploration_pool=2)
    first = rank_with_policy(
        candidates(), preference_influence=0.25, policy=policy, seed_material="fixed"
    )
    second = rank_with_policy(
        candidates(), preference_influence=0.25, policy=policy, seed_material="fixed"
    )
    assert first == second
    assert first[0].item_id in {"a1", "a2"}


def test_diversity_prefers_distinct_groups_then_backfills() -> None:
    ranked = rank_with_policy(
        candidates(),
        preference_influence=0.25,
        policy=RankingPolicy(exploration_rate=0.0),
        seed_material="decision-2",
    )
    diversified = diversify(ranked, limit=3, max_per_group=1)
    assert diversified[0].group != diversified[1].group
    assert len(diversified) == 3


def test_policy_rejects_unbounded_controls() -> None:
    try:
        RankingPolicy(novelty_weight=0.5)
    except ValueError as exc:
        assert "novelty_weight" in str(exc)
    else:
        raise AssertionError("unbounded novelty weight was accepted")

    try:
        RankingPolicy(exploration_rate=0.5)
    except ValueError as exc:
        assert "exploration_rate" in str(exc)
    else:
        raise AssertionError("unbounded exploration rate was accepted")
