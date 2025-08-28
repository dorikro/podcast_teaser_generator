# Podcast Teaser Generator

An AI-powered agentic flow application that transforms podcast scripts into engaging social media teasers using cutting-edge AI technologies. Features **Model Context Protocol (MCP)** integration for modular AI service connections.

## 🎯 Overview

This application takes podcast episode scripts and automatically generates short, engaging video teasers perfect for social media promotion. It combines:

- **MCP Integration**: Uses Model Context Protocol servers for flexible AI service connections
- **Content Intelligence**: AI-powered extraction of the most engaging moments
- **Voice Synthesis**: High-quality text-to-speech using ElevenLabs or MCP audio servers
- **Video Generation**: AI-generated visuals using OpenAI Sora or MCP video servers  
- **Automated Composition**: Seamless audio-video integration


## 🚀 Quick Start

### Prerequisites

- Python 3.9 or higher
- **For MCP Mode (Recommended)**: MCP servers for content, audio, and video generation
- **For Direct API Mode**: OpenAI API key (for GPT and Sora access) and ElevenLabs API key

### Installation

1. **Clone and setup the project:**
   ```bash
   git clone <repository-url>
   cd podcast-teaser-generator
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration (see Configuration section)
   ```

4. **Setup the application:**
   ```bash
   podcast-teaser setup
   ```

### MCP Server Setup (Recommended)

The application works best with MCP servers that provide specialized AI services:

1. **Start example MCP servers:**
   ```bash
   # Terminal 1 - Content extraction server
   python mcp_servers/content_server.py

   # Terminal 2 - Audio generation server  
   python mcp_servers/audio_server.py

   # Terminal 3 - Video generation server
   python mcp_servers/video_server.py
   ```

2. **Configure MCP URLs in .env:**
   ```bash
   USE_MCP_SERVERS=true
   MCP_CONTENT_SERVER_URL=stdio:python mcp_servers/content_server.py
   MCP_AUDIO_SERVER_URL=stdio:python mcp_servers/audio_server.py
   MCP_VIDEO_SERVER_URL=stdio:python mcp_servers/video_server.py
   ```

### Basic Usage

Generate a teaser from a script file:
```bash
podcast-teaser generate --title "My Podcast Episode" --script episode_script.txt
```

Generate from text directly:
```bash
podcast-teaser generate --title "Quick Episode" --text "Your podcast script content here..."
```

Resumable (cached) generation with selective re-runs:
```bash
podcast-teaser generate-resumable \
   --title "My Episode" \
   --text "Long script text..." \
   --force-video   # only re-generate video, reuse content/audio if present
```

Run individual steps explicitly:
```bash
podcast-teaser steps extract --title "My Episode" --text "..."   # teaser_content.json
podcast-teaser steps tts     --title "My Episode" --text "..."
podcast-teaser steps video   --title "My Episode" --text "..."
podcast-teaser steps compose --title "My Episode" --text "..."
```

Audio-first approval flow:
```bash
# Step 1: Generate only content + audio
podcast-teaser generate-audio --title "My Episode" --text "Long script..."

# (Review output/<project_id>/audio.mp3)

# Step 2: When satisfied, produce video + final teaser (reuses audio)
podcast-teaser generate-video-final --title "My Episode" --text "Long script..."
```

Interactive (script analysis + user refinement):
```bash
podcast-teaser smart-generate --title "My Episode" --script episode.txt
```

Process multiple files:
```bash
podcast-teaser batch ./scripts/
```

## 🏗️ Architecture

### Agent-Based Design

The application uses specialized agents for different tasks:

```
📥 Input Script
    ↓
🧠 ContentExtractionAgent → Analyzes script, extracts key moments
    ↓
🔄 Parallel Processing:
    ├── 🎵 AudioGenerationAgent → Creates voice narration
    └── 🎬 VideoGenerationAgent → Generates visual content
    ↓
🎭 CompositorAgent → Combines audio + video
    ↓
📤 Final Social Media Teaser
```

### Core Components

- **Workflow Orchestrator**: Manages the entire generation pipeline
- **Content Agent**: Uses GPT-4 to extract engaging content
- **Audio Agent**: Leverages ElevenLabs for voice synthesis
- **Video Agent**: Integrates with OpenAI Sora for visual generation
- **Compositor**: Combines assets using MoviePy

## ⚙️ Configuration

### Environment Variables

