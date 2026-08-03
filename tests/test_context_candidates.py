import pytest

from echosense.context_candidates import ContextCandidateService
from echosense.providers.spotify.client import SpotifyRateLimited


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


def test_optional_mood_candidate_outage_is_isolated() -> None:
    class UnavailableClient:
        def request(self, *args, **kwargs):
            raise RuntimeError("optional provider feature unavailable")

    result = ContextCandidateService().expand(
        UnavailableClient(),
        weather=None,
        region=None,
        road_setting=None,
        activity=None,
        daypart="evening",
        mood="romantic",
    )

    assert result.tracks == ()
    assert result.scores == {}
    assert result.evidence == {}


def test_context_search_never_swallows_provider_cooldown() -> None:
    class LimitedClient:
        def request(self, *args, **kwargs):
            raise SpotifyRateLimited(60, reason="QUOTA_EXCEEDED")

    with pytest.raises(SpotifyRateLimited, match="Spotify rate limit reached"):
        ContextCandidateService().expand(
            LimitedClient(),
            weather="sunny",
            region=None,
            road_setting=None,
            activity=None,
            daypart="morning",
        )


def test_every_selected_listening_moment_generates_explainable_catalog_candidates() -> None:
    expected = {
        "driving": "driving road trip music",
        "working": "focus instrumental work music",
        "exercising": "energetic workout music",
        "relaxing": "relaxing calm music",
        "social": "party social music",
    }

    for moment, query in expected.items():
        generated = ContextCandidateService.queries(
            weather=None,
            region=None,
            road_setting=None,
            activity=None,
            daypart=None,
            moment=moment,
        )
        assert generated[0] == (query, f"selected {moment} moment", 1.0)


def test_selected_driving_moment_does_not_duplicate_detected_driving_query() -> None:
    generated = ContextCandidateService.queries(
        weather=None,
        region=None,
        road_setting=None,
        activity="driving",
        daypart=None,
        moment="driving",
    )

    assert [label for _, label, _ in generated].count("selected driving moment") == 1
    assert all(label != "driving context" for _, label, _ in generated)
