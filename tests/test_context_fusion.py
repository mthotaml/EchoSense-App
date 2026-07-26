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
                "current": {
                    "temperature_2m": 78.4,
                    "precipitation": 0,
                    "weather_code": 0,
                    "is_day": 1,
                }
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
