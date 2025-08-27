"""Core agentic workflow orchestrator."""

import asyncio
import uuid
from typing import Optional
from loguru import logger

from .models import PodcastScript, TeaserProject, TeaserContent, GeneratedAssets, InputSpec, ScriptAnalysis
from .agents.content_agent import ContentExtractionAgent
from .agents.audio_agent import AudioGenerationAgent
from .agents.video_agent import VideoGenerationAgent
from .agents.compositor_agent import CompositorAgent
from .config import settings
from .mcp_client import mcp_manager

# New imports for resumable workflow
import os
import json
import hashlib
from pathlib import Path


class TeaserGenerationWorkflow:
    """Main workflow orchestrator for teaser generation."""
    
    def __init__(self):
        """Initialize the workflow with all agents."""
        self.content_agent = ContentExtractionAgent()
        self.audio_agent = AudioGenerationAgent()
        self.video_agent = VideoGenerationAgent()
        self.compositor_agent = CompositorAgent()
        self._mcp_initialized = False
    
    async def _ensure_mcp_initialized(self):
        """Ensure MCP manager is initialized."""
        if not self._mcp_initialized:
            await mcp_manager.initialize()
            self._mcp_initialized = True
    
    async def generate_teaser_from_enhanced_content(
        self, 
        script: "PodcastScript", 
        teaser_content: "TeaserContent",
        analysis: Optional["ScriptAnalysis"] = None,
        language: str = "en-US"
    ) -> "TeaserProject":
        """
        Generate teaser from pre-analyzed content and script analysis.
        
        Args:
            script: Original podcast script
            teaser_content: Pre-generated teaser content with enhancements
            analysis: Optional script analysis for additional context
            language: Language code for voice synthesis (e.g., "en-US", "he-IL")
            
        Returns:
            TeaserProject with generated assets
        """
        # Initialize MCP connections
        await self._ensure_mcp_initialized()
        
        # Create project
        project = TeaserProject(
            id=str(uuid.uuid4()),
            original_script=script,
            teaser_content=teaser_content
        )
        
        try:
            logger.info(f"Starting enhanced teaser generation for project {project.id}")
            
            # Step 1: Generate audio and video with enhanced context
            project.update_status("generating_media")
            logger.info("Generating enhanced audio and video assets...")
            
            # Pass analysis context to agents if available
            audio_task = self.audio_agent.generate_audio(teaser_content, language)
            video_task = self.video_agent.generate_video(teaser_content)
            
            audio_path, video_path = await asyncio.gather(audio_task, video_task)
            
            # Step 2: Compose final teaser
            project.update_status("compositing")
            logger.info("Compositing final teaser...")
            
            final_teaser_path = await self.compositor_agent.compose_teaser(
                audio_path=audio_path,
                video_path=video_path,
                project_id=project.id
            )
            
            # Store results
            project.generated_assets = GeneratedAssets(
                audio_path=audio_path,
                video_path=video_path,
                final_teaser_path=final_teaser_path,
                generation_metadata={
                    "analysis": analysis.dict() if analysis else {},
                    "enhanced": True
                }
            )
            
            project.update_status("completed")
            logger.success(f"Enhanced teaser generation completed for project {project.id}")
            
        except Exception as e:
            project.update_status("failed", str(e))
            logger.error(f"Error in enhanced teaser generation: {e}")
        
        return project

    async def generate_teaser(self, script: "PodcastScript", language: str = "en-US") -> "TeaserProject":
        """
        Generate a complete social media teaser from a podcast script.
        
        Args:
            script: The original podcast script
            language: Language code for voice synthesis (e.g., "en-US", "he-IL")
            
        Returns:
            TeaserProject with generated assets
        """
        # Initialize MCP connections
        await self._ensure_mcp_initialized()
        
        # Create project
        project = TeaserProject(
            id=str(uuid.uuid4()),
            original_script=script
        )
        
        try:
            logger.info(f"Starting teaser generation for project {project.id}")
            
            # Step 1: Extract teaser content
            project.update_status("extracting_content")
            logger.info("Extracting teaser content from script...")
            
            teaser_content = await self.content_agent.extract_teaser_content(script)
            project.teaser_content = teaser_content
            
            # Step 2: Generate audio and video in parallel
            project.update_status("generating_media")
            logger.info("Generating audio and video assets...")
            
            audio_task = self.audio_agent.generate_audio(teaser_content, language)
            video_task = self.video_agent.generate_video(teaser_content)
            
            audio_path, video_path = await asyncio.gather(audio_task, video_task)
            
            # Step 3: Compose final teaser
            project.update_status("compositing")
            logger.info("Compositing final teaser...")
            
            final_teaser_path = await self.compositor_agent.compose_teaser(
                audio_path=audio_path,
                video_path=video_path,
                project_id=project.id
            )
            
            # Update project with generated assets
            project.generated_assets = GeneratedAssets(
                audio_path=audio_path,
                video_path=video_path,
                final_teaser_path=final_teaser_path
            )
            
            project.update_status("completed")
            logger.success(f"Teaser generation completed for project {project.id}")
            
        except Exception as e:
            logger.error(f"Error in teaser generation: {str(e)}")
            project.update_status("failed", str(e))
            raise
        
        return project
    
    async def generate_teaser_from_text(self, title: str, content: str) -> TeaserProject:
        """
        Convenience method to generate teaser from text input.
        
        Args:
            title: Podcast episode title
            content: Script content
            
        Returns:
            TeaserProject with generated assets
        """
        script = PodcastScript(title=title, content=content)
        return await self.generate_teaser(script)

    async def generate_teaser_sequential_resumable(
        self,
        script: "PodcastScript",
        language: str = "en-US",
        force_content: bool = False,
        force_audio: bool = False,
        force_video: bool = False,
        force_compose: bool = False,
    ) -> "TeaserProject":
        """
        Sequential, resumable teaser generation. Each step checks for existing artifacts
        and reuses them unless forced.
        """
        await self._ensure_mcp_initialized()

        # Stable project id derived from content for resumability
        stable_id = hashlib.sha1(f"{script.title}|{script.content}".encode("utf-8")).hexdigest()[:12]
        project_dir = Path(settings.output_dir) / stable_id
        project_dir.mkdir(parents=True, exist_ok=True)

        project = TeaserProject(id=stable_id, original_script=script)
        logger.info(f"Starting sequential/resumable generation for project {stable_id}")

        # Paths
        content_json = project_dir / "teaser_content.json"
        audio_target = project_dir / f"audio.{settings.output_audio_format}"
        video_target = project_dir / f"video.{settings.output_video_format}"
        final_target = project_dir / f"final.{settings.output_video_format}"

        try:
            # Step 1: Extract teaser content
            project.update_status("extracting_content")
            if content_json.exists() and not force_content:
                logger.info(f"Reusing existing teaser content: {content_json}")
                teaser_content = TeaserContent(**json.loads(content_json.read_text()))
            else:
                logger.info("Extracting teaser content from script...")
                teaser_content = await self.content_agent.extract_teaser_content(script)
                content_json.write_text(teaser_content.model_dump_json(indent=2))
            project.teaser_content = teaser_content

            # Step 2: Generate audio
            project.update_status("generating_audio")
            if audio_target.exists() and audio_target.stat().st_size > 0 and not force_audio:
                logger.info(f"Reusing existing audio: {audio_target}")
                audio_path = str(audio_target)
            else:
                logger.info("Generating TTS audio...")
                gen_audio_path = await self.audio_agent.generate_audio(teaser_content, language)
                # Move to canonical path
                os.replace(gen_audio_path, audio_target)
                audio_path = str(audio_target)

            # Step 3: Generate video
            project.update_status("generating_video")
            if video_target.exists() and video_target.stat().st_size > 1024 and not force_video:
                logger.info(f"Reusing existing video: {video_target}")
                video_path = str(video_target)
            else:
                logger.info("Generating video...")
                gen_video_path = await self.video_agent.generate_video(teaser_content)
                # Move to canonical path
                os.replace(gen_video_path, video_target)
                video_path = str(video_target)

            # Step 4: Compose final teaser
            project.update_status("compositing")
            if final_target.exists() and final_target.stat().st_size > 1024 and not force_compose:
                logger.info(f"Reusing existing final teaser: {final_target}")
                final_teaser_path = str(final_target)
            else:
                logger.info("Compositing final teaser...")
                composed_path = await self.compositor_agent.compose_teaser(
                    audio_path=audio_path,
                    video_path=video_path,
                    project_id=stable_id,
                )
                # Move to canonical path
                os.replace(composed_path, final_target)
                final_teaser_path = str(final_target)

            # Save metadata
            metadata = {
                "language": language,
                "forced": {
                    "content": force_content,
                    "audio": force_audio,
                    "video": force_video,
                    "compose": force_compose,
                },
            }
            (project_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

            # Update project assets
            project.generated_assets = GeneratedAssets(
                audio_path=audio_path,
                video_path=video_path,
                final_teaser_path=final_teaser_path,
                generation_metadata=metadata,
            )
            project.update_status("completed")
            logger.success(f"Sequential/resumable teaser generation completed for project {stable_id}")
            return project
        except Exception as e:
            project.update_status("failed", str(e))
            logger.error(f"Error in sequential/resumable generation: {e}")
            return project

    def _stable_id_and_dir(self, script: "PodcastScript"):
        """Compute stable id and project directory for a script."""
        stable_id = hashlib.sha1(f"{script.title}|{script.content}".encode("utf-8")).hexdigest()[:12]
        project_dir = Path(settings.output_dir) / stable_id
        project_dir.mkdir(parents=True, exist_ok=True)
        return stable_id, project_dir

    async def step_extract(self, script: "PodcastScript", force: bool = False) -> tuple[str, str]:
        """Extract teaser content and persist it. Returns (project_id, content_json_path)."""
        await self._ensure_mcp_initialized()
        pid, pdir = self._stable_id_and_dir(script)
        content_json = pdir / "teaser_content.json"

        if content_json.exists() and not force:
            logger.info(f"Reusing existing teaser content: {content_json}")
            return pid, str(content_json)

        logger.info("Extracting teaser content from script...")
        teaser_content = await self.content_agent.extract_teaser_content(script)
        content_json.write_text(teaser_content.model_dump_json(indent=2))
        logger.success(f"Saved teaser content: {content_json}")
        return pid, str(content_json)

    async def step_tts(self, script: "PodcastScript", language: str = "en-US", force: bool = False) -> tuple[str, str]:
        """Generate/resume TTS audio. Returns (project_id, audio_path).

        Now supports gender / voice overrides via metadata in teaser_content.json if present.
        """
        await self._ensure_mcp_initialized()
        pid, pdir = self._stable_id_and_dir(script)
        content_json = pdir / "teaser_content.json"
        audio_target = pdir / f"audio.{settings.output_audio_format}"

        # Ensure content
        if not content_json.exists():
            await self.step_extract(script, force=False)
        teaser_raw = json.loads(content_json.read_text())
        gender = teaser_raw.get("voice_gender")
        voice_name = teaser_raw.get("voice_name")
        teaser_content = TeaserContent(**{k: v for k, v in teaser_raw.items() if k in {
            "headline", "script", "key_points", "visual_description", "duration_seconds"
        }})

        if audio_target.exists() and audio_target.stat().st_size > 0 and not force:
            logger.info(f"Reusing existing audio: {audio_target}")
            return pid, str(audio_target)

        logger.info("Generating TTS audio...")
        gen_audio_path = await self.audio_agent.generate_audio(
            teaser_content,
            language=language,
            gender=gender,
            voice_name=voice_name,
        )
        os.replace(gen_audio_path, audio_target)
        logger.success(f"Saved audio: {audio_target}")
        return pid, str(audio_target)

    async def step_video(self, script: "PodcastScript", force: bool = False) -> tuple[str, str]:
        """Generate/resume video. Returns (project_id, video_path)."""
        await self._ensure_mcp_initialized()
        pid, pdir = self._stable_id_and_dir(script)
        content_json = pdir / "teaser_content.json"
        video_target = pdir / f"video.{settings.output_video_format}"

        # Ensure content
        if not content_json.exists():
            await self.step_extract(script, force=False)
        teaser_content = TeaserContent(**json.loads(content_json.read_text()))

        if video_target.exists() and video_target.stat().st_size > 1024 and not force:
            logger.info(f"Reusing existing video: {video_target}")
            return pid, str(video_target)

        logger.info("Generating video...")
        gen_video_path = await self.video_agent.generate_video(teaser_content)
        os.replace(gen_video_path, video_target)
        logger.success(f"Saved video: {video_target}")
        return pid, str(video_target)

    async def step_compose(self, script: "PodcastScript", language: str = "en-US", force: bool = False) -> tuple[str, str]:
        """Compose/resume final teaser. Returns (project_id, final_path)."""
        await self._ensure_mcp_initialized()
        pid, pdir = self._stable_id_and_dir(script)
        audio_target = pdir / f"audio.{settings.output_audio_format}"
        video_target = pdir / f"video.{settings.output_video_format}"
        final_target = pdir / f"final.{settings.output_video_format}"

        # Ensure prerequisites
        if not audio_target.exists() or audio_target.stat().st_size == 0:
            await self.step_tts(script, language=language, force=False)
        if not video_target.exists() or video_target.stat().st_size < 1024:
            await self.step_video(script, force=False)

        if final_target.exists() and final_target.stat().st_size > 1024 and not force:
            logger.info(f"Reusing existing final teaser: {final_target}")
            return pid, str(final_target)

        logger.info("Compositing final teaser...")
        composed_path = await self.compositor_agent.compose_teaser(
            audio_path=str(audio_target),
            video_path=str(video_target),
            project_id=pid,
        )
        os.replace(composed_path, final_target)
        logger.success(f"Saved final teaser: {final_target}")
        return pid, str(final_target)

    async def step_generate_from_input(
        self,
        title: str,
        prompt: str | None = None,
        full_script: str | None = None,
        headline: str | None = None,
        target_duration: int = 15,
        language: str = "en-US",
        voice_gender: str | None = None,
        voice_name: str | None = None,
        visual_style: str | None = None,
        aspect_ratio: str | None = None,
        theme: str | None = None,
        force: bool = False,
    ) -> tuple[str, str]:
        """Generate teaser_content.json (and input_spec.json) from prompt or script.

        Returns (project_id, teaser_content.json path).
        """
        await self._ensure_mcp_initialized()

        source_text = full_script or prompt or ""
        script_model = PodcastScript(title=title, content=source_text)
        pid, pdir = self._stable_id_and_dir(script_model)
        content_json = pdir / "teaser_content.json"
        spec_json = pdir / "input_spec.json"

        if content_json.exists() and not force:
            logger.info(f"Reusing existing teaser content: {content_json}")
            return pid, str(content_json)

        spec = InputSpec(
            prompt=prompt,
            full_script=full_script,
            headline=headline,
            target_duration_seconds=target_duration,
            language=language,
            voice_gender=voice_gender,
            voice_name=voice_name,
            visual_style=visual_style,
            aspect_ratio=aspect_ratio,
            theme=theme,
        )

        teaser = await self.content_agent.generate_teaser_from_input(spec, title=title)
        # Persist spec & teaser (augment teaser with voice metadata for downstream audio)
        spec_json.write_text(spec.model_dump_json(indent=2))
        teaser_dict = teaser.model_dump()
        teaser_dict["voice_gender"] = voice_gender
        teaser_dict["voice_name"] = voice_name
        teaser_dict["language"] = language
        if spec.visual_style:
            teaser_dict["visual_style"] = spec.visual_style
        content_json.write_text(json.dumps(teaser_dict, indent=2))
        logger.success(f"Saved teaser content (from input spec): {content_json}")
        return pid, str(content_json)
