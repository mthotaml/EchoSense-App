from __future__ import annotations

import pytest

from echosense.providers.models import Track
from echosense.recommendation_contract import (
    CanonicalRecommendation,
    ProviderTrackBinding,
    binding_from_resolution,
    canonical_track_id_for_provider_item,
    learning_key,
    recording_reference_from_track,
    resolve_provider_binding,
)
from echosense.recording_identity import IdentityResolution


def spotify_track() -> Track:
    return Track(
        provider="spotify",
        provider_id="spotify-track-123",
        title="Night Drive",
        artists=("Echo Avenue",),
        album="City Lights",
        popularity=72,
        external_url="https://open.spotify.com/track/spotify-track-123",
        isrc="USABC2600001",
        duration_ms=218_000,
    )


def test_provider_track_is_normalized_into_recording_identity_contract() -> None:
    reference = recording_reference_from_track(spotify_track())

    assert reference.provider == "spotify"
    assert reference.provider_id == "spotify-track-123"
    assert reference.title == "Night Drive"
    assert reference.artists == ("Echo Avenue",)
    assert reference.isrc == "USABC2600001"
    assert reference.duration_ms == 218_000


def test_provider_binding_keeps_playback_identity_outside_canonical_identity() -> None:
    track = spotify_track()
    resolution = IdentityResolution(
        canonical_id="es_recording_canonical123",
        status="matched",
        confidence=0.99,
        method="isrc",
    )

    binding = binding_from_resolution(
        track,
        resolution,
        uri="spotify:track:spotify-track-123",
    )

    assert binding.canonical_track_id == "es_recording_canonical123"
    assert binding.provider == "spotify"
    assert binding.provider_track_id == "spotify-track-123"
    assert binding.uri == "spotify:track:spotify-track-123"


def test_recommendation_identity_is_owned_by_echosense() -> None:
    binding = ProviderTrackBinding(
        provider="spotify",
        provider_track_id="spotify-track-123",
        canonical_track_id="es_recording_canonical123",
        uri="spotify:track:spotify-track-123",
    )

    recommendation = CanonicalRecommendation(
        canonical_track_id="es_recording_canonical123",
        decision_id="dec_contract123",
        rank=1,
        score=0.91,
        explanation="Fits the current driving context and learned listening pattern.",
        provider_bindings=(binding,),
    )

    payload = recommendation.as_dict()

    assert payload["canonical_track_id"] == "es_recording_canonical123"
    assert payload["decision_id"] == "dec_contract123"
    assert payload["provider_binding"]["provider"] == "spotify"
    assert payload["provider_binding"]["provider_track_id"] == "spotify-track-123"
    assert payload["provider_bindings"] == [payload["provider_binding"]]


def test_same_canonical_recommendation_can_resolve_to_another_provider() -> None:
    spotify = ProviderTrackBinding(
        provider="spotify",
        provider_track_id="spotify-track-123",
        canonical_track_id="es_recording_canonical123",
    )
    apple = ProviderTrackBinding(
        provider="apple_music",
        provider_track_id="apple-song-987",
        canonical_track_id="es_recording_canonical123",
    )

    spotify_recommendation = CanonicalRecommendation(
        canonical_track_id="es_recording_canonical123",
        decision_id="dec_cross_provider",
        rank=1,
        score=0.88,
        explanation="Canonical EchoSense recommendation.",
        provider_bindings=(spotify,),
    )
    apple_recommendation = CanonicalRecommendation(
        canonical_track_id="es_recording_canonical123",
        decision_id="dec_cross_provider",
        rank=1,
        score=0.88,
        explanation="Canonical EchoSense recommendation.",
        provider_bindings=(apple,),
    )

    assert spotify_recommendation.canonical_track_id == apple_recommendation.canonical_track_id
    assert (
        spotify_recommendation.provider_binding.provider_track_id
        != apple_recommendation.provider_binding.provider_track_id
    )


def test_resolver_selects_preferred_playable_provider_binding() -> None:
    spotify = ProviderTrackBinding(
        provider="spotify",
        provider_track_id="spotify-track-123",
        canonical_track_id="es_recording_canonical123",
        playable=False,
    )
    apple = ProviderTrackBinding(
        provider="apple_music",
        provider_track_id="apple-song-987",
        canonical_track_id="es_recording_canonical123",
    )
    recommendation = CanonicalRecommendation(
        canonical_track_id="es_recording_canonical123",
        decision_id="dec_resolver",
        rank=1,
        score=0.88,
        explanation="Canonical EchoSense recommendation.",
        provider_bindings=(spotify, apple),
    )

    assert resolve_provider_binding(recommendation, "apple_music") == apple
    assert resolve_provider_binding(recommendation, "spotify") is None
    assert resolve_provider_binding(recommendation, "spotify", require_playable=False) == spotify
    assert resolve_provider_binding(recommendation) == apple


def test_recommendation_rejects_binding_for_different_canonical_track() -> None:
    binding = ProviderTrackBinding(
        provider="spotify",
        provider_track_id="spotify-track-123",
        canonical_track_id="es_recording_other",
    )

    with pytest.raises(ValueError, match="must resolve the recommended canonical track"):
        CanonicalRecommendation(
            canonical_track_id="es_recording_expected",
            decision_id="dec_invalid",
            rank=1,
            score=0.8,
            explanation="Invalid cross-recording binding.",
            provider_bindings=(binding,),
        )


def test_fallback_learning_key_is_echosense_owned_not_provider_owned() -> None:
    canonical_track_id = canonical_track_id_for_provider_item("spotify", "spotify-track-123")

    assert canonical_track_id.startswith("es_recording_")
    assert learning_key(canonical_track_id) == ("echosense", canonical_track_id)
    assert canonical_track_id == canonical_track_id_for_provider_item(
        "spotify", "spotify-track-123"
    )
