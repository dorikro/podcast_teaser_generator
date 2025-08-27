"""Command-line interface for the podcast teaser generator."""

import asyncio
import os
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from loguru import logger

from .workflow import TeaserGenerationWorkflow
from .models import PodcastScript
from .config import settings
from .interactive_cli import InteractiveTeaserGenerator


console = Console()


@click.group()
@click.version_option()
def cli():
    """Podcast Teaser Generator - AI-powered social media teaser creation."""
    pass


@cli.command()
@click.option('--title', '-t', required=True, help='Podcast episode title')
@click.option('--script', '-s', type=click.Path(exists=True), help='Path to script file')
@click.option('--text', help='Script text (alternative to --script)')
@click.option('--output', '-o', default='./output', help='Output directory')
def smart_generate(title: str, script: Optional[str], text: Optional[str], output: str):
    """Generate teaser with intelligent script analysis and user interaction."""
    from .interactive_cli import InteractiveTeaserGenerator
    
    # Read script content
    if script:
        with open(script, 'r', encoding='utf-8') as f:
            content = f.read()
    elif text:
        content = text
    else:
        console.print("[red]Error: Must provide either --script or --text[/red]")
        return
    
    # Set output directory
    settings.output_dir = output
    
    # Run interactive generation
    generator = InteractiveTeaserGenerator()
    asyncio.run(generator.generate_interactive_teaser(title, content))


@cli.command()
@click.option('--title', '-t', required=True, help='Podcast episode title')
@click.option('--script', '-s', type=click.Path(exists=True), help='Path to script file')
@click.option('--text', help='Script text (alternative to --script)')
@click.option('--output', '-o', help='Output directory (default: ./output)')
@click.option('--duration', '-d', type=int, help=f'Teaser duration in seconds (default: {settings.max_clip_duration})')
def generate(title: str, script: Optional[str], text: Optional[str], output: Optional[str], duration: Optional[int]):
    """Generate a social media teaser from a podcast script."""
    
    if not script and not text:
        console.print("[red]Error: Either --script or --text must be provided[/red]")
        return
    
    if script and text:
        console.print("[red]Error: Provide either --script or --text, not both[/red]")
        return
    
    # Read script content
    if script:
        script_path = Path(script)
        content = script_path.read_text()
    else:
        content = text
    
    # Set output directory
    if output:
        settings.output_dir = output
    
    # Set duration
    if duration:
        settings.max_clip_duration = duration
    
    console.print(f"[green]Generating teaser for: {title}[/green]")
    console.print(f"[blue]Output directory: {settings.output_dir}[/blue]")
    
    # Run the generation workflow
    asyncio.run(_run_generation(title, content))


async def _run_generation(title: str, content: str):
    """Run the teaser generation workflow with progress tracking."""
    
    workflow = TeaserGenerationWorkflow()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        
        task = progress.add_task("Initializing...", total=None)
        
        try:
            # Update progress for each step
            progress.update(task, description="Extracting teaser content...")
            
            project = await workflow.generate_teaser_from_text(title, content)
            
            if project.status == "completed":
                console.print("\n[green]✓ Teaser generation completed successfully![/green]")
                
                # Display results table
                table = Table(title="Generated Assets")
                table.add_column("Asset Type", style="cyan")
                table.add_column("File Path", style="green")
                
                if project.generated_assets:
                    if project.generated_assets.audio_path:
                        table.add_row("Audio", project.generated_assets.audio_path)
                    if project.generated_assets.video_path:
                        table.add_row("Video", project.generated_assets.video_path)
                    if project.generated_assets.final_teaser_path:
                        table.add_row("Final Teaser", project.generated_assets.final_teaser_path)
                
                console.print(table)
                
                # Display teaser content
                if project.teaser_content:
                    console.print(f"\n[bold]Headline:[/bold] {project.teaser_content.headline}")
                    console.print(f"[bold]Script:[/bold] {project.teaser_content.script}")
                    console.print(f"[bold]Duration:[/bold] {project.teaser_content.duration_seconds} seconds")
            
            else:
                console.print(f"[red]✗ Generation failed: {project.error_message}[/red]")
                
        except Exception as e:
            console.print(f"[red]✗ Error: {str(e)}[/red]")


@cli.command()
@click.argument('directory', type=click.Path(exists=True))
def batch(directory: str):
    """Process multiple script files in a directory."""
    
    script_dir = Path(directory)
    script_files = list(script_dir.glob("*.txt")) + list(script_dir.glob("*.md"))
    
    if not script_files:
        console.print(f"[yellow]No script files found in {directory}[/yellow]")
        return
    
    console.print(f"[green]Found {len(script_files)} script files[/green]")
    
    for script_file in script_files:
        title = script_file.stem  # Use filename as title
        content = script_file.read_text()
        
        console.print(f"\n[blue]Processing: {script_file.name}[/blue]")
        asyncio.run(_run_generation(title, content))


