import httpx

from echosense import context_fusion
from echosense.context_fusion import ContextFusionService


def test_context_fuses_socal_weather_time_and_fast_driving(monkeypatch) -> None:
    monkeypatch.setattr(
        context_fusion.httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("GET", ContextFusionService.WEATHER_URL),
            json={
                "elevation": 24,
                "current": {
                    "temperature_2m": 78.4,
                    "precipitation": 0,
                    "weather_code": 0,
                    "is_day": 1,
                },
            },
        ),
    )

    snapshot = ContextFusionService().resolve(
        latitude=33.68,
        longitude=-117.82,
        local_hour=15,
        speed_mps=25,
        baseline_speed_mps=18,
    )

    assert snapshot.daypart == "afternoon"
    assert snapshot.weather == "sunny"
    assert snapshot.temperature_f == 78
    assert snapshot.region == "Southern California"
    assert snapshot.road_setting == "coastal"
    assert snapshot.elevation_m == 24
    assert snapshot.activity == "fast_driving"
    assert snapshot.faster_than_usual is True
    assert snapshot.location_precision == "coarse"
    assert "latitude" not in snapshot.as_dict()
    assert "longitude" not in snapshot.as_dict()


def test_context_degrades_to_time_and_motion_when_weather_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        context_fusion.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )

    snapshot = ContextFusionService().resolve(
        latitude=40,
        longitude=-73,
        local_hour=8,
        speed_mps=0,
    )

    assert snapshot.daypart == "morning"
    assert snapshot.weather == "unknown"
    assert snapshot.weather_available is False
    assert snapshot.activity == "stationary"
    assert snapshot.region == "your area"
    assert snapshot.road_setting == "general"


def test_context_degrades_when_weather_client_cannot_initialize(monkeypatch) -> None:
    monkeypatch.setattr(
        context_fusion.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ImportError("optional proxy transport unavailable")
        ),
    )

    snapshot = ContextFusionService().resolve(
        latitude=33.54,
        longitude=-117.79,
        local_hour=14,
        speed_mps=14,
    )

    assert snapshot.weather_available is False
    assert snapshot.weather == "unknown"
    assert snapshot.road_setting == "coastal"
    assert snapshot.activity == "driving"


def test_context_identifies_mountain_setting_from_elevation(monkeypatch) -> None:
    monkeypatch.setattr(
        context_fusion.httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200,
            request=httpx.Request("GET", ContextFusionService.WEATHER_URL),
            json={
                "elevation": 1830,
                "current": {
                    "temperature_2m": 48,
                    "precipitation": 0,
                    "weather_code": 2,
                },
            },
        ),
    )

    snapshot = ContextFusionService().resolve(
        latitude=34.2439,
        longitude=-116.9114,
        local_hour=10,
        speed_mps=16,
    )

    assert snapshot.road_setting == "mountain"
    assert snapshot.elevation_m == 1830
    assert snapshot.activity == "driving"
