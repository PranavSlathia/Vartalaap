"""Voice API endpoint for browser-based voice testing."""

import asyncio
import contextlib
import time
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
from src.services.tts.cartesia import CartesiaTTSService

logger = get_logger(__name__)

router = APIRouter()

# Store sessions in memory (for demo - use Redis in production)
_sessions: dict[str, CallSession] = {}
# Track audio files per session for per-session cleanup
_session_audio_files: dict[str, list[Path]] = {}

# Directory for temp audio files
AUDIO_DIR = Path("data/audio_cache")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Browser TTS uses higher sample rate than telephony (8kHz) for better quality
_BROWSER_SAMPLE_RATE = 22050

NON_PRODUCTION_PARITY_NOTICE = (
    "Browser voice test uses a non-production path and may differ from live telephony quality."
)


def _cleanup_old_audio_files() -> None:
    """Delete WAV files older than 24h from audio cache (runs once on startup)."""
    cutoff = datetime.now(UTC).timestamp() - 86400
    removed = 0
    for wav_file in AUDIO_DIR.glob("*.wav"):
        try:
            if wav_file.stat().st_mtime < cutoff:
                wav_file.unlink(missing_ok=True)
                removed += 1
        except OSError:
            pass
    if removed:
        logger.info(f"Startup cleanup: removed {removed} stale WAV files from audio cache")


# Run once on module import (i.e., startup)
_cleanup_old_audio_files()


class TextToSpeechRequest(BaseModel):
    """Request body for direct browser TTS generation."""

    text: str = Field(min_length=1)


class _TranscriptionResult:
    """Internal result from STT transcription with metadata."""

    __slots__ = ("transcript", "detected_language", "confidence", "latency_ms")

    def __init__(
        self,
        transcript: str,
        detected_language: str | None = None,
        confidence: float | None = None,
        latency_ms: float | None = None,
    ) -> None:
        self.transcript = transcript
        self.detected_language = detected_language
        self.confidence = confidence
        self.latency_ms = latency_ms


def get_or_create_session(session_id: str, business_id: str = "himalayan_kitchen") -> CallSession:
    """Get existing session or create a new one.

    Evicts sessions older than 30 minutes before creating to prevent unbounded growth.
    """
    now = datetime.now(UTC)
    stale = [
        sid
        for sid, sess in _sessions.items()
        if (now - sess.call_start).total_seconds() > 1800
    ]
    for sid in stale:
        _sessions.pop(sid, None)
        _session_audio_files.pop(sid, None)

    if session_id not in _sessions:
        _sessions[session_id] = CallSession(business_id=business_id)
    return _sessions[session_id]


async def transcribe_webm(audio_data: bytes) -> _TranscriptionResult:
    """Transcribe webm audio using Deepgram.

    Returns transcript, language, confidence, and latency.
    Raises on STT service failure — caller should return HTTP 422.
    """
    from deepgram import DeepgramClient, PrerecordedOptions

    t0 = time.perf_counter()
    settings = get_settings()
    client = DeepgramClient(api_key=settings.deepgram_api_key.get_secret_value())

    options = PrerecordedOptions(
        model="nova-2",
        detect_language=True,
        smart_format=True,
        punctuate=True,
    )

    response = await asyncio.to_thread(
        client.listen.rest.v("1").transcribe_file,
        {"buffer": audio_data, "mimetype": "audio/webm"},
        options,
    )

    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    results = response.results
    if results and results.channels:
        channel = results.channels[0]
        alternatives = channel.alternatives
        if alternatives:
            alt = alternatives[0]
            transcript: str = alt.transcript or ""
            confidence: float | None = getattr(alt, "confidence", None)
            detected_language: str | None = getattr(channel, "detected_language", None)
            logger.info(
                f"Transcribed ({latency_ms:.0f}ms): {transcript[:50]}..."
                if transcript
                else f"No transcript ({latency_ms:.0f}ms)"
            )
            return _TranscriptionResult(
                transcript=transcript,
                detected_language=detected_language,
                confidence=confidence,
                latency_ms=latency_ms,
            )

    return _TranscriptionResult(transcript="", latency_ms=latency_ms)


def _save_audio_bytes(audio_bytes: bytes, suffix: str, session_id: str | None = None) -> str:
    """Persist generated audio bytes and return public URL.

    Tracks the file path in _session_audio_files if session_id provided,
    enabling per-session cleanup when the session ends.
    """
    audio_id = str(uuid.uuid4())[:8]
    filename = f"{audio_id}.{suffix}"
    audio_path = AUDIO_DIR / filename
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    if session_id:
        _session_audio_files.setdefault(session_id, []).append(audio_path)

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