@cli.command("smart-generate")
@click.option("--title", required=True, help="Title of the podcast episode")
@click.option("--script", required=True, type=click.Path(exists=True, path_type=Path), help="Path to the script file")
def smart_generate(title: str, script: Path):
    """Generate a teaser with intelligent script analysis and user interaction."""
    
    console.print(f"[green]Starting intelligent teaser generation for: {title}[/green]")
    
    try:
        # Read script content
        script_content = script.read_text()
        
        # Create and run interactive generator
        generator = InteractiveTeaserGenerator()
        asyncio.run(generator.generate_interactive_teaser(title, script_content))
        
    except Exception as e:
        console.print(f"[red]Error during generation: {e}[/red]")
        logger.exception("Smart generation failed")


@cli.command()
@click.option('--title', '-t', required=True, help='Podcast episode title')
@click.option('--script', '-s', type=click.Path(exists=True), help='Path to script file')
@click.option('--text', help='Script text (alternative to --script)')
@click.option('--output', '-o', help='Output directory (default: ./output)')
@click.option('--duration', '-d', type=int, help=f'Teaser duration in seconds (default: {settings.max_clip_duration})')
@click.option('--force-content', is_flag=True, help='Force re-extraction of teaser content')
@click.option('--force-audio', is_flag=True, help='Force re-generation of audio (TTS)')
@click.option('--force-video', is_flag=True, help='Force re-generation of video')
@click.option('--force-compose', is_flag=True, help='Force re-composition of final teaser')
def generate_resumable(title: str, script: Optional[str], text: Optional[str], output: Optional[str], duration: Optional[int], force_content: bool, force_audio: bool, force_video: bool, force_compose: bool):
    """Generate a teaser sequentially with resumable steps and force flags."""
    
    if not script and not text:
        console.print("[red]Error: Either --script or --text must be provided[/red]")
        return
    if script and text:
        console.print("[red]Error: Provide either --script or --text, not both[/red]")
        return

    # Read script content
    if script:
        script_path = Path(script)
        content = script_path.read_text()
    else:
        content = text

    # Set output directory
    if output:
        settings.output_dir = output

    # Set duration
    if duration:
        settings.max_clip_duration = duration

    console.print(f"[green]Generating teaser (resumable) for: {title}[/green]")
    console.print(f"[blue]Output directory: {settings.output_dir}[/blue]")

    asyncio.run(_run_generation_resumable(title, content, force_content, force_audio, force_video, force_compose))


async def _run_generation_resumable(title: str, content: str, force_content: bool, force_audio: bool, force_video: bool, force_compose: bool):
    """Run the sequential/resumable workflow."""
    workflow = TeaserGenerationWorkflow()
    project = await workflow.generate_teaser_sequential_resumable(
        script=PodcastScript(title=title, content=content),
        language=settings.azure_speech_language or 'en-US',
        force_content=force_content,
        force_audio=force_audio,
        force_video=force_video,
        force_compose=force_compose,
    )

    if project.status == "completed":
        console.print("\n[green]✓ Teaser generation (resumable) completed successfully![/green]")
        table = Table(title="Generated Assets (Resumable)")
        table.add_column("Asset Type", style="cyan")
        table.add_column("File Path", style="green")
        if project.generated_assets:
            if project.generated_assets.audio_path:
                table.add_row("Audio", project.generated_assets.audio_path)
            if project.generated_assets.video_path:
                table.add_row("Video", project.generated_assets.video_path)
            if project.generated_assets.final_teaser_path:
                table.add_row("Final Teaser", project.generated_assets.final_teaser_path)
        console.print(table)
    else:
        console.print(f"[red]✗ Generation failed: {project.error_message}[/red]")


