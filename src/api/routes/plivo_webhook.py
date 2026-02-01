"""Plivo webhook handlers for call lifecycle management.

Handles:
- Answer webhook: Returns XML to initiate WebSocket streaming
- Hangup webhook: Logs call metrics and cleans up
- Fallback webhook: Error handling
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from src.api.websocket.audio_stream import CallCapacityError, call_registry
from src.config import Settings, get_settings
from src.db.repositories.businesses import AsyncBusinessRepository
from src.db.repositories.calls import AsyncCallLogRepository
from src.db.session import get_session_context
from src.logging_config import get_logger
from src.security.crypto import hash_phone_for_dedup
from src.services.telephony.plivo import PlivoCallInfo, PlivoService

router = APIRouter(prefix="/plivo", tags=["Plivo"])
logger: Any = get_logger(__name__)


def get_plivo_service(settings: Settings = Depends(get_settings)) -> PlivoService:
    """Dependency injection for PlivoService."""
    return PlivoService(settings=settings)


@router.post("/webhook/answer")
async def plivo_answer_webhook(
    request: Request,
    plivo: PlivoService = Depends(get_plivo_service),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Handle incoming call answer event from Plivo.

    Returns XML that initiates bidirectional audio streaming.

    Expected form data:
    - CallUUID: Unique call identifier
    - From: Caller phone number
    - To: Called phone number
    - Direction: inbound/outbound
    - CallStatus: current call status
    """
    form_data = await request.form()
    form_dict = {k: str(v) for k, v in form_data.items()}

    # Parse call info
    call_info = PlivoCallInfo.from_webhook(form_dict)

    logger.info(
        f"Call answered: {call_info.call_uuid}",
        extra={
            "direction": call_info.direction,
            "to": call_info.to_number[-4:] if call_info.to_number else "",
        },
    )

    # Hash caller phone for privacy (never log raw number)
    caller_id_hash = None
    if call_info.from_number:
        try:
            caller_id_hash = hash_phone_for_dedup(call_info.from_number)
        except Exception as e:
            logger.warning(f"Failed to hash caller ID: {e}")

    # Resolve business from "To" phone number
    # SECURITY: Do NOT default to any business - fail safely if unknown
    business_id: str | None = None
    greeting_text = None

    if call_info.to_number:
        try:
            async with get_session_context() as db_session:
                repo = AsyncBusinessRepository(db_session)
                business = await repo.get_by_phone_number(call_info.to_number)
                if business:
                    business_id = business.id
                    greeting_text = business.greeting_text
                    logger.info(f"Resolved business: {business_id} for {call_info.to_number[-4:]}")
                else:
                    logger.warning(
                        f"No business configured for phone {call_info.to_number[-4:]}"
                    )
        except Exception as e:
            logger.error(f"Failed to resolve business: {e}")

    # SECURITY: If no business found, return error and hangup - never route to wrong business
    if business_id is None:
        logger.error(
            f"Call {call_info.call_uuid} rejected: no business for {call_info.to_number[-4:]}"
        )
        xml_response = plivo.generate_hangup_xml(
            reason="Yeh number abhi configure nahi hai. Kripya baad mein try karein."
        )
        return Response(content=xml_response, media_type="application/xml")

    # Pre-create session in registry (with capacity check)
    try:
        await call_registry.create(
            call_info.call_uuid,
            business_id=business_id,
            caller_id_hash=caller_id_hash,
            greeting_text=greeting_text,
            settings=settings,
        )
    except CallCapacityError:
        logger.warning(f"Call {call_info.call_uuid} rejected: system at capacity")
        xml_response = plivo.generate_hangup_xml(
            reason="Abhi hamari lines busy hain. Kripya kuch der baad call karein."
        )
        return Response(content=xml_response, media_type="application/xml")

    # Build WebSocket URL for audio streaming
    # Use forwarded headers if behind proxy
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost:8000")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    scheme = "wss" if proto == "https" else "ws"
    websocket_url = f"{scheme}://{host}/ws/audio/{call_info.call_uuid}"

    # Determine content type based on settings
    if settings.plivo_audio_format == "mulaw":
        content_type = "audio/basic"  # μ-law
    else:
        content_type = f"audio/x-l16;rate={settings.plivo_sample_rate}"

    # Generate XML response to initiate streaming
    xml_response = plivo.generate_stream_xml(
        websocket_url=websocket_url,
        bidirectional=True,
        content_type=content_type,
    )

    logger.debug(f"Returning stream XML for {call_info.call_uuid}")

    return Response(
        content=xml_response,
        media_type="application/xml",
    )


