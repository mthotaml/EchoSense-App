import pytest

from echosense.listening_intelligence_store import ListeningIntelligenceStore
from echosense.recording_identity import RecordingReference
from echosense.storage import Storage


def test_provider_accounts_and_tracks_resolve_to_canonical_echo_ids(tmp_path) -> None:
    store = ListeningIntelligenceStore(Storage(f"sqlite:///{tmp_path / 'identity.db'}"))
    spotify_user = store.resolve_user(
        provider="spotify",
        provider_user_id="spotify-listener",
        display_name="Listener",
    )
    apple_user = store.resolve_user(
        provider="apple_music",
        provider_user_id="apple-listener",
        echo_user_id=spotify_user.echo_user_id,
    )
    spotify_track = store.observe_track(
        RecordingReference(
            provider="spotify",
            provider_id="spotify-track",
            title="Open Road",
            artists=("Echo Artist",),
            album="Signals",
            isrc="USAAA2600001",
            duration_ms=180_000,
        )
    )
    apple_track = store.observe_track(
        RecordingReference(
            provider="apple_music",
            provider_id="apple-track",
            title="Open Road",
            artists=("Echo Artist",),
            album="Signals",
            isrc="USAAA2600001",
            duration_ms=180_400,
        )
    )

    assert apple_user.echo_user_id == spotify_user.echo_user_id
    assert spotify_user.echo_user_id.startswith("es_user_")
    assert spotify_track == apple_track
    assert spotify_track.startswith("es_recording_")


def test_events_are_idempotent_and_update_listener_intelligence(tmp_path) -> None:
    store = ListeningIntelligenceStore(Storage(f"sqlite:///{tmp_path / 'events.db'}"))
    identity = store.resolve_user(provider="spotify", provider_user_id="listener")
    track_id = store.observe_track(
        RecordingReference(
            provider="spotify",
            provider_id="track-one",
            title="Open Road",
            artists=("Echo Artist",),
        )
    )
    session_id = store.ensure_session(
        echo_user_id=identity.echo_user_id,
        provider="spotify",
        provider_session_id="provider-session",
        context={"moment": "driving"},
    )

    first = store.record_event(
        event_id="event-completed",
        echo_user_id=identity.echo_user_id,
        echo_track_id=track_id,
        provider="spotify",
        provider_track_id="track-one",
        event_type="completed",
        context="moment:driving",
        decision_id="decision-one",
        listening_session_id=session_id,
        playback_seconds=180,
        completion_ratio=0.98,
    )
    duplicate = store.record_event(
        event_id="event-completed",
        echo_user_id=identity.echo_user_id,
        echo_track_id=track_id,
        provider="spotify",
        provider_track_id="track-one",
        event_type="completed",
        context="moment:driving",
        decision_id="decision-one",
        listening_session_id=session_id,
        playback_seconds=180,
        completion_ratio=0.98,
    )
    store.record_event(
        event_id="event-liked",
        echo_user_id=identity.echo_user_id,
        echo_track_id=track_id,
        provider="spotify",
        provider_track_id="track-one",
        event_type="liked",
        context="moment:driving",
        decision_id="decision-one",
        listening_session_id=session_id,
    )

    snapshot = store.listener_snapshot(identity.echo_user_id)
    product = store.product_kpis()

    assert first.applied is True
    assert duplicate.applied is False
    assert snapshot["scope"] == "provider_neutral_listener"
    assert snapshot["summary"]["events"] == 2
    assert snapshot["summary"]["listen_seconds"] == 180
    assert snapshot["summary"]["completion_rate"] == 100
    assert snapshot["top_tracks"][0]["preference_score"] == 0.2
    assert product == {
        "listeners": 1,
        "sessions": 1,
        "events": 2,
        "listen_seconds": 180.0,
        "completion_rate": 100,
        "skip_rate": 0,
    }


def test_event_id_cannot_be_rebound_to_different_evidence(tmp_path) -> None:
    store = ListeningIntelligenceStore(Storage(f"sqlite:///{tmp_path / 'rebind.db'}"))
    identity = store.resolve_user(provider="spotify", provider_user_id="listener")
    track_id = store.observe_track(
        RecordingReference("spotify", "track-one", "Open Road", ("Echo Artist",))
    )
    store.record_event(
        event_id="event-one",
        echo_user_id=identity.echo_user_id,
        echo_track_id=track_id,
        provider="spotify",
        provider_track_id="track-one",
        event_type="completed",
        context="general",
    )

    with pytest.raises(ValueError, match="different evidence"):
        store.record_event(
            event_id="event-one",
            echo_user_id=identity.echo_user_id,
            echo_track_id=track_id,
            provider="spotify",
            provider_track_id="track-one",
            event_type="skipped",
            context="general",
        )
