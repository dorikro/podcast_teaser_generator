"""Video generation agent using MCP servers, Azure AI Foundry, or OpenAI Sora."""

import os
import asyncio
import uuid
from typing import Optional
from openai import AsyncOpenAI, AsyncAzureOpenAI
from loguru import logger

from ..models import TeaserContent
from ..config import settings
from ..mcp_client import mcp_manager


class VideoGenerationAgent:
    """Agent responsible for generating video clips using MCP servers, Azure AI Foundry, or OpenAI Sora."""
    
    def __init__(self):
        """Initialize the video generation agent."""
        self.openai_client = None
        self.sora_client = None
        
        if settings.use_azure_ai and settings.azure_openai_endpoint and settings.azure_openai_api_key:
            # Use Azure AI Foundry
            self.openai_client = AsyncAzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version
            )
            logger.info("Using Azure AI Foundry for video generation")
            
            # Check if Sora is available through Azure
            if settings.use_azure_sora:
                self.sora_client = self.openai_client
                logger.info("Sora available through Azure OpenAI")
                
        elif settings.sora_api_key or settings.openai_api_key:
            # Direct Sora/OpenAI access
            api_key = settings.sora_api_key or settings.openai_api_key
            if settings.sora_endpoint:
                # Custom Sora endpoint
                self.sora_client = AsyncOpenAI(
                    api_key=api_key,
                    base_url=settings.sora_endpoint
                )
                logger.info(f"Using custom Sora endpoint: {settings.sora_endpoint}")
            else:
                # Standard OpenAI endpoint
                self.sora_client = AsyncOpenAI(api_key=api_key)
                logger.info("Using OpenAI directly for Sora video generation")
        else:
            logger.warning("No API keys configured - will use MCP servers or placeholder video only")
    
    async def generate_video(self, teaser_content: TeaserContent) -> str:
        """
        Generate video from teaser content.
        
        Args:
            teaser_content: The teaser content with visual description
            
        Returns:
            Path to the generated video file
        """
        logger.info("Generating video...")
        
        # Ensure output directory exists
        os.makedirs(settings.output_dir, exist_ok=True)
        
        # Generate filename
        video_filename = f"teaser_video_{uuid.uuid4().hex[:8]}.{settings.output_video_format}"
        video_path = os.path.join(settings.output_dir, video_filename)
        
        # Try MCP server first
        if mcp_manager.is_service_available("video"):
            try:
                return await self._generate_via_mcp(teaser_content, video_path)
            except Exception as e:
                logger.error(f"MCP video generation failed: {str(e)}")
                logger.info("Falling back to Sora API")
        
        # Fallback to Sora API
        if self.sora_client:
            try:
                return await self._generate_via_sora(teaser_content, video_path)
            except Exception as e:
                logger.error(f"Sora video generation failed: {str(e)}")
        
        # Final fallback to placeholder
        logger.warning("All video generation methods failed - creating placeholder")
        await self._create_placeholder_video(video_path, teaser_content)
        return video_path
    
    async def _generate_via_mcp(self, teaser_content: TeaserContent, output_path: str) -> str:
        """Generate video using MCP server."""
        mcp_client = mcp_manager.get_client("video")
        if not mcp_client:
            raise Exception("MCP video client not available")
        
        # Prepare arguments for MCP tool call
        arguments = {
            "prompt": self._build_video_prompt(teaser_content),
            "duration": teaser_content.duration_seconds,
            "format": settings.output_video_format,
            "output_path": output_path,
            "aspect_ratio": "9:16"  # Vertical for social media
        }
        
        # Call the video generation tool
        result = await mcp_client.call_tool("generate_video", arguments)
        
        if not result or "video_path" not in result:
            raise Exception("Invalid response from MCP video server")
        
        generated_path = result["video_path"]
        logger.success(f"Video generated via MCP: {generated_path}")
        return generated_path
    
    async def _generate_via_sora(self, teaser_content: TeaserContent, output_path: str) -> str:
        """Generate video using Azure Sora API."""
        if not self.sora_client and not settings.sora_endpoint:
            raise Exception("Sora client not configured")
        
        # Create video generation prompt
        prompt = self._build_video_prompt(teaser_content)
        
        try:
            logger.info("Generating video with Azure Sora...")
            
            # Azure Sora uses a job-based API
            import aiohttp
            import json
            import time
            import ssl
            import random
            
            # Create SSL context that doesn't verify certificates (for Azure endpoints)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            headers = {
                "Content-Type": "application/json",
                # Use lowercase 'api-key' for Azure
                "api-key": settings.sora_api_key or settings.azure_openai_api_key
            }
            
            # Create job payload
            payload = {
                "model": settings.sora_model,
                "prompt": prompt,
                "height": "1080",
                "width": "1920",  # 16:9 aspect ratio for social media
                "n_seconds": str(min(teaser_content.duration_seconds, 10)),  # Azure Sora limit
                "n_variants": "1"
            }
            
            async with aiohttp.ClientSession(connector=connector) as session:
                # Step 1: Submit job
                async with session.post(settings.sora_endpoint, headers=headers, json=payload) as resp:
                    if resp.status not in [200, 201, 202]:
                        error_text = await resp.text()
                        raise Exception(f"Failed to submit Sora job: HTTP {resp.status} - {error_text}")
                    
                    job_data = await resp.json()
                    job_id = job_data.get("id")
                    if not job_id:
                        raise Exception("No job ID returned from Sora")
                    
                    logger.info(f"Sora job submitted successfully: {job_id} (status: {job_data.get('status')})")
                
                # Step 2: Poll for completion
                status_url = settings.sora_endpoint.replace("/jobs", f"/jobs/{job_id}")
                max_wait = 300  # 5 minutes max wait
                start_time = time.time()
                
                while time.time() - start_time < max_wait:
                    await asyncio.sleep(5)  # Poll every 5 seconds
                    
                    async with session.get(status_url, headers=headers) as resp:
                        if resp.status != 200:
                            continue
                        
                        status_data = await resp.json()
                        status = status_data.get("status")
                        
                        if status in ["completed", "succeeded"]:
                            generations = status_data.get("generations", [])
                            if generations:
                                gen_data = generations[0]
                                gen_id = gen_data.get("id")
                                
                                logger.info(f"🎬 Azure Sora video generation completed!")
                                logger.info(f"Generation ID: {gen_id}")
                                logger.info(f"Resolution: {gen_data.get('width')}x{gen_data.get('height')}")
                                logger.info(f"Duration: {gen_data.get('n_seconds')}s")
                                
                                # Step 3: Robust download with backoff retry
                                # Build download base from sora_endpoint first (same host used for job), fallback to azure endpoint
                                base_url = None
                                if settings.sora_endpoint and '/openai/' in settings.sora_endpoint:
                                    base_url = settings.sora_endpoint.split('/openai/')[0].rstrip('/')
                                elif settings.azure_openai_endpoint:
                                    base_url = settings.azure_openai_endpoint.rstrip('/')
                                else:
                                    base_url = ""
                                download_url = f"{base_url}/openai/v1/video/generations/{gen_id}/content/video?api-version=preview"
                                logger.info(f"Attempting video download from: {download_url}")
                                
                                attempts = 0
                                delay = settings.sora_download_retry_initial_delay
                                max_attempts = settings.sora_download_retry_max_attempts
                                max_total_seconds = settings.sora_download_retry_max_seconds
                                download_start = time.time()
                                last_error = None
                                
                                while attempts < max_attempts and (time.time() - download_start) < max_total_seconds:
                                    attempts += 1
                                    try:
                                        async with session.get(download_url, headers=headers) as video_resp:
                                            status_code = video_resp.status
                                            ctype = video_resp.headers.get('content-type', 'unknown')
                                            clen = video_resp.headers.get('content-length', '0')
                                            logger.info(f"Download try {attempts}: status={status_code}, type={ctype}, length={clen}")
                                            
                                            if status_code == 200 and ('video/' in ctype or int(clen or 0) > 1000):
                                                expected = int(clen or 0)
                                                bytes_written = 0
                                                tmp_path = output_path + ".part"
                                                
                                                with open(tmp_path, 'wb') as f:
                                                    async for chunk in video_resp.content.iter_chunked(1024 * 64):
                                                        f.write(chunk)
                                                        bytes_written += len(chunk)
                                                
                                                if expected and bytes_written < expected:
                                                    # Partial content; retry
                                                    last_error = RuntimeError(
                                                        f"Partial content: wrote {bytes_written} of {expected} bytes"
                                                    )
                                                    logger.warning(str(last_error))
                                                    try:
                                                        os.remove(tmp_path)
                                                    except Exception:
                                                        pass
                                                else:
                                                    os.replace(tmp_path, output_path)
                                                    logger.success(
                                                        f"🎬 Real video downloaded via Azure Sora: {output_path} ({bytes_written} bytes)"
                                                    )
                                                    return output_path
                                            else:
                                                # Not ready yet or wrong content type
                                                last_error = RuntimeError(
                                                    f"Not ready: HTTP {status_code}, type={ctype}, len={clen}"
                                                )
                                                logger.info(str(last_error))
                                    except Exception as de:
                                        last_error = de
                                        logger.info(f"Download attempt {attempts} errored: {de}")
                                    
                                    # Exponential backoff with jitter
                                    jitter = random.uniform(0, 0.5)
                                    sleep_for = min(delay * (settings.sora_download_retry_backoff ** (attempts - 1)) + jitter, 30)
                                    total_elapsed = int(time.time() - download_start)
                                    logger.info(f"Retrying download in {sleep_for:.1f}s (elapsed {total_elapsed}s)")
                                    await asyncio.sleep(sleep_for)
                                
                                # If we reach here, download failed after retries
                                logger.error(f"Failed to download Sora video after {attempts} attempts: {last_error}")
                                await self._create_sora_success_placeholder(output_path, teaser_content, gen_data)
                                return output_path
                            else:
                                raise Exception(f"No generations found in completed job. Response: {status_data}")
                        elif status == "failed":
                            error_msg = status_data.get("error", "Unknown error")
                            raise Exception(f"Sora job failed: {error_msg}")
                        elif status in ["pending", "running", "preprocessing", "queued", "processing"]:
                            logger.info(f"Sora job {status}... waiting ({int(time.time() - start_time)}s elapsed)")
                            continue
                        else:
                            logger.warning(f"Unknown Sora job status: {status}, continuing to wait...")
                
                raise Exception("Sora job timed out")
                
        except Exception as e:
            logger.error(f"Azure Sora generation error: {e}")
            # Fall back to placeholder if Sora fails
            logger.warning("Falling back to placeholder video")
            await self._create_placeholder_video(output_path, teaser_content)
            return output_path
    
    def _build_video_prompt(self, teaser_content: TeaserContent) -> str:
        """Build a structured XML + guidance prompt for video generation."""
        # Extract narrative fragments
        insight = (teaser_content.key_points[0] if teaser_content.key_points else teaser_content.headline).strip()
        emotional = (teaser_content.key_points[1] if len(teaser_content.key_points) > 1 else teaser_content.visual_description.split('.')[0]).strip()
        curiosity = (teaser_content.key_points[2] if len(teaser_content.key_points) > 2 else f"What comes next in '{teaser_content.headline}'?").strip()

        total = max(5, teaser_content.duration_seconds)
        base_scene = max(2, total // 3)
        remainder = total - base_scene * 3
        scene_durations = [base_scene, base_scene, base_scene]
        for i in range(remainder):
            scene_durations[i] += 1

        def fmt_secs(s: int) -> str:  # local helper
            return f"{s}s"

        xml_template = f"""<PodcastTeaserVideo>\n  <Meta>\n    <Duration>{total}s</Duration>\n    <Tone>Curious, cinematic, music-inspired</Tone>\n    <Style>Moody, abstract visuals, no humans</Style>\n  </Meta>\n\n  <Scene id=\"1\" duration=\"{fmt_secs(scene_durations[0])}\">\n    <Visual>\n      <Description>\n        Wide cinematic shot of a symbolic landscape connected to the song’s (episode’s) mood \n        (e.g., stormy sea for turmoil, neon city lights for nightlife, golden sunrise for hope).\n        Abstract elements appear subtly, like floating text fragments or glowing notes drifting in the air.\n      </Description>\n    </Visual>\n    <Audio>\n      <Narration>{insight}</Narration>\n    </Audio>\n  </Scene>\n\n  <Scene id=\"2\" duration=\"{fmt_secs(scene_durations[1])}\">\n    <Visual>\n      <Description>\n        Contrast scene that reflects the hidden emotional angle \n        (e.g., a cracked vinyl record glowing from within, dark room lit by shifting colors, \n        or surreal imagery like a bird breaking free from glass).\n      </Description>\n    </Visual>\n    <Audio>\n      <Narration>{emotional}</Narration>\n    </Audio>\n  </Scene>\n\n  <Scene id=\"3\" duration=\"{fmt_secs(scene_durations[2])}\">\n    <Visual>\n      <Description>\n        Transition to an open-ended symbolic visual that sparks curiosity \n        (e.g., a door slowly opening into bright light, a record spinning into darkness, \n        or floating question marks dissolving into starlight).\n      </Description>\n    </Visual>\n    <Audio>\n      <Narration>{curiosity}</Narration>\n    </Audio>\n  </Scene>\n</PodcastTeaserVideo>"""

        guidance = (
            "You are generating a short vertical social-media teaser video for a podcast episode "
            f"headline: '{teaser_content.headline}'. The narration lasts about {total} seconds. "
            "Use the XML specification to drive coherent, cinematic, symbolic visuals. Avoid literal human faces. "
            "Maintain smooth modern motion, readable composition, and cohesive color mood. If forced to linear text, "
            "summarize each scene sequentially keeping timing context."
        )

        summary_points = "\n".join(f"- {p}" for p in teaser_content.key_points)
        nl_summary = f"Key Points:\n{summary_points}\nVisual Description Hints: {teaser_content.visual_description.strip()}"

        return guidance + "\n\n" + xml_template + "\n\n" + nl_summary + "\n"
    
    async def _create_placeholder_video(self, video_path: str, teaser_content: TeaserContent):
        """Create a placeholder video until Sora API is available."""
        try:
            # MoviePy 2.x imports
            from moviepy import ColorClip
            try:
                from moviepy import TextClip  # optional; may not be available without ImageMagick
                from moviepy import CompositeVideoClip
                has_text = True
            except Exception:
                CompositeVideoClip = None
                TextClip = None
                has_text = False

            # Compatibility helper for TextClip (MoviePy 1.x vs 2.x)
            def make_text(text: str, size: int, color: str):  # returns a clip or None
                if not TextClip:
                    return None
                for kwargs in (
                    {"text": text, "font_size": size, "color": color},
                    {"text": text, "fontsize": size, "color": color},
                    {"text": text, "color": color},
                ):
                    try:
                        return TextClip(**kwargs)
                    except Exception:
                        continue
                return None

            def build_and_write():
                bg = ColorClip(size=(720, 1280), color=(30, 30, 40), duration=teaser_content.duration_seconds)
                if has_text and CompositeVideoClip and TextClip:
                    title_clip = make_text(teaser_content.headline, 60, 'white')
                    if title_clip is not None:
                        title_clip = title_clip.set_position('center').set_duration(teaser_content.duration_seconds)
                        final = CompositeVideoClip([bg, title_clip])
                    else:
                        final = bg
                else:
                    final = bg
                final.write_videofile(
                    video_path,
                    fps=24,
                    codec='libx264',
                    audio=False,
                    preset='medium'
                )
                final.close()
                bg.close()

            await asyncio.get_event_loop().run_in_executor(None, build_and_write)
            logger.info(f"Placeholder video created: {video_path}")
        except ImportError:
            logger.warning("MoviePy not available for placeholder video generation - skipping video creation")
            # Create an empty binary MP4 container would require ffmpeg; as a last resort leave no video
            with open(video_path, 'wb') as f:
                f.write(b"")
        except Exception as e:
            logger.error(f"Error creating placeholder video: {str(e)}")
            raise

    async def _create_sora_placeholder_video(self, video_path: str, teaser_content: TeaserContent, generation_metadata: dict):
        """Create a placeholder video with Sora generation metadata."""
        try:
            from moviepy import ColorClip
            try:
                from moviepy import TextClip
                from moviepy import CompositeVideoClip
                has_text = True
            except Exception:
                CompositeVideoClip = None
                TextClip = None
                has_text = False

            width = generation_metadata.get('width', 1920)
            height = generation_metadata.get('height', 1080)
            duration = generation_metadata.get('n_seconds', teaser_content.duration_seconds)

            def build_and_write():
                bg = ColorClip(size=(width, height), color=(20, 50, 80), duration=duration)
                if has_text and CompositeVideoClip and TextClip:
                    # local helper
                    def t(txt, sz, color='white'):  # noqa: E306
                        for kwargs in (
                            {"text": txt, "font_size": sz, "color": color},
                            {"text": txt, "fontsize": sz, "color": color},
                            {"text": txt, "color": color},
                        ):
                            try:
                                return TextClip(**kwargs)
                            except Exception:
                                continue
                        return None
                    title_text = f"SORA GENERATED\n{teaser_content.headline}"
                    title = t(title_text, min(width//20, 60))
                    meta_text = f"Resolution: {width}x{height} | Duration: {duration}s | Generation ID: {generation_metadata.get('id', 'unknown')}"
                    meta = t(meta_text, min(width//40, 30), 'lightgray')
                    clips = [bg]
                    if title is not None:
                        title = title.set_position('center').set_duration(duration)
                        clips.append(title)
                    if meta is not None:
                        meta = meta.set_position(('center', height*0.7)).set_duration(duration)
                        clips.append(meta)
                    final = CompositeVideoClip(clips) if len(clips) > 1 else bg
                else:
                    final = bg
                final.write_videofile(
                    video_path,
                    fps=24,
                    codec='libx264',
                    audio=False,
                    preset='medium'
                )
                final.close()
                bg.close()

            await asyncio.get_event_loop().run_in_executor(None, build_and_write)
            logger.success(f"Sora placeholder video created: {video_path} ({width}x{height})")
        except ImportError:
            logger.warning("MoviePy not available for Sora placeholder video generation - skipping video creation")
            with open(video_path, 'wb') as f:
                f.write(b"")
        except Exception as e:
            logger.error(f"Error creating Sora placeholder video: {str(e)}")
            raise

    async def _create_sora_success_placeholder(self, video_path: str, teaser_content: TeaserContent, generation_metadata: dict):
        """Create a success placeholder indicating real video was generated in Azure."""
        try:
            from moviepy import ColorClip
            try:
                from moviepy import TextClip
                from moviepy import CompositeVideoClip
                has_text = True
            except Exception:
                CompositeVideoClip = None
                TextClip = None
                has_text = False

            width = generation_metadata.get('width', 1920)
            height = generation_metadata.get('height', 1080)
            duration = generation_metadata.get('n_seconds', teaser_content.duration_seconds)

            def build_and_write():
                bg = ColorClip(size=(width, height), color=(0, 50, 100), duration=duration)
                if has_text and CompositeVideoClip and TextClip:
                    def t(txt, sz, color='white'):
                        for kwargs in (
                            {"text": txt, "font_size": sz, "color": color},
                            {"text": txt, "fontsize": sz, "color": color},
                            {"text": txt, "color": color},
                        ):
                            try:
                                return TextClip(**kwargs)
                            except Exception:
                                continue
                        return None
                    clips = [bg]
                    title = t("✅ VIDEO GENERATED SUCCESSFULLY", min(width//25, 48))
                    if title is not None:
                        clips.append(title.set_position(('center', height*0.2)).set_duration(duration))
                    headline_clip = t(teaser_content.headline, min(width//30, 36), 'lightblue')
                    if headline_clip is not None:
                        clips.append(headline_clip.set_position(('center', height*0.4)).set_duration(duration))
                    instr = t(f"🎬 Generated by Azure Sora\n🆔 {generation_metadata.get('id', 'unknown')}", min(width//40, 24))
                    if instr is not None:
                        clips.append(instr.set_position(('center', height*0.65)).set_duration(duration))
                    meta = t(f"Resolution: {width}x{height} | Duration: {duration}s", min(width//50, 18), 'gray')
                    if meta is not None:
                        clips.append(meta.set_position(('center', height*0.85)).set_duration(duration))
                    final = CompositeVideoClip(clips) if len(clips) > 1 else bg
                else:
                    final = bg
                final.write_videofile(
                    video_path,
                    fps=24,
                    codec='libx264',
                    audio=False,
                    preset='medium'
                )
                final.close()
                bg.close()

            await asyncio.get_event_loop().run_in_executor(None, build_and_write)
            logger.success(f"Success placeholder created: {video_path} ({width}x{height})")
        except ImportError:
            logger.warning("MoviePy not available - creating empty placeholder video")
            with open(video_path, 'wb') as f:
                f.write(b"")
        except Exception as e:
            logger.error(f"Error creating success placeholder: {str(e)}")
            raise
