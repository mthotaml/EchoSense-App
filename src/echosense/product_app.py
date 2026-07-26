from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault(
    "SPOTIFY_SCOPES",
    "user-top-read user-read-recently-played user-read-email user-read-private "
    "streaming user-read-playback-state user-modify-playback-state",
)

from echosense.app import app
from echosense.player_routes import router as player_router
from echosense.product_ui import router as product_ui_router
from echosense.spotify_auth import router as spotify_auth_router

app.include_router(spotify_auth_router)
app.include_router(player_router)
app.include_router(product_ui_router)
