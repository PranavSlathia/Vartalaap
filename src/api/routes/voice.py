"""Voice API endpoint for browser-based voice testing."""

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from src.config import get_settings
from src.core.session import CallSession
from src.db.models import CallLog, CallOutcome, CallSource
from src.db.session import get_session_context
from src.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Store sessions in memory (for demo - use Redis in production)
_sessions: dict[str, CallSession] = {}

# Directory for temp audio files
AUDIO_DIR = Path("data/audio_cache")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

NON_PRODUCTION_PARITY_NOTICE = (
    "Browser voice test uses a non-production path and may differ from live telephony quality."
)

DEFAULT_ELEVENLABS_VOICE_ID = "9BWtsMINqrJLrRacOk9x"
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_EDGE_VOICE = "hi-IN-SwaraNeural"


class TTSSelection(BaseModel):
    """Voice test TTS selection sent by the browser UI."""

    provider: Literal["auto", "elevenlabs", "edge", "piper", "gtts"] = "auto"
    voice_id: str | None = None
    model_id: str | None = None
    edge_voice: str | None = None
    piper_voice: str | None = None


class TextToSpeechRequest(BaseModel):
    """Request body for direct browser TTS generation."""

    text: str = Field(min_length=1)
    provider: Literal["auto", "elevenlabs", "edge", "piper", "gtts"] = "auto"
    voice_id: str | None = None
    model_id: str | None = None
    edge_voice: str | None = None
    piper_voice: str | None = None


def get_or_create_session(session_id: str) -> CallSession:
    """Get existing session or create new one."""
    if session_id not in _sessions:
        _sessions[session_id] = CallSession(business_id="himalayan_kitchen")
    return _sessions[session_id]


async def transcribe_webm(audio_data: bytes) -> str:
    """Transcribe webm audio using Deepgram."""
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
                transcript: str = alternatives[0].transcript or ""
                logger.info(f"Transcribed: {transcript[:50]}..." if transcript else "No transcript")
                return transcript

        return ""

    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return ""


def _save_audio_bytes(audio_bytes: bytes, suffix: str) -> str:
    """Persist generated audio bytes and return public URL."""
    audio_id = str(uuid.uuid4())[:8]
    filename = f"{audio_id}.{suffix}"
    audio_path = AUDIO_DIR / filename
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)
    return f"/api/voice/audio/{filename}"


