from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet

from echosense import spotify_auth
from echosense.repositories.provider_connections import (
    ProviderConnection,
    ProviderConnectionRepository,
)
from echosense.storage import Storage


def _repository(path: Path, key: bytes) -> ProviderConnectionRepository:
    return ProviderConnectionRepository(Storage(f"sqlite:///{path}"), key)


def _connection(*, expires_at: datetime | None = None) -> ProviderConnection:
    return ProviderConnection(
        session_id="durable-session",
        provider="spotify",
        provider_user_id="spotify-user-123",
        access_token="plaintext-access-token",
        refresh_token="plaintext-refresh-token",
        expires_at=expires_at or datetime.now(UTC) + timedelta(hours=1),
        profile={"id": "spotify-user-123", "display_name": "Mohan"},
    )


def test_connection_survives_repository_recreation(tmp_path: Path) -> None:
    database = tmp_path / "connections.db"
    key = Fernet.generate_key()
    _repository(database, key).save(_connection())

    restored = _repository(database, key).get("durable-session", "spotify")

    assert restored is not None
    assert restored.access_token == "plaintext-access-token"
    assert restored.refresh_token == "plaintext-refresh-token"
    assert restored.profile["display_name"] == "Mohan"


def test_tokens_are_not_persisted_in_plaintext(tmp_path: Path) -> None:
    database = tmp_path / "connections.db"
    repository = _repository(database, Fernet.generate_key())
    repository.save(_connection())

    raw_database = database.read_bytes()

    assert b"plaintext-access-token" not in raw_database
    assert b"plaintext-refresh-token" not in raw_database


def test_revoked_connection_cannot_be_restored(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "connections.db", Fernet.generate_key())
    repository.save(_connection())

    assert repository.revoke("durable-session", "spotify") is True
    assert repository.get("durable-session", "spotify") is None


def test_key_rotation_reads_old_tokens_and_reencrypts_with_primary_key(tmp_path: Path) -> None:
    database = tmp_path / "connections.db"
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    old_repository = _repository(database, old_key)
    old_repository.save(_connection())

    rotating_repository = ProviderConnectionRepository(
        Storage(f"sqlite:///{database}"),
        [new_key, old_key],
    )
    restored = rotating_repository.get("durable-session", "spotify")
    assert restored is not None
    rotating_repository.save(restored)

    assert (
        ProviderConnectionRepository(Storage(f"sqlite:///{database}"), new_key).get(
            "durable-session", "spotify"
        )
        is not None
    )
    with pytest.raises(RuntimeError, match="cannot be decrypted"):
        old_repository.get("durable-session", "spotify")


def test_refresh_updates_durable_credentials(tmp_path: Path, monkeypatch) -> None:
    repository = _repository(tmp_path / "connections.db", Fernet.generate_key())
    expired = _connection(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    repository.save(expired)
    monkeypatch.setattr(spotify_auth, "_connection_repository", repository)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "client-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "client-secret")

    def fake_post(*args, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", spotify_auth.SPOTIFY_TOKEN_URL),
            json={"access_token": "rotated-access-token", "expires_in": 3600},
        )

    monkeypatch.setattr(spotify_auth.httpx, "post", fake_post)

    spotify_auth._refresh_session(expired)
    restored = repository.get("durable-session", "spotify")

    assert restored is not None
    assert restored.access_token == "rotated-access-token"
    assert restored.refresh_token == "plaintext-refresh-token"
    assert restored.expires_at > datetime.now(UTC)
