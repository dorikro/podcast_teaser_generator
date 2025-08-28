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

# In-memory task registry (ephemeral; acceptable for single-instance dev use)
background_tasks: dict[str, asyncio.Task] = {}

def _fs_to_web_path(path: str | None) -> str | None:
    """Convert absolute filesystem path under output_dir into web path served at /output.
    Returns None if path is None or outside output_dir.
    """
    if not path:
        return None
    try:
        import os
        root = os.path.abspath(settings.output_dir)
        ap = os.path.abspath(path)
        if not ap.startswith(root):
            return None
        rel = os.path.relpath(ap, root)
        return f"/output/{rel}".replace('//', '/')
    except Exception:
        return None

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
    force: bool = False  # force regenerate all artifacts

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
                "song_title": "<Enter Song Title>",
                "artist": "<Enter Artist>",
                "surprising_insight": "Insert a little-known or misunderstood lyric element that reveals hidden meaning.",
                "emotional_angle": "Describe the deeper emotional context or personal journey the song reflects.",
                "curiosity_hook": "Pose a question that makes the listener want to hear the full story.",
                "tone_field": "curious, energetic, inviting",
                "audience_field": "music fans 18–35 who love storytelling in music",
                "output_desc": "${DURATION}s punchy spoken teaser",
            },
        },
    )

@router.post("/api/generate", response_class=JSONResponse)
async def api_generate(data: GenerationRequest):
    """Kick off generation. For mode=full, video + compose happen in background so the
    HTTP response returns promptly (prevents long-poll hang). Frontend should poll /api/status."""
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
        force=data.force,
    )
    _, audio_path = await workflow.step_tts(script_model, language=language, force=data.force)
    audio_url = _fs_to_web_path(audio_path)

    # If only audio requested, return immediately.
    if data.mode == "audio":
        return {
            "project_id": pid,
            "audio_path": audio_path,  # legacy absolute
            "audio_url": audio_url,
            "video_path": None,
            "video_url": None,
            "final_path": None,
            "final_url": None,
            "status": "audio_ready",
        }

    # For full mode, schedule video + compose in background if not already done
    async def run_video_and_compose():
        try:
            await workflow.step_video(script_model, force=data.force)
            await workflow.step_compose(script_model, language=language, force=data.force)
        except Exception as e:
            # Log; status endpoint will reflect presence/absence of files
            from loguru import logger as _log
            _log.error(f"Background video/compose failed for {pid}: {e}")

    if pid not in background_tasks or background_tasks[pid].done():
        background_tasks[pid] = asyncio.create_task(run_video_and_compose())

    return {
        "project_id": pid,
        "audio_path": audio_path,
        "audio_url": audio_url,
        "video_path": None,
        "video_url": None,
        "final_path": None,
        "final_url": None,
        "status": "processing",
    }


@router.get("/api/status", response_class=JSONResponse)
async def api_status(project_id: str):
    """Return generation status and available asset paths for a given project id."""
    # Reconstruct paths based on hashing logic (same as workflow._stable_id_and_dir)
    # The provided project_id is already the stable id, so we directly inspect output dir.
    from pathlib import Path
    project_dir = Path(settings.output_dir) / project_id
    audio_target = project_dir / f"audio.{settings.output_audio_format}"
    video_target = project_dir / f"video.{settings.output_video_format}"
    final_target = project_dir / f"final.{settings.output_video_format}"

    def present(p: Path, min_size: int = 1):
        return p.exists() and p.stat().st_size >= min_size

    audio_path = str(audio_target) if present(audio_target, 1) else None
    video_path = str(video_target) if present(video_target, 1024) else None
    final_path = str(final_target) if present(final_target, 1024) else None
    audio_url = _fs_to_web_path(audio_path)
    video_url = _fs_to_web_path(video_path)
    final_url = _fs_to_web_path(final_path)

    task = background_tasks.get(project_id)
    task_state = None
    if task:
        if task.cancelled():
            task_state = "cancelled"
        elif task.done():
            task_state = "done"
        else:
            task_state = "running"

    if final_path:
        status = "completed"
    elif video_path:
        status = "video_ready"
    elif audio_path:
        status = "audio_ready"
    else:
        status = "pending"

    return {
        "project_id": project_id,
        "status": status,
        "task_state": task_state,
        "audio_path": audio_path,
        "video_path": video_path,
        "final_path": final_path,
        "audio_url": audio_url,
        "video_url": video_url,
        "final_url": final_url,
    }
