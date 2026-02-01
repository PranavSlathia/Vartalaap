"""Voice API endpoint for browser-based voice testing."""

import io
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydub import AudioSegment

from src.config import get_settings
from src.core.session import CallSession
from src.services.stt.deepgram import DeepgramService
from src.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Store sessions in memory (for demo - use Redis in production)
_sessions: dict[str, CallSession] = {}

# Directory for temp audio files
AUDIO_DIR = Path("data/audio_cache")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def get_or_create_session(session_id: str) -> CallSession:
    """Get existing session or create new one."""
    if session_id not in _sessions:
        _sessions[session_id] = CallSession(business_id="himalayan_kitchen")
    return _sessions[session_id]


async def transcribe_webm(audio_data: bytes) -> str:
    """Transcribe webm audio using Deepgram."""
    import asyncio
    from deepgram import DeepgramClient, PrerecordedOptions

    try:
        settings = get_settings()
        client = DeepgramClient(api_key=settings.deepgram_api_key.get_secret_value())

        # Send webm directly to Deepgram - they support it natively
        options = PrerecordedOptions(
            model="nova-2",
            language="hi",
            detect_language=True,
            smart_format=True,
            punctuate=True,
        )

        response = await asyncio.to_thread(
            client.listen.rest.v("1").transcribe_file,
            {"buffer": audio_data, "mimetype": "audio/webm"},
            options,
        )

        # Extract transcript
        results = response.results
        if results and results.channels:
            alternatives = results.channels[0].alternatives
            if alternatives:
                transcript = alternatives[0].transcript
                logger.info(f"Transcribed: {transcript[:50]}..." if transcript else "No transcript")
                return transcript

        return ""

    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return ""


def generate_tts_elevenlabs(text: str) -> str | None:
    """Generate TTS using ElevenLabs (realistic Hindi voice)."""
    try:
        settings = get_settings()

        if not settings.elevenlabs_api_key:
            logger.warning("ELEVENLABS_API_KEY not set, falling back to gTTS")
            return generate_tts_gtts(text)

        api_key = settings.elevenlabs_api_key.get_secret_value()

        from elevenlabs import ElevenLabs

        client = ElevenLabs(api_key=api_key)

        # Use multilingual v2 model with a natural voice
        # "Aria" voice is warm and natural, good for Hindi
        audio_generator = client.text_to_speech.convert(
            text=text,
            voice_id="9BWtsMINqrJLrRacOk9x",  # Aria - natural, warm voice
            model_id="eleven_multilingual_v2",  # Best multilingual model
            output_format="mp3_44100_128",
        )

        # Save to file
        audio_id = str(uuid.uuid4())[:8]
        audio_path = AUDIO_DIR / f"{audio_id}.mp3"

        with open(audio_path, "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)

        logger.info(f"Generated ElevenLabs TTS: {audio_path}")
        return f"/api/voice/audio/{audio_id}.mp3"

    except Exception as e:
        logger.error(f"ElevenLabs TTS error: {e}")
        # Fallback to gTTS
        return generate_tts_gtts(text)


def generate_tts_gtts(text: str) -> str | None:
    """Generate TTS using Google TTS (fallback)."""
    try:
        from gtts import gTTS

        tts = gTTS(text=text, lang="hi", slow=False)

        audio_id = str(uuid.uuid4())[:8]
        audio_path = AUDIO_DIR / f"{audio_id}.mp3"
        tts.save(str(audio_path))

        logger.info(f"Generated gTTS: {audio_path}")
        return f"/api/voice/audio/{audio_id}.mp3"

    except Exception as e:
        logger.error(f"gTTS error: {e}")
        return None


def generate_tts(text: str) -> str | None:
    """Generate TTS audio - tries ElevenLabs first, falls back to gTTS."""
    # Try ElevenLabs first for better quality
    return generate_tts_elevenlabs(text)


@router.post("/voice/process")
async def process_voice(
    audio: UploadFile = File(...),
    session_id: str = Form(...),
):
    """Process voice input and return response with audio."""
    try:
        # Read audio data
        audio_data = await audio.read()
        logger.info(f"Received audio: {len(audio_data)} bytes, session: {session_id}")

        # Transcribe
        transcript = await transcribe_webm(audio_data)
        if not transcript:
            return JSONResponse({
                "error": "Could not understand. Please try again.",
                "transcript": None,
                "response": None,
            })

        # Get session and process
        session = get_or_create_session(session_id)
        response, metadata = await session.process_user_input(transcript)

        # Generate TTS
        audio_url = generate_tts(response)

        return JSONResponse({
            "transcript": transcript,
            "response": response,
            "audio_url": audio_url,
            "latency_ms": metadata.first_token_ms,
        })

    except Exception as e:
        logger.exception("Voice processing error")
        return JSONResponse({
            "error": str(e),
            "transcript": None,
            "response": None,
        }, status_code=500)


@router.get("/voice/audio/{filename}")
async def get_audio(filename: str):
    """Serve generated audio file."""
    audio_path = AUDIO_DIR / filename
    if not audio_path.exists():
        return JSONResponse({"error": "Audio not found"}, status_code=404)

    return FileResponse(
        audio_path,
        media_type="audio/mpeg",
        filename=filename,
    )
