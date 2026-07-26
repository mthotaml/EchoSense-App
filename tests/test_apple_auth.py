from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from echosense.apple_auth import AppleDeveloperTokenProvider, AppleUserTokenVault
from echosense.storage import Storage


def private_key_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def test_developer_token_is_es256_and_cached() -> None:
    now = datetime(2026, 7, 20, tzinfo=timezone.utc)
    provider = AppleDeveloperTokenProvider(
        team_id="TEAMID1234",
        key_id="KEYID12345",
        private_key=private_key_pem(),
        now=lambda: now,
    )

    first = provider.token()
    second = provider.token()
    header = jwt.get_unverified_header(first)
    claims = jwt.decode(first, options={"verify_signature": False})

    assert first == second
    assert header["alg"] == "ES256"
    assert header["kid"] == "KEYID12345"
    assert claims["iss"] == "TEAMID1234"
    assert claims["exp"] - claims["iat"] == int(timedelta(hours=12).total_seconds())


def test_user_token_is_encrypted_and_revocable(tmp_path: Path) -> None:
    storage = Storage(f"sqlite:///{tmp_path / 'tokens.db'}")
    vault = AppleUserTokenVault(storage, Fernet.generate_key())

    vault.store("user-1", "music-user-token-secret")
    encrypted = storage.get_apple_music_user_token("user-1")

    assert encrypted is not None
    assert "music-user-token-secret" not in encrypted
    assert vault.retrieve("user-1") == "music-user-token-secret"
    assert vault.revoke("user-1") is True
    assert vault.retrieve("user-1") is None
