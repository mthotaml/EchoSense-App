from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Callable

import jwt
from cryptography.fernet import Fernet, InvalidToken

from echosense.storage import Storage


class AppleDeveloperTokenProvider:
    """Generate and cache Apple Music ES256 developer tokens."""

    def __init__(
        self,
        team_id: str,
        key_id: str,
        private_key: str,
        ttl: timedelta = timedelta(hours=12),
        refresh_skew: timedelta = timedelta(minutes=5),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not team_id or not key_id or not private_key:
            raise ValueError("Apple Music team ID, key ID and private key are required")
        if ttl <= timedelta(0) or ttl > timedelta(days=180):
            raise ValueError("Apple Music developer-token TTL must be between 0 and 180 days")
        self.team_id = team_id
        self.key_id = key_id
        self.private_key = private_key
        self.ttl = ttl
        self.refresh_skew = refresh_skew
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._token: str | None = None
        self._expires_at: datetime | None = None
        self._lock = Lock()

    def token(self) -> str:
        current = self.now()
        with self._lock:
            if self._token and self._expires_at and current < self._expires_at - self.refresh_skew:
                return self._token
            expires_at = current + self.ttl
            self._token = jwt.encode(
                {"iss": self.team_id, "iat": int(current.timestamp()), "exp": int(expires_at.timestamp())},
                self.private_key,
                algorithm="ES256",
                headers={"kid": self.key_id},
            )
            self._expires_at = expires_at
            return self._token

    @classmethod
    def from_environment(cls) -> AppleDeveloperTokenProvider:
        private_key = os.getenv("APPLE_MUSIC_PRIVATE_KEY")
        private_key_path = os.getenv("APPLE_MUSIC_PRIVATE_KEY_PATH")
        if not private_key and private_key_path:
            private_key = Path(private_key_path).read_text()
        return cls(
            team_id=os.environ["APPLE_MUSIC_TEAM_ID"],
            key_id=os.environ["APPLE_MUSIC_KEY_ID"],
            private_key=private_key or "",
            ttl=timedelta(seconds=int(os.getenv("APPLE_MUSIC_TOKEN_TTL_SECONDS", "43200"))),
        )


class AppleUserTokenVault:
    """Encrypt Music User Tokens before persistence and never expose ciphertext to callers."""

    def __init__(self, storage: Storage, encryption_key: str | bytes) -> None:
        key = encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
        self.storage = storage
        self.fernet = Fernet(key)

    def store(self, user_id: str, token: str) -> None:
        if not token.strip():
            raise ValueError("Music User Token cannot be empty")
        encrypted = self.fernet.encrypt(token.encode()).decode()
        self.storage.upsert_apple_music_user_token(user_id, encrypted)

    def retrieve(self, user_id: str) -> str | None:
        encrypted = self.storage.get_apple_music_user_token(user_id)
        if encrypted is None:
            return None
        try:
            return self.fernet.decrypt(encrypted.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("Stored Apple Music user token cannot be decrypted") from exc

    def revoke(self, user_id: str) -> bool:
        return self.storage.revoke_apple_music_user_token(user_id)

    @classmethod
    def from_environment(cls, storage: Storage) -> AppleUserTokenVault:
        return cls(storage, os.environ["ECHOSENSE_TOKEN_ENCRYPTION_KEY"])
