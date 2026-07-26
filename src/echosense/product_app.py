from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault(
    "SPOTIFY_SCOPES",
    "user-top-read user-read-recently-played user-read-email user-read-private "
    "streaming user-read-playback-state user-modify-playback-state",
)

from echosense.app import create_app

app = create_app("product")
