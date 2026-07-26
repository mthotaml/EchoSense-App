from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from echosense.app import app
from echosense.apple_music_sync import router as apple_music_sync_router
from echosense.apple_music_web import router as apple_music_web_router
from echosense.profile_recommendations import router as profile_recommendations_router
from echosense.taste_profile import router as taste_profile_router

UI_DIR = Path(__file__).with_name("web")

app.include_router(apple_music_web_router)
app.include_router(apple_music_sync_router)
app.include_router(taste_profile_router)
app.include_router(profile_recommendations_router)
app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")


@app.get("/", include_in_schema=False)
def cognitive_dashboard() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")