def _pcm16_to_wav_bytes(raw_pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw mono PCM16 bytes into a WAV container."""
    import io
    import wave

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # int16
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(raw_pcm)
    return wav_buffer.getvalue()


def generate_tts_elevenlabs(
    text: str,
    *,
    voice_id: str | None = None,
    model_id: str | None = None,
) -> str | None:
    """Generate TTS using ElevenLabs (realistic Hindi voice)."""
    try:
        settings = get_settings()

        if not settings.elevenlabs_api_key:
            logger.warning("ELEVENLABS_API_KEY not set")
            return None

        api_key = settings.elevenlabs_api_key.get_secret_value()

        from elevenlabs import ElevenLabs

        client = ElevenLabs(api_key=api_key)

        audio_generator = client.text_to_speech.convert(
            text=text,
            voice_id=voice_id or settings.elevenlabs_voice_id or DEFAULT_ELEVENLABS_VOICE_ID,
            model_id=model_id or settings.elevenlabs_model_id or DEFAULT_ELEVENLABS_MODEL_ID,
            output_format="mp3_44100_128",
        )

        audio_bytes = b"".join(audio_generator)
        if not audio_bytes:
            return None

        audio_url = _save_audio_bytes(audio_bytes, "mp3")
        logger.info(f"Generated ElevenLabs TTS: {audio_url}")
        return audio_url

    except Exception as e:
        logger.error(f"ElevenLabs TTS error: {e}")
        return None


async def generate_tts_edge(
    text: str,
    *,
    voice: str | None = None,
) -> str | None:
    """Generate TTS using Edge neural voices (MP3 output)."""
    try:
        import edge_tts

        selected_voice = voice or get_settings().edge_tts_voice or DEFAULT_EDGE_VOICE
        audio_id = str(uuid.uuid4())[:8]
        filename = f"{audio_id}.mp3"
        audio_path = AUDIO_DIR / filename

        communicate = edge_tts.Communicate(text=text, voice=selected_voice)
        await communicate.save(str(audio_path))

        logger.info(f"Generated Edge TTS: {audio_path}")
        return f"/api/voice/audio/{filename}"
    except Exception as e:
        logger.error(f"Edge TTS error: {e}")
        return None


async def generate_tts_piper(
    text: str,
    *,
    voice_name: str | None = None,
) -> str | None:
    """Generate TTS using local Piper model (WAV output)."""
    try:
        from src.services.tts.piper import PiperTTSService

        settings = get_settings()
        target_rate = 16000
        service = PiperTTSService(
            settings=settings,
            voice_name=voice_name or settings.piper_voice,
        )
        try:
            raw_pcm, _metadata = await service.synthesize(
                text,
                target_sample_rate=target_rate,
            )
        finally:
            await service.close()

        if not raw_pcm:
            return None

        wav_bytes = _pcm16_to_wav_bytes(
            raw_pcm,
            sample_rate=target_rate,
        )
        audio_url = _save_audio_bytes(wav_bytes, "wav")
        logger.info(f"Generated Piper TTS: {audio_url}")
        return audio_url
    except Exception as e:
        logger.error(f"Piper TTS error: {e}")
        return None


def generate_tts_gtts(text: str) -> str | None:
    """Generate TTS using Google TTS (fallback)."""
    try:
        from gtts import gTTS

        tts = gTTS(text=text, lang="hi", slow=False)

        audio_id = str(uuid.uuid4())[:8]
        filename = f"{audio_id}.mp3"
        audio_path = AUDIO_DIR / filename
        tts.save(str(audio_path))

        logger.info(f"Generated gTTS: {audio_path}")
        return f"/api/voice/audio/{filename}"

    except Exception as e:
        logger.error(f"gTTS error: {e}")
        return None


async def generate_tts(text: str, selection: TTSSelection) -> tuple[str | None, str]:
    """Generate TTS audio using selected provider with fallback chain."""
    provider = selection.provider
    chain: list[str]

    if provider == "elevenlabs":
        chain = ["elevenlabs", "edge", "piper", "gtts"]
    elif provider == "edge":
        chain = ["edge", "elevenlabs", "piper", "gtts"]
    elif provider == "piper":
        chain = ["piper", "elevenlabs", "edge", "gtts"]
    elif provider == "gtts":
        chain = ["gtts"]
    else:
        chain = ["elevenlabs", "edge", "piper", "gtts"]

    for candidate in chain:
        audio_url: str | None = None
        if candidate == "elevenlabs":
            audio_url = generate_tts_elevenlabs(
                text,
                voice_id=selection.voice_id,
                model_id=selection.model_id,
            )
        elif candidate == "edge":
            audio_url = await generate_tts_edge(
                text,
                voice=selection.edge_voice,
            )
        elif candidate == "piper":
            audio_url = await generate_tts_piper(
                text,
                voice_name=selection.piper_voice,
            )
        elif candidate == "gtts":
            audio_url = generate_tts_gtts(text)

        if audio_url:
            return audio_url, candidate

    return None, "none"


@router.post("/voice/process")
async def process_voice(
    audio: UploadFile = File(...),
    session_id: str = Form(...),
    tts_provider: Literal["auto", "elevenlabs", "edge", "piper", "gtts"] = Form("auto"),
    tts_voice_id: str | None = Form(default=None),
    tts_model_id: str | None = Form(default=None),
    tts_edge_voice: str | None = Form(default=None),
    tts_piper_voice: str | None = Form(default=None),
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
        selection = TTSSelection(
            provider=tts_provider,
            voice_id=tts_voice_id,
            model_id=tts_model_id,
            edge_voice=tts_edge_voice,
            piper_voice=tts_piper_voice,
        )
        audio_url, provider_used = await generate_tts(response, selection)

        return JSONResponse({
            "transcript": transcript,
            "response": response,
            "audio_url": audio_url,
            "tts_provider_requested": selection.provider,
            "tts_provider_used": provider_used,
            "latency_ms": metadata.first_token_ms,
            "production_parity": False,
            "notice": NON_PRODUCTION_PARITY_NOTICE,
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

    suffix = audio_path.suffix.lower()
    if suffix == ".wav":
        media_type = "audio/wav"
    elif suffix == ".mp3":
        media_type = "audio/mpeg"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        audio_path,
        media_type=media_type,
        filename=filename,
    )


@router.post("/voice/tts")
async def text_to_speech(request: TextToSpeechRequest):
    """Generate TTS audio from text."""
    selection = TTSSelection(
        provider=request.provider,
        voice_id=request.voice_id,
        model_id=request.model_id,
        edge_voice=request.edge_voice,
        piper_voice=request.piper_voice,
    )
    audio_url, provider_used = await generate_tts(request.text, selection)
    return JSONResponse({
        "audio_url": audio_url,
        "tts_provider_requested": selection.provider,
        "tts_provider_used": provider_used,
        "production_parity": False,
        "notice": NON_PRODUCTION_PARITY_NOTICE,
    })


class EndSessionRequest(BaseModel):
    """Request body for ending a voice test session."""

    session_id: str


class EndSessionResponse(BaseModel):
    """Response for ending a voice test session."""

    call_log_id: str
    total_turns: int
    analysis_queued: bool


@router.post("/voice/end-session", response_model=EndSessionResponse)
async def end_session(request: EndSessionRequest):
    """End a voice test session and persist call log.

    This endpoint:
    1. Creates a CallLog entry with call_source='voice_test'
    2. Queues the analyze_transcript_quality background job
    3. Cleans up the in-memory session

    Returns the call_log_id for tracking.
    """
    session_id = request.session_id

    # Get session data
    session = _sessions.get(session_id)
    if not session:
        return JSONResponse(
            {"error": f"Session not found: {session_id}"},
            status_code=404,
        )

    try:
        # Get transcript and metrics from session
        transcript = session.get_transcript()
        metrics = session.get_metrics()
        now = datetime.now(UTC)

        # Calculate duration
        duration_seconds = int((now - session.call_start).total_seconds())

        # Create CallLog entry
        async with get_session_context() as db_session:
            call_log = CallLog(
                id=session.call_id,
                business_id=session.business_id,
                caller_id_hash=None,  # No phone for browser tests
                call_start=session.call_start,
                call_end=now,
                duration_seconds=duration_seconds,
                detected_language=(
                    session.detected_language
                    if session.detected_language.value != "unknown"
                    else None
                ),
                transcript=transcript if transcript else None,
                extracted_info=None,
                outcome=CallOutcome.resolved,
                consent_type=None,
                call_source=CallSource.voice_test,
                stt_latency_p50_ms=metrics.get("p50_first_word_ms"),
                llm_latency_p50_ms=metrics.get("p50_first_token_ms"),
                total_turns=metrics.get("total_llm_calls", 0),
            )
            db_session.add(call_log)
            await db_session.commit()
            await db_session.refresh(call_log)

            logger.info(f"Created call log for voice test: {call_log.id}")

        # Queue background analysis job
        analysis_queued = False
        if transcript:
            try:
                settings = get_settings()
                from arq import create_pool

                pool = await create_pool(settings.redis_settings)
                try:
                    await pool.enqueue_job("generate_call_summary", session.call_id)
                    await pool.enqueue_job("analyze_transcript_quality", session.call_id)
                    analysis_queued = True
                    logger.info(f"Queued analysis for voice test: {session.call_id}")
                finally:
                    await pool.close()
            except Exception as e:
                logger.warning(f"Failed to queue analysis job: {e}")

        # Clean up session
        await session.close()
        del _sessions[session_id]

        return EndSessionResponse(
            call_log_id=session.call_id,
            total_turns=metrics.get("total_llm_calls", 0),
            analysis_queued=analysis_queued,
        )

    except Exception as e:
        logger.exception(f"Error ending session {session_id}")
        return JSONResponse(
            {"error": str(e)},
            status_code=500,
        )
