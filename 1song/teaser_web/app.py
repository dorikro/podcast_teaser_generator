"""FastAPI application entrypoint for the teaser web UI."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from .routers import ui

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


def run():  # console script entry point
    import uvicorn
    uvicorn.run("teaser_web.app:app", host="0.0.0.0", port=8000, reload=True)