@router.post("/webhook/hangup")
async def plivo_hangup_webhook(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    """Handle call hangup event from Plivo.

    Logs call metrics and cleans up session.

    Expected form data:
    - CallUUID: Unique call identifier
    - Duration: Call duration in seconds
    - HangupCause: Reason for hangup
    - EndTime: When call ended
    """
    form_data = await request.form()

    call_uuid = str(form_data.get("CallUUID", ""))
    duration = str(form_data.get("Duration", "0"))
    hangup_cause = str(form_data.get("HangupCause", ""))

    logger.info(
        f"Call ended: {call_uuid}",
        extra={"duration": duration, "cause": hangup_cause},
    )

    # Get session and persist final metrics
    result = await call_registry.get(call_uuid)
    if result:
        session, pipeline = result

        try:
            # Finalize pipeline and get metrics
            metrics = await pipeline.finalize()

            # Log to database with latency metrics
            async with get_session_context() as db_session:
                repo = AsyncCallLogRepository(db_session)
                await repo.upsert_call_log(
                    call_id=call_uuid,
                    business_id=session.business_id,
                    caller_id_hash=session.caller_id_hash,
                    duration_seconds=int(duration),
                    transcript=metrics.get("transcript"),
                    detected_language=session.detected_language,
                    # Performance metrics (prefer session metrics, fallback to pipeline)
                    stt_latency_p50_ms=(
                        metrics.get("p50_first_word_ms") or metrics.get("p50_stt_latency_ms")
                    ),
                    llm_latency_p50_ms=(
                        metrics.get("p50_first_token_ms") or metrics.get("p50_llm_first_token_ms")
                    ),
                    tts_latency_p50_ms=metrics.get("p50_tts_first_chunk_ms"),
                    barge_in_count=metrics.get("barge_in_count", 0),
                    total_turns=metrics.get("total_turns", 0),
                )
                await db_session.commit()

            logger.info(f"Persisted final metrics for {call_uuid}")

            # Queue summary generation and transcript analysis if transcript exists
            if metrics.get("transcript"):
                try:
                    from arq import create_pool

                    pool = await create_pool(settings.redis_settings)
                    await pool.enqueue_job("generate_call_summary", call_uuid)
                    logger.debug(f"Queued summary generation for {call_uuid}")

                    # Queue transcript analysis for QA (runs after summary)
                    await pool.enqueue_job("analyze_transcript_quality", call_uuid)
                    logger.debug(f"Queued transcript analysis for {call_uuid}")

                    await pool.close()
                except Exception as e:
                    logger.warning(f"Failed to queue background jobs: {e}")

        except Exception as e:
            logger.error(f"Error persisting call metrics: {e}")

        # Cleanup registry
        await call_registry.remove(call_uuid)

    return {"ok": True}


@router.post("/webhook/fallback")
async def plivo_fallback_webhook(
    request: Request,
    plivo: PlivoService = Depends(get_plivo_service),
) -> Response:
    """Fallback handler for Plivo errors.

    Called when the primary answer webhook fails.
    Returns a simple apology message and hangs up.
    """
    form_data = await request.form()
    call_uuid = str(form_data.get("CallUUID", ""))
    error = str(form_data.get("ErrorMessage", "Unknown error"))

    logger.error(f"Plivo fallback triggered: {call_uuid} - {error}")

    # Return hangup XML with apology
    xml_response = plivo.generate_hangup_xml(
        reason="Maaf kijiye, technical problem aa gayi hai. Kripya baad mein call karein."
    )

    return Response(
        content=xml_response,
        media_type="application/xml",
    )


@router.post("/webhook/ringing")
async def plivo_ringing_webhook(request: Request) -> dict[str, bool]:
    """Handle call ringing event (optional).

    Can be used for analytics or early session setup.
    """
    form_data = await request.form()
    call_uuid = str(form_data.get("CallUUID", ""))

    logger.debug(f"Call ringing: {call_uuid}")

    return {"ok": True}


@router.get("/health")
async def plivo_health(
    plivo: PlivoService = Depends(get_plivo_service),
) -> dict[str, Any]:
    """Check Plivo service health.

    Verifies:
    - Plivo API credentials are valid
    - Call registry is accessible
    """
    plivo_healthy = await plivo.health_check()

    return {
        "healthy": plivo_healthy,
        "active_calls": call_registry.active_count,
    }
