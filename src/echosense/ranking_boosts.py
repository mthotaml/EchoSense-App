from __future__ import annotations

from dataclasses import asdict, dataclass

BOOST_MAX = 100


@dataclass(frozen=True)
class RecommendationBoosts:
    """User-controlled, bounded emphasis applied to recommendation evidence."""

    music_dna: int = 0
    live_context: int = 0
    learned_preference: int = 0
    diversity: int = 0

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not 0 <= value <= BOOST_MAX:
                raise ValueError(f"{name} boost must be between 0 and {BOOST_MAX}")

    def effective_weights(self, *, live_context_available: bool) -> dict[str, float]:
        # Context gets a larger baseline only when context evidence is available.
        base = {
            "music_dna": 0.55,
            "live_context": 0.20 if live_context_available else 0.10,
            "learned_preference": 0.15,
            "diversity": 0.10,
        }
        boosted = {
            name: weight * (1.0 + getattr(self, name) / BOOST_MAX) for name, weight in base.items()
        }
        total = sum(boosted.values())
        return {name: round(value / total, 6) for name, value in boosted.items()}

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def build_context_statement(
    *,
    moment: str,
    weather: str | None,
    region: str | None,
    road_setting: str | None,
    activity: str | None,
    daypart: str | None,
    boosts: RecommendationBoosts,
    effective_weights: dict[str, float],
) -> str:
    observations: list[str] = []
    if daypart:
        observations.append(daypart.replace("_", " "))
    if weather:
        observations.append(f"{weather.replace('_', ' ')} weather")
    if road_setting and road_setting != "general":
        observations.append(f"a {road_setting.replace('_', ' ')} setting")
    if activity and activity != "unknown":
        observations.append(activity.replace("_", " "))
    if region and region != "your area":
        observations.append(region)

    if observations:
        opening = "EchoSense sees " + ", ".join(observations) + "."
    elif moment == "general":
        opening = (
            "Any moment is selected, so EchoSense is using broadly suitable listening signals."
        )
    else:
        opening = f"EchoSense is tailoring this sequence for {moment.replace('_', ' ')}."

    labels = {
        "music_dna": "Music DNA affinity",
        "live_context": "live context",
        "learned_preference": "learned preference",
        "diversity": "artist diversity",
    }
    requested = [labels[name] for name, value in boosts.as_dict().items() if value > 0]
    if requested:
        emphasis = " You asked it to emphasize " + ", ".join(requested) + "."
    else:
        emphasis = " Balanced recommendation weights are active."
    dominant = max(effective_weights, key=effective_weights.get)
    outcome = (
        f" The next track is ranked from the same evidence, with {labels[dominant]} "
        f"carrying the largest effective weight."
    )
    return opening + emphasis + outcome