```bash
# MCP Server Configuration (Primary)
USE_MCP_SERVERS=true
MCP_CONTENT_SERVER_URL=stdio:python mcp_servers/content_server.py
MCP_AUDIO_SERVER_URL=stdio:python mcp_servers/audio_server.py  
MCP_VIDEO_SERVER_URL=stdio:python mcp_servers/video_server.py
# (remove the stray extra code fence above if copying)
# Azure AI Foundry Configuration (Recommended)
USE_AZURE_AI=true
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_API_KEY=your_azure_api_key_here
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_DEPLOYMENT_NAME=gpt-4

# Azure Speech (optional primary TTS)
AZURE_SPEECH_KEY=your_azure_speech_key
AZURE_SPEECH_REGION=your_region   # e.g. eastus, westeurope
AZURE_SPEECH_VOICE=en-US-JennyNeural
AZURE_SPEECH_LANGUAGE=en-US

# API Keys (Fallback when MCP servers and Azure unavailable)
OPENAI_API_KEY=your_openai_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# Sora (Direct or via Azure). If using Azure-managed Sora, just set Azure vars.
SORA_API_KEY=optional_separate_key_if_not_same_as_OPENAI
SORA_ENDPOINT=https://custom-sora-endpoint.example.com
SORA_MODEL=sora-1.0-turbo

# Sora download retry tuning (defaults usually fine)
SORA_DOWNLOAD_RETRY_MAX_SECONDS=300
SORA_DOWNLOAD_RETRY_INITIAL_DELAY=3.0
SORA_DOWNLOAD_RETRY_BACKOFF=1.7
SORA_DOWNLOAD_RETRY_MAX_ATTEMPTS=12

# Generation Settings
MAX_CLIP_DURATION=30
OUTPUT_VIDEO_FORMAT=mp4
OUTPUT_AUDIO_FORMAT=mp3
DEFAULT_VOICE_ID=21m00Tcm4TlvDq8ikWAM

# Paths
OUTPUT_DIR=output
TEMP_DIR=temp
LOG_LEVEL=INFO
```

### Service Priorities

The application tries services in this order:
1. **MCP Servers** (when `USE_MCP_SERVERS=true`)
2. **Azure AI Foundry** (when `USE_AZURE_AI=true`)
3. **Azure Speech** (for TTS) / **ElevenLabs** fallback
4. **Direct OpenAI / Sora APIs** (fallback with `OPENAI_API_KEY` / `SORA_API_KEY`)
5. **Placeholder content** (when no services available)

### Azure AI Foundry Setup

