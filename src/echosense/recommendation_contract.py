from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from echosense.providers import RecommendationCandidate
from echosense.providers.models import Track
from echosense.recording_identity import IdentityResolution, RecordingReference

PROVIDER_NEUTRAL_PROVIDER = "echosense"


def canonical_track_id_for_provider_item(provider: str, provider_item_id: str) -> str:
    """Stable fallback identity when only provider candidate IDs are available."""

    if not provider.strip() or not provider_item_id.strip():
        raise ValueError("Provider identity is required")
    key = f"{provider}:{provider_item_id}"
    return f"es_recording_{uuid5(NAMESPACE_URL, key).hex}"


@dataclass(frozen=True)
class ProviderTrackBinding:
    """A provider-specific playable representation of one canonical recording."""

    provider: str
    provider_track_id: str
    canonical_track_id: str
    playable: bool = True
    uri: str | None = None
    external_url: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("Provider is required")
        if not self.provider_track_id.strip():
            raise ValueError("Provider track identity is required")
        if not self.canonical_track_id.strip():
            raise ValueError("Canonical track identity is required")


@dataclass(frozen=True)
class CanonicalRecommendation:
    """EchoSense-owned recommendation with an optional playback-provider binding."""

    canonical_track_id: str
    decision_id: str
    rank: int
    score: float
    explanation: str
    provider_bindings: tuple[ProviderTrackBinding, ...] = ()

    @property
    def provider_binding(self) -> ProviderTrackBinding | None:
        return self.provider_bindings[0] if self.provider_bindings else None

    def __post_init__(self) -> None:
        if not self.canonical_track_id.strip():
            raise ValueError("Canonical track identity is required")
        if not self.decision_id.strip():
            raise ValueError("Decision identity is required")
        if self.rank < 1:
            raise ValueError("Recommendation rank must be positive")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("Recommendation score must be between 0 and 1")
        for binding in self.provider_bindings:
            if binding.canonical_track_id != self.canonical_track_id:
                raise ValueError("Provider binding must resolve the recommended canonical track")

    def as_dict(self) -> dict[str, object]:
        bindings = [binding_as_dict(binding) for binding in self.provider_bindings]
        return {
            "canonical_track_id": self.canonical_track_id,
            "decision_id": self.decision_id,
            "rank": self.rank,
            "score": self.score,
            "explanation": self.explanation,
            "provider_binding": bindings[0] if bindings else None,
            "provider_bindings": bindings,
        }


def binding_as_dict(binding: ProviderTrackBinding) -> dict[str, object]:
    return {
        "provider": binding.provider,
        "provider_track_id": binding.provider_track_id,
        "canonical_track_id": binding.canonical_track_id,
        "playable": binding.playable,
        "uri": binding.uri,
        "external_url": binding.external_url,
    }


def learning_key(canonical_track_id: str) -> tuple[str, str]:
    return (PROVIDER_NEUTRAL_PROVIDER, canonical_track_id)


def candidate_canonical_track_id(candidate: RecommendationCandidate) -> str:
    return candidate.canonical_track_id or canonical_track_id_for_provider_item(
        candidate.provider, candidate.item_id
    )


def binding_from_candidate(candidate: RecommendationCandidate) -> ProviderTrackBinding:
    return ProviderTrackBinding(
        provider=candidate.provider,
        provider_track_id=candidate.item_id,
        canonical_track_id=candidate_canonical_track_id(candidate),
    )


def recommendation_from_candidate(
    candidate: RecommendationCandidate,
    *,
    decision_id: str,
    rank: int,
    score: float,
    explanation: str,
) -> CanonicalRecommendation:
    canonical_track_id = candidate_canonical_track_id(candidate)
    return CanonicalRecommendation(
        canonical_track_id=canonical_track_id,
        decision_id=decision_id,
        rank=rank,
        score=max(0.0, min(1.0, score)),
        explanation=explanation,
        provider_bindings=(binding_from_candidate(candidate),),
    )


def recording_reference_from_track(track: Track) -> RecordingReference:
    """Convert provider metadata into the canonical identity registry contract."""

    return RecordingReference(
        provider=track.provider,
        provider_id=track.provider_id,
        title=track.title,
        artists=track.artists,
        album=track.album,
        isrc=track.isrc,
        duration_ms=track.duration_ms,
    )


def binding_from_resolution(
    track: Track,
    resolution: IdentityResolution,
    *,
    playable: bool = True,
    uri: str | None = None,
) -> ProviderTrackBinding:
    """Attach provider playback identity only after canonical resolution."""

    return ProviderTrackBinding(
        provider=track.provider,
        provider_track_id=track.provider_id,
        canonical_track_id=resolution.canonical_id,
        playable=playable,
        uri=uri,
        external_url=track.external_url,
    )
