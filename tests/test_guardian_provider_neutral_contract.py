from pathlib import Path


def test_guardian_provider_neutral_recommendation_contract_exists() -> None:
    contract = Path("src/echosense/recommendation_contract.py").read_text()

    assert "class CanonicalRecommendation" in contract
    assert "canonical_track_id: str" in contract
    assert "class ProviderTrackBinding" in contract
    assert "provider_track_id: str" in contract
    assert "provider_bindings: tuple[ProviderTrackBinding, ...]" in contract
    assert "recording_reference_from_track" in contract
    assert "binding_from_resolution" in contract
    assert "resolve_provider_binding" in contract


def test_guardian_recommendation_contract_separates_decision_from_playback() -> None:
    contract = Path("src/echosense/recommendation_contract.py").read_text()

    canonical_position = contract.index("class CanonicalRecommendation")
    binding_field_position = contract.index(
        "provider_bindings: tuple[ProviderTrackBinding, ...]", canonical_position
    )

    assert canonical_position < binding_field_position
    assert "Provider binding must resolve the recommended canonical track" in contract


def test_guardian_spotify_is_only_a_provider_binding() -> None:
    core_api = Path("src/echosense/app.py").read_text()
    spotify_boundary = Path("src/echosense/spotify_auth.py").read_text()

    assert "learning_key(" in core_api
    assert "candidate_canonical_track_id(candidate)" in core_api
    assert "legacy_provider_bridge" in core_api
    assert "promote_provider_preference" in core_api
    assert '"canonical_track_id": echo_track_id' in spotify_boundary
    assert "ProviderTrackBinding(" in spotify_boundary
    assert "provider_track_id=slate_item.track.provider_id" in spotify_boundary
