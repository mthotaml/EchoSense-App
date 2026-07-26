from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from echosense.storage import Storage


@dataclass
class ProviderConnection:
    session_id: str
    provider: str
    provider_user_id: str
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    profile: dict[str, object]


class ProviderConnectionRepository:
    """Persist provider credentials encrypted at rest."""

    def __init__(
        self,
        storage: Storage,
        encryption_key: str | bytes | Sequence[str | bytes],
    ) -> None:
        keys = (
            list(encryption_key)
            if not isinstance(encryption_key, (str, bytes))
            else [encryption_key]
        )
        if not keys:
            raise ValueError("At least one token-encryption key is required")
        self.storage = storage
        self.fernet = MultiFernet(
            [Fernet(key.encode() if isinstance(key, str) else key) for key in keys]
        )

    def save(self, connection: ProviderConnection) -> None:
        self.storage.upsert_provider_connection(
            session_id=connection.session_id,
            provider=connection.provider,
            provider_user_id=connection.provider_user_id,
            encrypted_access_token=self._encrypt(connection.access_token),
            encrypted_refresh_token=self._encrypt(connection.refresh_token),
            expires_at=connection.expires_at,
            profile=connection.profile,
        )

    def get(self, session_id: str, provider: str) -> ProviderConnection | None:
        payload = self.storage.get_provider_connection(session_id, provider)
        if payload is None:
            return None
        try:
            return ProviderConnection(
                session_id=payload["session_id"],
                provider=payload["provider"],
                provider_user_id=payload["provider_user_id"],
                access_token=self._decrypt(payload["encrypted_access_token"]) or "",
                refresh_token=self._decrypt(payload["encrypted_refresh_token"]),
                expires_at=datetime.fromisoformat(payload["expires_at"]),
                profile=payload["profile"],
            )
        except InvalidToken as exc:
            raise RuntimeError("Stored provider credentials cannot be decrypted") from exc

    def revoke(self, session_id: str, provider: str) -> bool:
        return self.storage.revoke_provider_connection(session_id, provider)

    def _encrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        return self.fernet.encrypt(value.encode()).decode()

    def _decrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        return self.fernet.decrypt(value.encode()).decode()

    @classmethod
    def from_environment(cls) -> ProviderConnectionRepository:
        configured_keys = os.getenv("ECHOSENSE_TOKEN_ENCRYPTION_KEYS")
        keys = (
            [key.strip() for key in configured_keys.split(",") if key.strip()]
            if configured_keys
            else [os.environ["ECHOSENSE_TOKEN_ENCRYPTION_KEY"]]
        )
        return cls(
            Storage(),
            keys,
        )
