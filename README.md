# Vartalaap 🍽️

> **वार्तालाप** (Hindi: "conversation") - Self-hosted voice bot platform for local Indian businesses

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A production-ready voice bot that handles phone calls autonomously with native **Hindi-English-Hinglish** support. Built for restaurants, clinics, and local businesses that need affordable, high-quality voice AI.

## ✨ Features

- **🎙️ Real-time Voice Pipeline**: Deepgram STT → Groq LLM → gTTS/Piper TTS
- **🇮🇳 Native Hindi Support**: Seamless code-switching between Hindi, English, and Hinglish
- **📞 Telephony Ready**: Plivo integration for inbound calls (WebSocket audio streaming)
- **🍽️ Restaurant Demo**: Table reservations, menu queries, hours - fully functional
- **🎯 Low Latency**: P50 < 500ms processing, optimized for real conversations
- **🔒 Privacy First**: Phone encryption, PII masking, GDPR-friendly
- **💰 Cost Effective**: ~$16-27/month operational cost

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Browser   │────▶│   FastAPI    │────▶│  Deepgram   │
│  (WebRTC)   │◀────│  WebSocket   │◀────│    STT      │
└─────────────┘     └──────┬───────┘     └─────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │   Groq LLM   │
                   │ (llama-3.3)  │
                   └──────┬───────┘
                          │
                          ▼
┌─────────────┐     ┌──────────────┐
│   Plivo     │◀───▶│  TTS Engine  │
│ (Telephony) │     │ (gTTS/Piper) │
└─────────────┘     └──────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- API keys: [Deepgram](https://deepgram.com), [Groq](https://groq.com)

### 1. Clone & Install

```bash
git clone https://github.com/PranavSlathia/Vartalaap.git
cd Vartalaap

# Install dependencies
uv sync --all-extras
```

### 2. Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit with your API keys
nano .env
```

**Required API Keys:**
| Service | Purpose | Get Key |
|---------|---------|---------|
| `GROQ_API_KEY` | LLM (conversation) | [console.groq.com](https://console.groq.com) |
| `DEEPGRAM_API_KEY` | Speech-to-text | [deepgram.com](https://deepgram.com) |

**Optional (for telephony):**
| Service | Purpose | Get Key |
|---------|---------|---------|
| `PLIVO_AUTH_ID` | Phone calls | [plivo.com](https://plivo.com) |
| `PLIVO_AUTH_TOKEN` | Phone calls | [plivo.com](https://plivo.com) |

### 3. Generate Security Keys

```bash
# Generate encryption keys
python scripts/generate_keys.py
```

### 4. Run the Server

```bash
# Start API server
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000

# Or with hot reload (development)
uv run uvicorn src.main:app --reload
```

### 5. Test Voice Bot

Open in browser: **http://localhost:8000/voice**

1. Click **"Start Call"**
2. Speak naturally in Hindi/English
3. Bot responds automatically
4. Click **"End Call"** when done

## 📁 Project Structure

```
vartalaap/
├── src/
│   ├── api/                 # FastAPI routes & WebSocket handlers
│   │   ├── routes/          # REST endpoints
│   │   ├── websocket/       # Audio streaming
│   │   └── static/          # Voice test UI
│   ├── core/                # Business logic
│   │   ├── pipeline.py      # Voice pipeline orchestrator
│   │   ├── session.py       # Call session management
│   │   └── conversation_state.py
│   ├── services/            # External service integrations
│   │   ├── stt/             # Speech-to-text (Deepgram)
│   │   ├── llm/             # Language model (Groq)
│   │   ├── tts/             # Text-to-speech (gTTS/Piper)
│   │   └── telephony/       # Phone (Plivo)
│   └── db/                  # Database models & repositories
├── admin/                   # Streamlit admin dashboard
├── config/                  # Business configuration (YAML)
├── tests/                   # Test suite
└── scripts/                 # Utility scripts
```

## 🎯 Demo: Himalayan Kitchen

The default configuration is a demo restaurant bot for "Himalayan Kitchen":

**Try saying:**
- "Table book karna hai" (I want to book a table)
- "4 log, kal shaam 7 baje" (4 people, tomorrow 7 PM)
- "Menu mein kya hai?" (What's on the menu?)
- "Timing kya hai?" (What are the hours?)

## 🔧 Configuration

### Environment Variables

See [.env.example](.env.example) for all options.

**Key Settings:**
```bash
# LLM
GROQ_API_KEY=gsk_xxxx              # Required

# Speech-to-Text
DEEPGRAM_API_KEY=xxxx              # Required

# TTS (optional - defaults to gTTS)
PIPER_VOICE=hi_IN-priyamvada-medium
EDGE_TTS_ENABLED=false

# Conversation
GREETING_TEXT=Namaste! ...
BARGE_IN_ENABLED=true              # Interrupt bot while speaking
```

### Business Configuration

Edit `config/business/himalayan_kitchen.yaml`:

```yaml
name: "Himalayan Kitchen"
hours:
  monday: closed
  tuesday: "11:00-22:30"
  # ...
reservation:
  max_party_size: 10
  advance_days: 30
```

## 🧪 Testing

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src

# Test specific module
uv run pytest tests/test_core/
```

### Manual Testing Scripts

```bash
# Test TTS voice quality
uv run python scripts/test_tts.py

# Test LLM responses
uv run python scripts/test_llm.py

# Text-based conversation test
uv run python scripts/chat_cli.py
```

## 🛠️ Development

### Code Quality

```bash
# Lint
uv run ruff check .

# Format
uv run ruff format .

# Type check
uv run mypy src/
```

### Database Migrations

```bash
# Create migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head
```

## 📊 Admin Dashboard

```bash
# Start admin UI
uv run streamlit run admin/app.py
```

Access at: **http://localhost:8501**

Features:
- Call logs & transcripts
- Reservation management
- Analytics dashboard
- Configuration editor

## 🚢 Deployment

### Docker

```bash
docker-compose up -d
```

### Manual

1. Set `ENVIRONMENT=production` in `.env`
2. Use a process manager (systemd, supervisor)
3. Put behind reverse proxy (Caddy, nginx)
4. Configure SSL certificates

## 📈 Performance Targets

| Metric | Target | Actual |
|--------|--------|--------|
| STT Latency (P50) | < 300ms | ~250ms |
| LLM Latency (P50) | < 500ms | ~350ms |
| TTS Latency (P50) | < 200ms | ~150ms |
| End-to-end (P95) | < 1.2s | ~1.0s |

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open a Pull Request

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [Deepgram](https://deepgram.com) - Speech-to-text
- [Groq](https://groq.com) - Fast LLM inference
- [Piper](https://github.com/rhasspy/piper) - Offline TTS
- [FastAPI](https://fastapi.tiangolo.com) - Web framework

---

**Built with ❤️ for local Indian businesses**

*Questions? Open an issue or reach out!*
