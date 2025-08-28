"""UI routes for teaser generation."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import asyncio
from podcast_teaser_generator.workflow import TeaserGenerationWorkflow
from podcast_teaser_generator.models import PodcastScript
from podcast_teaser_generator.config import settings

templates = Jinja2Templates(directory="teaser_web/templates")
router = APIRouter()

class GenerationRequest(BaseModel):
    title: str
    prompt: str | None = None
    script: str | None = None
    headline: str | None = None
    duration: int = 15
    language: str = "en-US"
    gender: str | None = None
    voice_name: str | None = None
    mode: str = "audio"  # audio or full

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "defaults": {
                "title": "Demo Episode",
                "prompt": "Short description of the episode topic",
                "headline": "Catchy Headline Here",
                "duration": 15,
                "language": settings.azure_speech_language or "en-US",
                "gender": "auto",
            },
        },
    )

@router.post("/api/generate", response_class=JSONResponse)
async def api_generate(data: GenerationRequest):
    workflow = TeaserGenerationWorkflow()
    # Build script model for stable ID and subsequent steps
    content_text = data.script or data.prompt or ""
    script_model = PodcastScript(title=data.title, content=content_text)

    # Step 1: teaser content + audio
    pid, _ = await workflow.step_generate_from_input(
        title=data.title,
        prompt=data.prompt,
        full_script=data.script,
        headline=data.headline,
        target_duration=data.duration,
        language=data.language,
        voice_gender=None if data.gender == "auto" else data.gender,
        voice_name=data.voice_name,
        force=False,
    )
    _, audio_path = await workflow.step_tts(script_model, language=data.language, force=False)

    video_path = None
    final_path = None
    if data.mode == "full":
        _, video_path = await workflow.step_video(script_model, force=False)
        _, final_path = await workflow.step_compose(script_model, language=data.language, force=False)

    return {
        "project_id": pid,
        "audio_path": audio_path,
        "video_path": video_path,
        "final_path": final_path,
    }