@cli.command("generate-audio")
@click.option('--title', '-t', required=True, help='Podcast episode title')
@click.option('--script', '-s', type=click.Path(exists=True), help='Path to full script file (alternative to --prompt)')
@click.option('--prompt', help='High-level prompt describing the episode (alternative to --script)')
@click.option('--headline', help='Optional pre-written headline to enforce')
@click.option('--duration', type=int, default=15, show_default=True, help='Target teaser duration seconds')
@click.option('--language', default=lambda: settings.azure_speech_language or 'en-US', show_default=True, help='Language / locale for TTS (e.g. en-US, he-IL)')
@click.option('--gender', type=click.Choice(['male','female','auto']), default='auto', show_default=True, help='Preferred voice gender (auto lets system choose)')
@click.option('--voice-name', help='Explicit Azure voice name override (takes precedence)')
@click.option('--output', '-o', help='Output directory (default: ./output)')
@click.option('--force-content', is_flag=True, help='Force re-generation of teaser content from input spec')
@click.option('--force-audio', is_flag=True, help='Force re-generation of audio even if exists')
def generate_audio_cmd(title: str, script: Optional[str], prompt: Optional[str], headline: Optional[str], duration: int, language: str, gender: str, voice_name: Optional[str], output: Optional[str], force_content: bool, force_audio: bool):
    """Audio-first flow using unified InputSpec (prompt OR script) producing teaser_content + audio."""
    if not script and not prompt:
        console.print("[red]Error: Provide either --script or --prompt[/red]")
        return
    if script and prompt:
        console.print("[red]Error: Provide only one of --script or --prompt, not both[/red]")
        return

    full_script = Path(script).read_text() if script else None  # type: ignore[arg-type]
    if output:
        settings.output_dir = output

    workflow = TeaserGenerationWorkflow()
    voice_gender = None if gender == 'auto' else gender

    async def _run():
        pid, content_path = await workflow.step_generate_from_input(
            title=title,
            prompt=prompt,
            full_script=full_script,
            headline=headline,
            target_duration=duration,
            language=language,
            voice_gender=voice_gender,
            voice_name=voice_name,
            force=force_content,
        )
        # Now TTS
        from .models import PodcastScript as _PS
        script_text = full_script or prompt or ""
        script_model = _PS(title=title, content=script_text)
        _, audio_path = await workflow.step_tts(script_model, language=language, force=force_audio)
        table = Table(title="Audio Generation Result")
        table.add_column("Project ID", style="cyan")
        table.add_column("Teaser Content", style="green")
        table.add_column("Audio Path", style="magenta")
        table.add_row(pid, content_path, audio_path)
        console.print(table)
        console.print("[bold green]Next:[/bold green] When satisfied with audio run: \n  podcast-teaser generate-video-final --title '" + title + "' --script '<same script file>' (or --prompt '<same prompt>')")

    asyncio.run(_run())


@cli.command("generate-video-final")
@click.option('--title', '-t', required=True, help='Podcast episode title')
@click.option('--script', '-s', type=click.Path(exists=True), help='Path to full script file (alternative to --prompt)')
@click.option('--prompt', help='Same prompt used for audio phase (if prompt-based)')
@click.option('--headline', help='Optional headline (should match if previously enforced)')
@click.option('--language', default=lambda: settings.azure_speech_language or 'en-US', show_default=True, help='Language / locale (must match audio)')
@click.option('--gender', type=click.Choice(['male','female','auto']), default='auto', show_default=True, help='Voice gender (only used if audio missing)')
@click.option('--voice-name', help='Explicit Azure voice name (only used if regenerating audio)')
@click.option('--output', '-o', help='Output directory (default: ./output)')
@click.option('--force-video', is_flag=True, help='Force re-generation of video')
@click.option('--force-compose', is_flag=True, help='Force re-composition of final teaser')
@click.option('--force-audio', is_flag=True, help='Force re-generation of audio before video (rare)')
def generate_video_final_cmd(title: str, script: Optional[str], prompt: Optional[str], headline: Optional[str], language: str, gender: str, voice_name: Optional[str], output: Optional[str], force_video: bool, force_compose: bool, force_audio: bool):
    """After audio phase: ensure teaser content exists, ensure audio, then video + final compose."""
    if not script and not prompt:
        console.print("[red]Error: Provide either --script or --prompt[/red]")
        return
    if script and prompt:
        console.print("[red]Error: Provide only one of --script or --prompt[/red]")
        return

    full_script = Path(script).read_text() if script else None  # type: ignore[arg-type]
    if output:
        settings.output_dir = output
    workflow = TeaserGenerationWorkflow()
    voice_gender = None if gender == 'auto' else gender

    async def _run():
        # (Re)create spec/content only if missing
        pid, content_path = await workflow.step_generate_from_input(
            title=title,
            prompt=prompt,
            full_script=full_script,
            headline=headline,
            # do not override duration here; rely on stored spec if exists
            target_duration=15,
            language=language,
            voice_gender=voice_gender,
            voice_name=voice_name,
            force=False,
        )
        from .models import PodcastScript as _PS
        script_model = _PS(title=title, content=full_script or prompt or "")
        await workflow.step_tts(script_model, language=language, force=force_audio)
        pid_v, video_path = await workflow.step_video(script_model, force=force_video)
        pid_f, final_path = await workflow.step_compose(script_model, language=language, force=force_compose)
        table = Table(title="Video + Final Composition Result")
        table.add_column("Project ID", style="cyan")
        table.add_column("Teaser Content", style="green")
        table.add_column("Video Path", style="yellow")
        table.add_column("Final Teaser", style="magenta")
        table.add_row(pid_v, content_path, video_path, final_path)
        console.print(table)
        console.print("[bold green]Done.[/bold green] If you need a different voice re-run generate-audio with new params.")

    asyncio.run(_run())