1. **Create Azure OpenAI Resource:**
   - Go to [Azure Portal](https://portal.azure.com)
   - Create a new "Azure OpenAI" resource
   - Deploy your preferred model (e.g., GPT-4)

2. **Get Configuration Values:**
   ```bash
   # Your endpoint URL (found in Azure portal)
   AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
   
   # API key (found in "Keys and Endpoint" section)
   AZURE_OPENAI_API_KEY=your_api_key_here
   
   # Deployment name (what you named your model deployment)
   AZURE_DEPLOYMENT_NAME=gpt-4
   ```

### MCP vs Azure vs Direct API Mode

**Azure AI Foundry (Recommended):**
- ✅ Enterprise-grade security and compliance
- ✅ Better cost control and monitoring
- ✅ Regional data residency options
- ✅ Integrated with Azure ecosystem

**MCP Mode:**
- ✅ Modular architecture with specialized servers
- ✅ Easy to customize and extend individual services
- ✅ Better separation of concerns
- ✅ Can use different AI providers for different tasks
- ✅ Local development and testing friendly

**Direct API Mode (Fallback):**
- ✅ Simpler setup for quick testing
- ✅ Direct integration with OpenAI and ElevenLabs
- ❌ Less flexible and harder to customize
- ❌ Tightly coupled to specific API providers

### Customization

The application supports extensive customization:

- **Duration**: Adjust teaser length (15-60 seconds)
- **Voice Selection**: Choose from various ElevenLabs voices
- **Video Style**: Configure visual themes and styles
- **Output Formats**: Support for multiple video/audio formats
- **Batch Processing**: Custom naming and organization

## 🔧 Development

### Project Structure

```
podcast_teaser_generator/
├── __init__.py
├── config.py              # Configuration management
├── models.py              # Data models (Pydantic)
├── workflow.py            # Main orchestration logic
├── cli.py                 # Command-line interface
└── agents/
    ├── __init__.py
    ├── content_agent.py    # Content extraction
    ├── audio_agent.py      # Audio generation
    ├── video_agent.py      # Video generation
    └── compositor_agent.py # Final composition
```

### Running Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=podcast_teaser_generator
```

Additional manual diagnostic scripts (ignored by git) live under `local_tests/` for connectivity & latency checks.

### Code Quality

```bash
# Format code
black podcast_teaser_generator/

# Sort imports
isort podcast_teaser_generator/

# Type checking
mypy podcast_teaser_generator/
```

## 📋 API Reference

### Python API

```python
import asyncio
from podcast_teaser_generator.workflow import TeaserGenerationWorkflow
from podcast_teaser_generator.models import PodcastScript

async def main():
   workflow = TeaserGenerationWorkflow()
   script = PodcastScript(title="My Episode", content="Your script content...")

   # One-shot generation
   project = await workflow.generate_teaser_from_text(script.title, script.content)
   print("Final teaser:", project.generated_assets.final_teaser_path if project.generated_assets else None)

   # Resumable (cached) generation
   project2 = await workflow.generate_teaser_sequential_resumable(script)
   print("Resumable final:", project2.generated_assets.final_teaser_path if project2.generated_assets else None)

asyncio.run(main())
```

### CLI Commands

| Command | Purpose |
|---------|---------|
| `podcast-teaser setup` | Initialize folders & show config |
| `podcast-teaser generate` | One-shot full generation |
| `podcast-teaser generate-resumable` | Cached, stepwise generation with force flags |
| `podcast-teaser generate-audio` | Extract + TTS only (audio-first) |
| `podcast-teaser generate-video-final` | Continue after audio to create video + final |
| `podcast-teaser steps extract|tts|video|compose` | Run an individual pipeline stage |
| `podcast-teaser smart-generate` | Interactive + script analysis guided flow |
| `podcast-teaser batch <dir>` | Process all scripts in a directory |

## 🤝 Contributing

## 🌐 Web UI (Optional Separate Deployment)

An optional FastAPI + Jinja2 based web interface is provided (kept separate so CLI users remain unaffected). It lets you:

- Enter either a prompt or full script
- Supply/override a headline
- Set target duration, language, gender, explicit voice name
- Generate Audio only (preview & approve)
- Or generate Audio + Video + Final in one click

### Install Web Extras

```bash
pip install -e .[web]
```

### Run the Web Server

```bash
podcast-teaser-web
# Opens FastAPI app at http://localhost:8000
```

### UI Paths

| Route | Purpose |
|-------|---------|
| `/` | Main form UI |
| `/api/generate` | JSON endpoint (POST) for generation |
| `/static/*` | CSS assets |

### API Payload (POST /api/generate)
```jsonc
{
   "title": "Episode Title",
   "prompt": "Short descriptive prompt", // optional if script provided
   "script": "Full script text",         // optional if prompt provided
   "headline": "Custom headline",        // optional
   "duration": 15,                        // seconds (5-120)
   "language": "en-US",
   "gender": "female" | "male" | "auto",
   "voice_name": "en-US-JennyNeural",    // optional explicit override
   "mode": "audio" | "full"             // audio -> content+tts; full -> +video+final
}
```

### Response
```jsonc
{
   "project_id": "81b389de82f1",
   "audio_path": "output/81b389de82f1/audio.mp3",
   "video_path": "output/81b389de82f1/video.mp4",   // null if mode=audio
   "final_path": "output/81b389de82f1/final.mp4"    // null if mode=audio
}
```

### Separation of Concerns

The web UI lives in the `teaser_web/` package with its own optional dependency group (`[web]`). CLI functionality and core generation pipeline remain unchanged. Deployment choices:

- CLI only: `pip install .` and use `podcast-teaser` commands.
- Web only: `pip install .[web]` and run `podcast-teaser-web`.
- Both: `pip install -e .[web]` during development.

### Production Notes

- For production use a process manager (e.g. `uvicorn teaser_web.app:app --host 0.0.0.0 --port 8000 --workers 2`).
- Behind a reverse proxy (NGINX / Traefik) serve `/static/` with caching.
- Consider persisting logs and enabling auth if exposed publicly (e.g. add API key header check middleware).

### Future Enhancements (Ideas)

- Progress polling endpoints (stream job status)
- WebSocket for live status updates
- Editable teaser script + re-synthesize audio
- Auth & multi-user project listing
- Download zip artifact bundling content.json + media


1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- OpenAI for GPT and Sora technologies
- ElevenLabs for excellent text-to-speech capabilities
- The open-source community for the underlying tools and libraries

## 📞 Support

- 📧 Email: support@example.com
- 💬 Issues: [GitHub Issues](https://github.com/yourusername/podcast-teaser-generator/issues)
- 📖 Documentation: [Full Documentation](https://docs.example.com)

---

*Transform your podcast content into engaging social media teasers with the power of AI!*

## 🔐 Security Notes

- Never commit your `.env`; only `.env.example` belongs in version control.
- All API keys are loaded via environment variables; no secrets are stored in source files.
- Consider adding secret scanning (gitleaks / detect-secrets) in CI.

---

*Build once, iterate fast, resume anytime.*
