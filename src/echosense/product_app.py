from __future__ import annotations

import os

from dotenv import load_dotenv

from echosense.spotify_auth import DEFAULT_SCOPES

load_dotenv()
os.environ.setdefault("SPOTIFY_SCOPES", DEFAULT_SCOPES)

from echosense.app import create_app

app = create_app("product")
