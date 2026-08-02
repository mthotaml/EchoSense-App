from fastapi.testclient import TestClient

from echosense.app import AppProfile, create_app


def _route_paths(profile: AppProfile) -> list[str]:
    return list(create_app(profile).openapi()["paths"])


def test_profiles_own_distinct_root_routes() -> None:
    legacy = TestClient(create_app("legacy")).get("/")
    product = TestClient(create_app("product")).get("/")

    assert legacy.status_code == 200
    assert "Connect Apple Music" in legacy.text
    assert "Today's pick" not in legacy.text

    assert product.status_code == 200
    assert "Current EchoSense recommendation" in product.text
    assert "Connect Apple Music" not in product.text


def test_profile_route_maps_are_isolated_and_repeatable() -> None:
    product_before = _route_paths("product")
    legacy = _route_paths("legacy")
    product_after = _route_paths("product")

    assert product_before == product_after
    assert "/auth/spotify/login" in product_before
    assert "/auth/spotify/login" not in legacy
    assert "/v1/providers/apple-music/config" in legacy
    assert "/v1/providers/apple-music/config" not in product_before


def test_api_profile_has_no_user_interface_root() -> None:
    response = TestClient(create_app("api")).get("/")

    assert response.status_code == 404
