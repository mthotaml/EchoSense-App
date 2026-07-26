from echosense.context_candidates import ContextCandidateService


class FakeSpotifyClient:
    def __init__(self) -> None:
        self.queries = []

    def request(self, method, path, *, params):
        self.queries.append(params["q"])
        item_id = f"track-{len(self.queries)}"
        return {
            "tracks": {
                "items": [
                    {
                        "id": item_id,
                        "name": params["q"].title(),
                        "artists": [{"name": "Context Artist"}],
                        "album": {"name": "Context", "images": []},
                        "external_urls": {"spotify": f"https://open.spotify.com/track/{item_id}"},
                    }
                ]
            }
        }


def test_context_expands_candidates_with_explainable_queries() -> None:
    client = FakeSpotifyClient()

    result = ContextCandidateService().expand(
        client,
        weather="sunny",
        region="Southern California",
        road_setting="coastal",
        activity="driving",
        daypart="afternoon",
    )

    assert client.queries == [
        "beach coastal drive",
        "sunny day",
        "California Los Angeles",
        "driving",
        "afternoon music",
    ]
    assert len(result.tracks) == 5
    assert result.scores["track-1"] == 1.0
    assert result.evidence["track-1"] == ("coastal drive matched to your Music DNA",)
    assert result.evidence["track-3"] == ("local connection to Southern California",)


def test_mountain_query_has_situational_explanation() -> None:
    queries = ContextCandidateService.queries(
        weather=None,
        region="your area",
        road_setting="mountain",
        activity="driving",
        daypart="morning",
    )

    assert queries[0] == (
        "mountain scenic drive",
        "mountain drive matched to your Music DNA",
        1.0,
    )