@cli.command()
def setup():
    """Setup the application (create directories, check dependencies)."""
    
    console.print("[green]Setting up Podcast Teaser Generator...[/green]")
    
    # Create directories
    os.makedirs(settings.output_dir, exist_ok=True)
    os.makedirs(settings.temp_dir, exist_ok=True)
    
    # Check for .env file
    if not os.path.exists('.env'):
        console.print("[yellow]No .env file found. Copy .env.example to .env and configure your API keys.[/yellow]")
    
    # Display configuration
    table = Table(title="Current Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Output Directory", settings.output_dir)
    table.add_row("Temp Directory", settings.temp_dir)
    table.add_row("Max Clip Duration", f"{settings.max_clip_duration} seconds")
    table.add_row("Video Format", settings.output_video_format)
    table.add_row("Audio Format", settings.output_audio_format)
    table.add_row("Log Level", settings.log_level)
    
    console.print(table)
    console.print("\n[green]✓ Setup completed![/green]")


@cli.group()
def steps():
    """Run individual generation steps (resumable)."""
    pass


@steps.command("extract")
@click.option('--title', '-t', required=True, help='Podcast episode title')
@click.option('--script', '-s', type=click.Path(exists=True), help='Path to script file')
@click.option('--text', help='Script text (alternative to --script)')
@click.option('--force', is_flag=True, help='Force re-extraction')
def step_extract_cmd(title: str, script: Optional[str], text: Optional[str], force: bool):
    content = Path(script).read_text() if script else text
    if not content:
        console.print("[red]Error: Either --script or --text must be provided[/red]")
        return
    workflow = TeaserGenerationWorkflow()
    pid, path = asyncio.run(workflow.step_extract(PodcastScript(title=title, content=content), force=force))
    console.print(f"[green]Extracted teaser content for project {pid}[/green] -> {path}")


@steps.command("tts")
@click.option('--title', '-t', required=True, help='Podcast episode title')
@click.option('--script', '-s', type=click.Path(exists=True), help='Path to script file')
@click.option('--text', help='Script text (alternative to --script)')
@click.option('--language', default=lambda: settings.azure_speech_language or 'en-US')
@click.option('--force', is_flag=True, help='Force re-generate audio')
def step_tts_cmd(title: str, script: Optional[str], text: Optional[str], language: str, force: bool):
    content = Path(script).read_text() if script else text
    if not content:
        console.print("[red]Error: Either --script or --text must be provided[/red]")
        return
    workflow = TeaserGenerationWorkflow()
    pid, path = asyncio.run(workflow.step_tts(PodcastScript(title=title, content=content), language=language, force=force))
    console.print(f"[green]Generated audio for project {pid}[/green] -> {path}")


@steps.command("video")
@click.option('--title', '-t', required=True, help='Podcast episode title')
@click.option('--script', '-s', type=click.Path(exists=True), help='Path to script file')
@click.option('--text', help='Script text (alternative to --script)')
@click.option('--force', is_flag=True, help='Force re-generate video')
def step_video_cmd(title: str, script: Optional[str], text: Optional[str], force: bool):
    content = Path(script).read_text() if script else text
    if not content:
        console.print("[red]Error: Either --script or --text must be provided[/red]")
        return
    workflow = TeaserGenerationWorkflow()
    pid, path = asyncio.run(workflow.step_video(PodcastScript(title=title, content=content), force=force))
    console.print(f"[green]Generated video for project {pid}[/green] -> {path}")


@steps.command("compose")
@click.option('--title', '-t', required=True, help='Podcast episode title')
@click.option('--script', '-s', type=click.Path(exists=True), help='Path to script file')
@click.option('--text', help='Script text (alternative to --script)')
@click.option('--language', default=lambda: settings.azure_speech_language or 'en-US')
@click.option('--force', is_flag=True, help='Force re-compose final')
def step_compose_cmd(title: str, script: Optional[str], text: Optional[str], language: str, force: bool):
    content = Path(script).read_text() if script else text
    if not content:
        console.print("[red]Error: Either --script or --text must be provided[/red]")
        return
    workflow = TeaserGenerationWorkflow()
    pid, path = asyncio.run(workflow.step_compose(PodcastScript(title=title, content=content), language=language, force=force))
    console.print(f"[green]Composed final teaser for project {pid}[/green] -> {path}")


def main():
    """Main entry point for the CLI."""
    # Configure logging
    logger.remove()
    logger.add(
        lambda msg: console.print(msg, highlight=False),
        level=settings.log_level,
        format="<level>{time:HH:mm:ss}</level> | <level>{message}</level>"
    )
    
    cli()


if __name__ == '__main__':
    main()
