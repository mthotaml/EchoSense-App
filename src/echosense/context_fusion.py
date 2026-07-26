from __future__ import annotations

from dataclasses import asdict, dataclass
from math import asin, cos, radians, sin, sqrt

import httpx


@dataclass(frozen=True)
class ContextSnapshot:
    daypart: str
    weather: str
    temperature_f: int | None
    region: str
    road_setting: str
    elevation_m: int | None
    activity: str
    speed_mph: int | None
    faster_than_usual: bool
    weather_available: bool
    location_precision: str = "coarse"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class ContextFusionService:
    """Derives transient listening context without persisting raw coordinates."""

    WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
    SOCAL_COAST_ANCHORS = (
        (32.7157, -117.1611),
        (33.1959, -117.3795),
        (33.5427, -117.7854),
        (33.6189, -117.9298),
        (33.6595, -117.9988),
        (33.7701, -118.1937),
        (34.0195, -118.4912),
        (34.0259, -118.7798),
    )

    def resolve(
        self,
        *,
        latitude: float,
        longitude: float,
        local_hour: int,
        speed_mps: float | None = None,
        baseline_speed_mps: float | None = None,
    ) -> ContextSnapshot:
        weather, temperature_f, elevation_m, available = self._weather(latitude, longitude)
        activity, faster = self._activity(speed_mps, baseline_speed_mps)
        return ContextSnapshot(
            daypart=self._daypart(local_hour),
            weather=weather,
            temperature_f=temperature_f,
            region=self._region(latitude, longitude),
            road_setting=self._road_setting(latitude, longitude, elevation_m),
            elevation_m=elevation_m,
            activity=activity,
            speed_mph=round(speed_mps * 2.23694) if speed_mps is not None else None,
            faster_than_usual=faster,
            weather_available=available,
        )

    def _weather(
        self, latitude: float, longitude: float
    ) -> tuple[str, int | None, int | None, bool]:
        try:
            response = httpx.get(
                self.WEATHER_URL,
                params={
                    "latitude": round(latitude, 3),
                    "longitude": round(longitude, 3),
                    "current": "temperature_2m,precipitation,weather_code,is_day",
                    "temperature_unit": "fahrenheit",
                },
                timeout=8.0,
            )
            response.raise_for_status()
            payload = response.json()
            current = payload["current"]
            code = int(current["weather_code"])
            precipitation = float(current.get("precipitation", 0))
            weather = self._weather_label(code, precipitation)
            elevation = payload.get("elevation")
            elevation_m = round(float(elevation)) if elevation is not None else None
            return weather, round(float(current["temperature_2m"])), elevation_m, True
        except (httpx.HTTPError, ImportError, KeyError, RuntimeError, TypeError, ValueError):
            return "unknown", None, None, False

    @classmethod
    def _road_setting(
        cls,
        latitude: float,
        longitude: float,
        elevation_m: int | None,
    ) -> str:
        if elevation_m is not None and elevation_m >= 500:
            return "mountain"
        if (
            cls._region(latitude, longitude) == "Southern California"
            and (elevation_m is None or elevation_m <= 250)
            and min(
                cls._distance_km(latitude, longitude, anchor_lat, anchor_lon)
                for anchor_lat, anchor_lon in cls.SOCAL_COAST_ANCHORS
            )
            <= 18
        ):
            return "coastal"
        return "general"

    @staticmethod
    def _distance_km(
        latitude: float,
        longitude: float,
        other_latitude: float,
        other_longitude: float,
    ) -> float:
        lat_delta = radians(other_latitude - latitude)
        lon_delta = radians(other_longitude - longitude)
        start_lat = radians(latitude)
        end_lat = radians(other_latitude)
        value = sin(lat_delta / 2) ** 2 + cos(start_lat) * cos(end_lat) * sin(lon_delta / 2) ** 2
        return 6371 * 2 * asin(sqrt(value))

    @staticmethod
    def _weather_label(code: int, precipitation: float) -> str:
        if precipitation > 0 or 51 <= code <= 99:
            return "rainy"
        if code == 0:
            return "sunny"
        if code in {1, 2}:
            return "partly_cloudy"
        if code == 3 or 45 <= code <= 48:
            return "cloudy"
        return "mixed"

    @staticmethod
    def _daypart(hour: int) -> str:
        if not 0 <= hour <= 23:
            raise ValueError("local_hour must be between 0 and 23")
        if hour < 6:
            return "late_night"
        if hour < 12:
            return "morning"
        if hour < 17:
            return "afternoon"
        if hour < 21:
            return "evening"
        return "night"

    @staticmethod
    def _region(latitude: float, longitude: float) -> str:
        if 32.0 <= latitude <= 35.8 and -121.0 <= longitude <= -114.0:
            return "Southern California"
        if 32.0 <= latitude <= 42.1 and -124.6 <= longitude <= -114.0:
            return "California"
        return "your area"

    @staticmethod
    def _activity(
        speed_mps: float | None,
        baseline_speed_mps: float | None,
    ) -> tuple[str, bool]:
        if speed_mps is None or speed_mps < 0:
            return "unknown", False
        if speed_mps < 1:
            return "stationary", False
        if speed_mps < 3.5:
            return "walking", False
        if speed_mps < 8:
            return "moving", False
        faster = speed_mps >= 27
        if baseline_speed_mps and baseline_speed_mps >= 8:
            faster = faster or (
                speed_mps >= baseline_speed_mps * 1.2 and speed_mps - baseline_speed_mps >= 2
            )
        return ("fast_driving" if faster else "driving"), faster
