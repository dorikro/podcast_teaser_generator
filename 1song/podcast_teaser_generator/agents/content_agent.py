"""Content extraction agent using MCP servers, Azure AI Foundry, or OpenAI GPT models."""

from typing import Optional
from openai import AsyncOpenAI, AsyncAzureOpenAI
from loguru import logger

from ..models import PodcastScript, TeaserContent, InputSpec
from ..config import settings
from ..mcp_client import mcp_manager


class ContentExtractionAgent:
    """Agent responsible for extracting teaser content from podcast scripts."""
    
    def __init__(self):
        """Initialize the content extraction agent."""
        self.openai_client = None
        
        if settings.use_azure_ai and settings.azure_openai_endpoint and settings.azure_openai_api_key:
            # Use Azure AI Foundry
            self.openai_client = AsyncAzureOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version
            )
            self.model = settings.azure_deployment_name
            logger.info("Using Azure AI Foundry for content extraction")
        elif settings.openai_api_key:
            # Fallback to direct OpenAI
            self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
            self.model = "gpt-4"
            logger.info("Using OpenAI directly for content extraction")
        else:
            logger.warning("No API keys configured - will use MCP servers or default content only")
    
    async def extract_teaser_content(self, script: PodcastScript) -> TeaserContent:
        """
        Extract teaser content from a podcast script.
        
        Args:
            script: The original podcast script
            
        Returns:
            TeaserContent with extracted information
        """
        logger.info(f"Extracting teaser content for: {script.title}")
        
        # Try MCP server first
        if mcp_manager.is_service_available("content"):
            try:
                return await self._extract_via_mcp(script)
            except Exception as e:
                logger.error(f"MCP content extraction failed: {str(e)}")
                logger.info("Falling back to OpenAI API")
        
        # Fallback to OpenAI API
        if self.openai_client:
            try:
                return await self._extract_via_openai(script)
            except Exception as e:
                logger.error(f"OpenAI content extraction failed: {str(e)}")
        
        # Final fallback to default content
        logger.warning("All content extraction methods failed - using default content")
        return self._create_default_content(script)

    async def generate_teaser_from_input(self, spec: InputSpec, title: str) -> TeaserContent:
        """Generate teaser content starting from an InputSpec (prompt or full script).

        If both prompt and full_script are provided, priority is given to full_script
        for extraction context while the prompt can bias style (future enhancement).
        """
        # Build a synthetic PodcastScript to reuse existing extraction logic.
        source_text = spec.full_script or spec.prompt or ""
        script = PodcastScript(title=title, content=source_text)

        # Temporarily adjust max_clip_duration to requested target (restore after)
        original_duration = settings.max_clip_duration
        settings.max_clip_duration = spec.target_duration_seconds
        try:
            teaser = await self.extract_teaser_content(script)
        finally:
            settings.max_clip_duration = original_duration

        # Override headline if provided
        if spec.headline:
            teaser.headline = spec.headline
        # Ensure duration matches requested (capped inside validation range)
        teaser.duration_seconds = spec.target_duration_seconds
        return teaser
    
    async def _extract_via_mcp(self, script: PodcastScript) -> TeaserContent:
        """Extract content using MCP server."""
        mcp_client = mcp_manager.get_client("content")
        if not mcp_client:
            raise Exception("MCP content client not available")
        
        # Prepare arguments for MCP tool call
        arguments = {
            "title": script.title,
            "content": script.content[:2000],  # Truncate for token limits
            "max_duration": settings.max_clip_duration
        }
        
        # Call the content extraction tool
        result = await mcp_client.call_tool("extract_teaser_content", arguments)
        
        if not result or "content" not in result:
            raise Exception("Invalid response from MCP server")
        
        content_data = result["content"]
        
        return TeaserContent(
            headline=content_data.get("headline", "Engaging Podcast Moment"),
            script=content_data.get("script", "Check out this amazing insight!"),
            key_points=content_data.get("key_points", ["Interesting content ahead"]),
            visual_description=content_data.get("visual_description", "Dynamic podcast visuals"),
            duration_seconds=content_data.get("duration_seconds", settings.max_clip_duration)
        )
    
    async def _extract_via_openai(self, script: PodcastScript) -> TeaserContent:
        """Extract content using OpenAI API."""
        if not self.openai_client:
            raise Exception("OpenAI client not configured")
        
        prompt = self._build_extraction_prompt(script)
        
        response = await self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert content creator specializing in social media teasers for podcasts. Your job is to extract the most engaging content for short-form social media clips."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        content = response.choices[0].message.content
        return self._parse_response(content)
    
    def _create_default_content(self, script: PodcastScript) -> TeaserContent:
        """Create default content when all extraction methods fail."""
        return TeaserContent(
            headline=f"Amazing Insights from {script.title}",
            script="Check out this incredible podcast episode with amazing insights!",
            key_points=["Engaging content", "Expert insights", "Must-listen episode"],
            visual_description="Dynamic podcast studio visuals with text overlay",
            duration_seconds=settings.max_clip_duration
        )
    
    def _build_extraction_prompt(self, script: PodcastScript) -> str:
        """Build the prompt for content extraction."""
        # Infer target language from settings.azure_speech_language; if Hebrew (he-IL), enforce Hebrew output.
        lang = (settings.azure_speech_language or "en-US").lower()
        language_instruction = (
            "All textual fields (headline, script, key points, visual description) MUST be written entirely in HEBREW (Modern Hebrew, natural, no transliteration)."
            if lang.startswith("he") else
            "All textual fields should be in natural, fluent English."
        )
        target = settings.max_clip_duration
        # Provide a small flexible window around target (e.g., 15 -> 14-16s)
        lower = max(5, target - 1)
        upper = target + 1 if target < 120 else target
        return f"""
Extract teaser content from this podcast script for a {target}-second social media clip.

{language_instruction}

PODCAST TITLE: {script.title}

SCRIPT CONTENT:
{script.content[:2000]}

Please provide:
1. HEADLINE: A catchy, attention-grabbing headline (max 10 words)
2. SCRIPT: A {lower}-{upper} second narration script that hooks viewers (stay within this window)
3. KEY_POINTS: 3-5 bullet points of the most interesting content
4. VISUAL_DESCRIPTION: Description for video generation (what should be shown)

Format your response as JSON:
{{
    "headline": "Your catchy headline here",
    "script": "Your {lower}-{upper} second script here",
    "key_points": ["Point 1", "Point 2", "Point 3"],
    "visual_description": "Description of visuals for video generation",
    "duration_seconds": {settings.max_clip_duration}
}}
"""
    
    def _parse_response(self, content: str) -> TeaserContent:
        """Parse the AI response into TeaserContent model."""
        import json
        
        try:
            # Try to extract JSON from the response
            start_idx = content.find('{')
            end_idx = content.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON found in response")
            
            json_str = content[start_idx:end_idx]
            data = json.loads(json_str)
            
            return TeaserContent(**data)
            
        except Exception as e:
            logger.error(f"Error parsing AI response: {str(e)}")
            # Fallback to manual parsing or default values
            return TeaserContent(
                headline="Engaging Podcast Moment",
                script="Check out this amazing insight from our latest podcast episode!",
                key_points=["Interesting content ahead"],
                visual_description="Dynamic podcast-style visuals with text overlay",
                duration_seconds=settings.max_clip_duration
            )
