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
    # Deprecated individual fields (language, gender) now inferred from voice_name; kept for backward compat
    language: str | None = None
    gender: str | None = None
    voice_name: str | None = None  # e.g. en-US-JennyNeural
    mode: str = "audio"  # audio or full

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "defaults": {
                "title": "Demo Episode",
                "prompt": (
                    "<TeaserTemplate>\n"
                    "  <Episode>\n"
                    "    <SongTitle>{SONG_TITLE}</SongTitle>\n"
                    "    <Artist>{ARTIST}</Artist>\n"
                    "  </Episode>\n\n"
                    "  <Content>\n"
                    "    <SurprisingInsight>\n"
                    "      {SURPRISING_LYRIC_INSIGHT}\n"
                    "    </SurprisingInsight>\n\n"
                    "    <EmotionalAngle>\n"
                    "      {EMOTIONAL_ANGLE}\n"
                    "    </EmotionalAngle>\n\n"
                    "    <CuriosityHook>\n"
                    "      {HOOK_QUESTION}\n"
                    "    </CuriosityHook>\n"
                    "  </Content>\n\n"
                    "  <Tone>\n"
                    "    curious, energetic, inviting\n"
                    "  </Tone>\n\n"
                    "  <Audience>\n"
                    "    music fans 18–35 who love storytelling in music\n"
                    "  </Audience>\n\n"
                    "  <Output>\n"
                    "    15s punchy spoken teaser\n"
                    "  </Output>\n"
                    "</TeaserTemplate>"
                ),
                "headline": "Catchy Headline Here",
                "duration": 15,
                "voice_name": settings.azure_speech_voice or "en-US-JennyNeural",
                # Structured template defaults
                "song_title": "Fix You",
                "artist": "Coldplay",
                "surprising_insight": "The 'lights will guide you home' line was originally a placeholder lyric that became the emotional core.",
                "emotional_angle": "A quiet promise of support during private grief rather than a generic stadium anthem.",
                "curiosity_hook": "What secret moment in Chris's life shaped that soaring final build?",
                "tone_field": "curious, energetic, inviting",
                "audience_field": "music fans 18–35 who love storytelling in music",
                "output_desc": "15s punchy spoken teaser",
            },
        },
    )

@router.post("/api/generate", response_class=JSONResponse)
async def api_generate(data: GenerationRequest):
    workflow = TeaserGenerationWorkflow()

    # Derive language & gender from voice_name (single dropdown parameter)
    voice = data.voice_name or settings.azure_speech_voice or "en-US-JennyNeural"
    # Language is first two hyphen-separated parts (e.g. en-US, he-IL)
    parts = voice.split("-")
    language = "-".join(parts[0:2]) if len(parts) >= 2 else (data.language or settings.azure_speech_language or "en-US")
    gender_map = {
        "en-US-JennyNeural": "female",
        "en-US-SaraNeural": "female",
        "en-US-GuyNeural": "male",
        "he-IL-HilaNeural": "female",
        "he-IL-AvriNeural": "male",
    }
    inferred_gender = gender_map.get(voice)

    # Build script model for stable ID and subsequent steps
    content_text = data.script or data.prompt or ""
    script_model = PodcastScript(title=data.title, content=content_text)

    # Step 1: teaser content + audio (stores voice metadata)
    # Ensure global settings reflects language so prompt generation outputs correct language
    try:
        from podcast_teaser_generator.config import settings as global_settings
        global_settings.azure_speech_language = language
    except Exception:
        pass
    pid, _ = await workflow.step_generate_from_input(
        title=data.title,
        prompt=data.prompt,
        full_script=data.script,
        headline=data.headline,
        target_duration=data.duration,
        language=language,
        voice_gender=inferred_gender,
        voice_name=voice,
        force=False,
    )
    _, audio_path = await workflow.step_tts(script_model, language=language, force=False)

    video_path = None
    final_path = None
    if data.mode == "full":
        _, video_path = await workflow.step_video(script_model, force=False)
        _, final_path = await workflow.step_compose(script_model, language=language, force=False)

    return {
        "project_id": pid,
        "audio_path": audio_path,
        "video_path": video_path,
        "final_path": final_path,
    }