async def generate_tts_cartesia(
    text: str, session_id: str | None = None
) -> tuple[str | None, float | None]:
    """Generate TTS audio using Cartesia Sonic.

    Returns (audio_url, first_chunk_ms). Both None on failure.
    """
    settings = get_settings()
    service = CartesiaTTSService(
        api_key=settings.cartesia_api_key.get_secret_value(),
        voice_id=settings.cartesia_voice_id,
        model_id=settings.cartesia_model_id,
    )
    try:
        pcm_chunks: list[bytes] = []
        first_chunk_ms: float | None = None
        t0 = time.perf_counter()
        async for chunk in service.synthesize_stream(
            text,
            target_sample_rate=_BROWSER_SAMPLE_RATE,
        ):
            if first_chunk_ms is None:
                first_chunk_ms = round((time.perf_counter() - t0) * 1000, 1)
            pcm_chunks.append(chunk)

        if not pcm_chunks:
            return None, None

        raw_pcm = b"".join(pcm_chunks)
        wav_bytes = _pcm16_to_wav_bytes(raw_pcm, sample_rate=_BROWSER_SAMPLE_RATE)
        audio_url = _save_audio_bytes(wav_bytes, "wav", session_id=session_id)
        logger.info(
            f"Generated Cartesia TTS: {audio_url} ({len(raw_pcm)} bytes PCM,"
            f" first_chunk={first_chunk_ms}ms)"
        )
        return audio_url, first_chunk_ms

    except Exception as e:
        logger.error(f"Cartesia TTS error: {e}")
        return None, None
    finally:
        await service.close()


def _build_voice_compare_response(transcript: str) -> str:
    """Fast, deterministic response for voice comparison mode."""
    cleaned = transcript.strip()
    if not cleaned:
        return "I could not catch that. Please try once more."

    has_devanagari = any("\u0900" <= ch <= "\u097F" for ch in cleaned)
    if has_devanagari:
        return f"ठीक है, मैंने सुना: {cleaned}"
    return f"Got it. I heard: {cleaned}"


@router.post("/voice/process")
async def process_voice(
    audio: UploadFile = File(...),
    session_id: str = Form(...),
    response_mode: Literal["echo", "agent"] = Form(default="echo"),
    business_id: str = Form(default="himalayan_kitchen"),
):
    """Process voice input and return response with audio and full latency breakdown."""
    t_start = time.perf_counter()
    try:
        audio_data = await audio.read()
        logger.info(f"Received audio: {len(audio_data)} bytes, session: {session_id}")

        # STT — raise so caller returns 422 with specific error
        try:
            stt_result = await transcribe_webm(audio_data)
        except Exception as e:
            logger.error(f"STT failed for session {session_id}: {e}")
            return JSONResponse(
                {"error": "stt_failed", "detail": str(e)},
                status_code=422,
            )

        if not stt_result.transcript:
            return JSONResponse({
                "error": "Could not understand. Please try again.",
                "transcript": None,
                "response": None,
            })

        # LLM
        llm_first_token_ms: float | None = None
        if response_mode == "agent":
            session = get_or_create_session(session_id, business_id=business_id)
            response, metadata = await session.process_user_input(stt_result.transcript)
            llm_first_token_ms = metadata.first_token_ms
        else:
            from src.services.llm.protocol import StreamMetadata

            response = _build_voice_compare_response(stt_result.transcript)
            metadata = StreamMetadata(model="voice-compare")

        # TTS
        audio_url, tts_first_chunk_ms = await generate_tts_cartesia(
            response, session_id=session_id
        )

        total_ms = round((time.perf_counter() - t_start) * 1000, 1)

        return JSONResponse({
            "transcript": stt_result.transcript,
            "response": response,
            "audio_url": audio_url,
            "tts_provider_used": "cartesia",
            "response_mode": response_mode,
            "stt_latency_ms": stt_result.latency_ms,
            "llm_first_token_ms": llm_first_token_ms,
            "tts_first_chunk_ms": tts_first_chunk_ms,
            "total_ms": total_ms,
            "detected_language": stt_result.detected_language,
            "stt_confidence": stt_result.confidence,
            "production_parity": False,
            "notice": NON_PRODUCTION_PARITY_NOTICE,
        })

    except Exception as e:
        logger.exception("Voice processing error")
        return JSONResponse(
            {"error": str(e), "transcript": None, "response": None},
            status_code=500,
        )


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
    """Generate TTS audio from text using Cartesia Sonic."""
    audio_url, _ = await generate_tts_cartesia(request.text)
    return JSONResponse({
        "audio_url": audio_url,
        "tts_provider_used": "cartesia",
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

    1. Creates a CallLog entry with call_source='voice_test'
    2. Queues the analyze_transcript_quality background job
    3. Deletes per-session audio cache files
    4. Cleans up the in-memory session
    """
    session_id = request.session_id

    session = _sessions.get(session_id)
    if not session:
        return JSONResponse(
            {"error": f"Session not found: {session_id}"},
            status_code=404,
        )

    try:
        transcript = session.get_transcript()
        metrics = session.get_metrics()
        now = datetime.now(UTC)

        duration_seconds = int((now - session.call_start).total_seconds())

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

        # Clean up per-session audio files
        audio_files = _session_audio_files.pop(session_id, [])
        for wav_path in audio_files:
            with contextlib.suppress(OSError):
                wav_path.unlink(missing_ok=True)
        if audio_files:
            logger.info(f"Cleaned up {len(audio_files)} audio files for session {session_id}")

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
