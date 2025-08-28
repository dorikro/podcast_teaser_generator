"""FastAPI application entrypoint for the teaser web UI.

Adds mounts for:
 - /static  -> web UI assets
 - /output  -> generated project assets (audio/video/final)
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from .routers import ui
from podcast_teaser_generator.config import settings
import os, sys

app = FastAPI(title="Podcast Teaser Generator UI", version="0.1.0")

# CORS (adjust as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ui.router)
app.mount("/static", StaticFiles(directory="teaser_web/static"), name="static")
# Serve generated teaser assets (audio/video/final compositions)
app.mount("/output", StaticFiles(directory=settings.output_dir), name="output")


def run():  # console script entry point
    """Launch the FastAPI web UI.

    Supports optional CLI args:
      --port / -p <int>
      --host / -H <str>
      --no-reload (disable auto-reload)

    Also honors environment variables PORT and HOST if flags omitted.
    """
    import uvicorn

    # Very lightweight manual arg parsing to avoid adding dependencies
    argv = sys.argv[1:]
    def _extract(flag_names, default=None):
        for i, a in enumerate(argv):
            if a in flag_names and i + 1 < len(argv):
                try:
                    return argv[i + 1]
                except Exception:
                    return default
        return default

    host = _extract(["--host", "-H"], os.environ.get("HOST", "0.0.0.0"))
    port_raw = _extract(["--port", "-p"], os.environ.get("PORT", "8000"))
    try:
        port = int(port_raw)
    except ValueError:
        port = 8000
    reload_flag = "--no-reload" not in argv

    uvicorn.run("teaser_web.app:app", host=host, port=port, reload=reload_flag)
