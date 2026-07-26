from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from echosense.apple_auth import AppleDeveloperTokenProvider

router = APIRouter(prefix="/v1/providers/apple-music", tags=["apple-music"])


class AppleMusicWebConfiguration(BaseModel):
    configured: bool
    developer_token: str | None = None
    app_name: str = "EchoSense"
    app_build: str = "0.1.0"


@router.get("/config", response_model=AppleMusicWebConfiguration)
def apple_music_web_configuration() -> AppleMusicWebConfiguration:
    """Return the short-lived browser configuration required by MusicKit JS.

    The private signing key never leaves the server. When credentials are not
    configured, the UI receives an explicit disabled state instead of a 500.
    """
    try:
        token = AppleDeveloperTokenProvider.from_environment().token()
    except (KeyError, ValueError, OSError):
        return AppleMusicWebConfiguration(configured=False)

    return AppleMusicWebConfiguration(configured=True, developer_token=token)
