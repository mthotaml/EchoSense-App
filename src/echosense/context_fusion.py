from __future__ import annotations

from dataclasses import asdict, dataclass

import httpx


@dataclass(frozen=True)
class ContextSnapshot:
    daypart: str
    weather: str
    temperature_f: int | None
    region: str
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

    def resolve(
        self,
        *,
        latitude: float,
        longitude: float,
        local_hour: int,
        speed_mps: float | None = None,
        baseline_speed_mps: float | None = None,
    ) -> ContextSnapshot:
        weather, temperature_f, available = self._weather(latitude, longitude)
        activity, faster = self._activity(speed_mps, baseline_speed_mps)
        return ContextSnapshot(
            daypart=self._daypart(local_hour),
            weather=weather,
            temperature_f=temperature_f,
            region=self._region(latitude, longitude),
            activity=activity,
            speed_mph=round(speed_mps * 2.23694) if speed_mps is not None else None,
            faster_than_usual=faster,
            weather_available=available,
        )

    def _weather(self, latitude: float, longitude: float) -> tuple[str, int | None, bool]:
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
            current = response.json()["current"]
            code = int(current["weather_code"])
            precipitation = float(current.get("precipitation", 0))
            weather = self._weather_label(code, precipitation)
            return weather, round(float(current["temperature_2m"])), True
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return "unknown", None, False

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
