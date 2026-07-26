from echosense.recording_identity import RecordingIdentityRegistry, RecordingReference
from echosense.storage import Storage


def reference(
    provider: str,
    provider_id: str,
    *,
    title: str = "Midnight Drive",
    artist: str = "Echo Avenue",
    album: str = "City Lights",
    isrc: str | None = None,
    duration_ms: int | None = 201000,
) -> RecordingReference:
    return RecordingReference(
        provider,
        provider_id,
        title,
        (artist,),
        album,
        isrc,
        duration_ms,
    )


def registry(tmp_path) -> RecordingIdentityRegistry:
    return RecordingIdentityRegistry(Storage(f"sqlite:///{tmp_path / 'identity.db'}"))


def test_exact_isrc_links_spotify_and_apple_music(tmp_path) -> None:
    identities = registry(tmp_path)
    spotify = identities.resolve(reference("spotify", "sp-1", isrc="USABC1234567"))
    apple = identities.resolve(reference("apple_music", "am-1", isrc="usabc1234567"))

    assert apple.canonical_id == spotify.canonical_id
    assert apple.status == "matched"
    assert apple.method == "isrc"
    assert apple.confidence == 0.99


def test_missing_isrc_uses_conservative_metadata_fallback(tmp_path) -> None:
    identities = registry(tmp_path)
    spotify = identities.resolve(reference("spotify", "sp-1"))
    apple = identities.resolve(reference("apple_music", "am-1", duration_ms=202500))

    assert apple.canonical_id == spotify.canonical_id
    assert apple.method == "metadata"
    assert apple.confidence >= 0.9


def test_live_and_remastered_versions_do_not_merge(tmp_path) -> None:
    identities = registry(tmp_path)
    studio = identities.resolve(reference("spotify", "studio", isrc="USABC1234567"))
    live = identities.resolve(
        reference(
            "apple_music",
            "live",
            title="Midnight Drive (Live)",
            album="City Lights Live",
            isrc="USABC1234567",
        )
    )
    remaster = identities.resolve(
        reference(
            "apple_music",
            "remaster",
            title="Midnight Drive - 2026 Remastered",
            isrc="USABC1234567",
        )
    )

    assert len({studio.canonical_id, live.canonical_id, remaster.canonical_id}) == 3


def test_cover_with_same_title_and_conflicting_isrc_metadata_stays_separate(tmp_path) -> None:
    identities = registry(tmp_path)
    original = identities.resolve(reference("spotify", "original", isrc="USABC1234567"))
    cover = identities.resolve(
        reference(
            "apple_music",
            "cover",
            artist="Different Artist",
            isrc="USABC1234567",
        )
    )

    assert cover.canonical_id != original.canonical_id


def test_tied_metadata_candidates_are_reported_as_ambiguous(tmp_path) -> None:
    identities = registry(tmp_path)
    first = identities.resolve(reference("spotify", "one", duration_ms=None))
    second = identities.resolve(
        reference("apple_music", "two", album="Another Album", duration_ms=260000)
    )
    third = identities.resolve(reference("tidal", "three", album="Third Album", duration_ms=None))

    assert second.canonical_id != first.canonical_id
    assert third.status == "ambiguous"
    assert set(third.candidate_ids) == {first.canonical_id, second.canonical_id}
    assert third.canonical_id not in third.candidate_ids


def test_provider_alias_resolution_is_idempotent(tmp_path) -> None:
    identities = registry(tmp_path)
    first = identities.resolve(reference("spotify", "sp-1", isrc="USABC1234567"))
    duplicate = identities.resolve(reference("spotify", "sp-1", title="Changed provider metadata"))

    assert duplicate.canonical_id == first.canonical_id
    assert duplicate.status == "existing"
