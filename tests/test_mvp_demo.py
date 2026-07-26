from echosense.demo import run_demo


def test_mvp_demo_exercises_complete_cognitive_loop() -> None:
    result = run_demo()

    first = result["first"]
    first_trace = result["first_trace"]
    learned = result["learned"]
    second_trace = result["second_trace"]
    deletion = result["deletion"]

    assert first["context"] == "rainy_commute"
    assert first_trace["factors"]["candidate_count"] == 3
    assert first_trace["factors"]["candidate_slate"][0]["selected"] is True
    assert learned["weight"] > 0

    second_candidates = {
        item["item_id"]: item
        for item in second_trace["factors"]["candidate_slate"]
    }
    repeated = second_candidates[first["item_id"]]
    assert repeated["preference_weight"] == learned["weight"]
    assert repeated["exposure_count"] == 1
    assert repeated["novelty_score"] < 1.0

    assert deletion["status"] == "completed"
    assert sum(deletion["counts"].values()) > 0
