"""Compositor agent for combining audio and video into final teaser."""

import os
import asyncio
import uuid
from typing import Optional
from loguru import logger

from ..config import settings


class CompositorAgent:
    """Agent responsible for compositing final teaser from audio and video."""
    
    def __init__(self):
        """Initialize the compositor agent."""
        pass
    
    async def compose_teaser(
        self, 
        audio_path: str, 
        video_path: str, 
        project_id: str
    ) -> str:
        """
        Compose final teaser by combining audio and video.
        
        Args:
            audio_path: Path to the generated audio file
            video_path: Path to the generated video file  
            project_id: Unique project identifier
            
        Returns:
            Path to the final composed teaser
        """
        logger.info("Compositing final teaser...")
        
        # Ensure output directory exists
        os.makedirs(settings.output_dir, exist_ok=True)
        
        # Generate final filename
        final_filename = f"teaser_final_{project_id[:8]}.{settings.output_video_format}"
        final_path = os.path.join(settings.output_dir, final_filename)
        
        try:
            # Use MoviePy for audio-video composition
            await self._compose_with_moviepy(audio_path, video_path, final_path)
            
            logger.success(f"Final teaser composed: {final_path}")
            return final_path
            
        except Exception as e:
            logger.error(f"Error compositing teaser: {str(e)}")
            raise
    
    async def _compose_with_moviepy(
        self, 
        audio_path: str, 
        video_path: str, 
        output_path: str
    ):
        """Compose video using MoviePy."""
        try:
            # Import for MoviePy 2.x
            from moviepy import VideoFileClip, AudioFileClip
            
            logger.info(f"Composing video: {video_path} + audio: {audio_path}")
            
            def compose_sync():
                # Load video and audio
                logger.info("Loading video file...")
                video = VideoFileClip(video_path)
                logger.info(f"Video loaded: {video.duration}s, {video.size}, {video.fps}fps")
                
                logger.info("Loading audio file...")
                audio = AudioFileClip(audio_path)
                logger.info(f"Audio loaded: {audio.duration}s")
                
                # If audio is longer than video, build a ping-pong (forward+reverse) loop
                if audio.duration > video.duration + 0.05:  # tolerance
                    logger.info(
                        f"Audio ({audio.duration:.2f}s) longer than video ({video.duration:.2f}s). Building ping-pong loop."
                    )
                    from moviepy import concatenate_videoclips
                    # Reverse copy
                    rev = video.reversed()
                    # Construct repeated sequence until we exceed audio duration
                    seq = []
                    total = 0.0
                    # One cycle duration (forward+reverse but avoid duplicating boundary frame visually)
                    cycle = [video, rev]
                    cycle_duration = video.duration + rev.duration
                    # Safety guard to avoid runaway loops (max 20 cycles ~ plenty for short teasers)
                    max_cycles = 20
                    cycles = 0
                    while total < audio.duration and cycles < max_cycles:
                        for clip in cycle:
                            if total >= audio.duration:
                                break
                            seq.append(clip)
                            total += clip.duration
                        cycles += 1
                    looped = concatenate_videoclips(seq)
                    if looped.duration > audio.duration + 0.05:
                        logger.info(
                            f"Trimming looped sequence from {looped.duration:.2f}s to match audio {audio.duration:.2f}s"
                        )
                        looped = looped.subclipped(0, audio.duration)
                    final_video = looped.with_audio(audio)
                else:
                    # Video is same or longer; trim if needed
                    logger.info("Combining audio with original (or trimming if longer)...")
                    base = video.with_audio(audio)
                    if video.duration > audio.duration + 0.05:
                        base = base.subclipped(0, audio.duration)
                    final_video = base
                
                # Write final video (MoviePy 2.x parameters with better compatibility)
                logger.info(f"Writing final video to: {output_path}")
                final_video.write_videofile(
                    output_path,
                    fps=24,
                    codec='libx264',
                    audio_codec='aac',
                    audio_bitrate='128k',
                    bitrate='1000k',
                    preset='medium'
                )
                
                # Clean up
                video.close()
                audio.close()
                final_video.close()
                
                logger.success(f"Final video composed successfully: {output_path}")
            
            # Run composition in thread pool
            await asyncio.get_event_loop().run_in_executor(None, compose_sync)
            
        except ImportError:
            logger.warning("MoviePy not available - creating placeholder composition")
            # Create placeholder file
            with open(output_path, 'w') as f:
                f.write(f"# Final teaser composition\n")
                f.write(f"# Audio: {audio_path}\n")
                f.write(f"# Video: {video_path}\n")
        except Exception as e:
            logger.error(f"Error in MoviePy composition: {str(e)}")
            raise
