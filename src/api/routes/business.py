"""Business settings API routes.

Security: Endpoints require authentication and tenant scoping.
Admins can list/create businesses, while tenant-scoped routes remain isolated.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import delete, select

from src.api.auth import RequireAuth, RequireBusinessAccess
from src.config import get_settings
from src.db.models import Business, BusinessPhoneNumber, BusinessStatus, BusinessType
from src.db.session import get_session

router = APIRouter(prefix="/api/business", tags=["business"])

# Valid time format HH:MM (supports single-digit hours like 9:00)
TIME_PATTERN = re.compile(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
VALID_DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}

LEGACY_RULE_KEYS = {
    "max_advance_booking_days": "advance_days",
    "dining_window_mins": "slot_duration_minutes",
    "buffer_between_bookings_mins": "buffer_between_bookings_minutes",
}

EDGE_VOICE_OPTIONS = [
    {"id": "hi-IN-SwaraNeural", "name": "Swara (Hindi, Female)", "language": "hi-IN"},
    {"id": "hi-IN-MadhurNeural", "name": "Madhur (Hindi, Male)", "language": "hi-IN"},
    {"id": "en-IN-NeerjaNeural", "name": "Neerja (English India, Female)", "language": "en-IN"},
    {"id": "en-IN-PrabhatNeural", "name": "Prabhat (English India, Male)", "language": "en-IN"},
]

ELEVENLABS_MODEL_FALLBACKS = [
    {"id": "eleven_multilingual_v2", "name": "Multilingual v2", "language": "multilingual"},
    {"id": "eleven_flash_v2_5", "name": "Flash v2.5", "language": "multilingual"},
    {"id": "eleven_turbo_v2_5", "name": "Turbo v2.5", "language": "multilingual"},
]

ELEVENLABS_VOICE_FALLBACKS = [
    {"id": "9BWtsMINqrJLrRacOk9x", "name": "Aria", "language": "multilingual"},
]


def default_reservation_rules() -> "ReservationRules":
    """Create default reservation rules."""
    return ReservationRules.model_validate({})


def default_voice_profile() -> "VoiceProfile":
    """Create default voice profile."""
    return VoiceProfile.model_validate({})


def default_rag_profile() -> "RagProfile":
    """Create default RAG profile."""
    return RagProfile.model_validate({})


# =============================================================================
# Request/Response Schemas
# =============================================================================


def time_to_minutes(time_str: str) -> int:
    """Convert HH:MM time string to minutes since midnight.

    Handles single-digit hours (e.g., "9:00" → 540, "10:00" → 600).
    This avoids string comparison bugs like "10:00" < "9:00".
    """
    hours, minutes = time_str.split(":")
    return int(hours) * 60 + int(minutes)


class OperatingHours(BaseModel):
    """Operating hours for a single day."""

    open: str | None = Field(None, description="Opening time (HH:MM) or null if closed")
    close: str | None = Field(None, description="Closing time (HH:MM) or null if closed")
    overnight: bool = Field(
        False,
        description="True if close time is the next day (e.g., 22:00-02:00)",
    )

    @model_validator(mode="after")
    def validate_times(self) -> "OperatingHours":
        """Validate time format and order."""
        if self.open is not None and not TIME_PATTERN.match(self.open):
            raise ValueError(f"Invalid opening time format: {self.open}. Use HH:MM.")
        if self.close is not None and not TIME_PATTERN.match(self.close):
            raise ValueError(f"Invalid closing time format: {self.close}. Use HH:MM.")

        if self.open and self.close:
            # Convert to minutes for proper numeric comparison
            open_mins = time_to_minutes(self.open)
            close_mins = time_to_minutes(self.close)

            if self.overnight:
                # Overnight hours: close can be <= open (e.g., 22:00-02:00)
                # But must make sense (not 02:00-02:00)
                if open_mins == close_mins:
                    raise ValueError("Open and close times cannot be identical")
            else:
                # Same-day hours: close must be after open
                if close_mins <= open_mins:
                    raise ValueError(
                        f"Closing time ({self.close}) must be after opening ({self.open}). "
                        "For overnight hours (e.g., 22:00-02:00), set overnight: true"
                    )
        return self


class ReservationRules(BaseModel):
    """Reservation rules for the business."""

    min_party_size: int = Field(1, ge=1)
    max_party_size: int = Field(10, ge=1)
    max_phone_party_size: int = Field(
        10, ge=1, description="Max party size bookable by phone (larger → WhatsApp)"
    )
    total_seats: int = Field(40, ge=1)
    advance_days: int = Field(30, ge=1, description="How many days ahead can book")
    slot_duration_minutes: int = Field(90, ge=15)
    buffer_between_bookings_minutes: int = Field(
        15,
        ge=0,
        description="Buffer between bookings in minutes",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_keys(cls, data: Any) -> Any:
        """Accept legacy YAML-style keys and normalize to canonical API keys."""
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        for old_key, new_key in LEGACY_RULE_KEYS.items():
            if new_key not in normalized and old_key in normalized:
                normalized[new_key] = normalized[old_key]
        return normalized

    @model_validator(mode="after")
    def validate_party_sizes(self) -> "ReservationRules":
        """Validate cross-field constraints."""
        if self.min_party_size > self.max_party_size:
            raise ValueError(
                f"min_party_size ({self.min_party_size}) cannot exceed "
                f"max_party_size ({self.max_party_size})"
            )
        if self.max_phone_party_size > self.max_party_size:
            raise ValueError(
                f"max_phone_party_size ({self.max_phone_party_size}) cannot exceed "
                f"max_party_size ({self.max_party_size})"
            )
        # Ensure phone booking is possible (min_party_size must be achievable by phone)
        if self.min_party_size > self.max_phone_party_size:
            raise ValueError(
                f"min_party_size ({self.min_party_size}) cannot exceed "
                f"max_phone_party_size ({self.max_phone_party_size}). "
                "This would make phone booking impossible."
            )
        if self.max_party_size > self.total_seats:
            raise ValueError(
                f"max_party_size ({self.max_party_size}) cannot exceed "
                f"total_seats ({self.total_seats})"
            )
        return self


class VoiceProfile(BaseModel):
    """Voice provider/runtime settings for a business."""

    provider: Literal["auto", "elevenlabs", "piper", "edge"] = Field(
        default="auto",
        description="Preferred provider: auto, elevenlabs, piper, or edge",
    )
    voice_id: str | None = None
    model_id: str | None = None
    piper_voice: str | None = None
    edge_voice: str | None = None
    speaking_style: str | None = None
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    similarity_boost: float | None = Field(default=None, ge=0.0, le=1.0)


class VoiceCatalogItem(BaseModel):
    """Voice/model option for frontend selection."""

    id: str
    name: str
    language: str | None = None
    hindi_recommended: bool = False


class VoicePreset(BaseModel):
    """Ready-to-test preset for comparing TTS quality."""

    id: str
    name: str
    description: str
    provider: Literal["auto", "elevenlabs", "piper", "edge"]
    voice_id: str | None = None
    model_id: str | None = None
    piper_voice: str | None = None
    edge_voice: str | None = None


class VoiceOptionsResponse(BaseModel):
    """Catalog of available voice providers, models, and recommended presets."""

    providers: list[Literal["auto", "elevenlabs", "piper", "edge"]]
    provider_status: dict[str, bool]
    elevenlabs_models: list[VoiceCatalogItem]
    elevenlabs_voices: list[VoiceCatalogItem]
    piper_voices: list[VoiceCatalogItem]
    edge_voices: list[VoiceCatalogItem]
    recommended_presets: list[VoicePreset]


class RagProfile(BaseModel):
    """RAG retrieval settings for a business."""

    enabled: bool = True
    max_results: int = Field(default=5, ge=1, le=10)
    min_score: float = Field(default=0.3, ge=0.0, le=1.0)


class BusinessResponse(BaseModel):
    """Business settings response."""

    id: str
    name: str
    type: BusinessType
    timezone: str
    status: BusinessStatus
    phone_numbers: list[str]
    operating_hours: dict[str, OperatingHours | str]
    reservation_rules: ReservationRules
    greeting_text: str | None
    menu_summary: str | None
    voice_profile: VoiceProfile
    rag_profile: RagProfile


class BusinessUpdate(BaseModel):
    """Business settings update request."""

    name: str | None = None
    timezone: str | None = None
    phone_numbers: list[str] | None = None
    operating_hours: dict[str, OperatingHours | str] | None = None
    reservation_rules: ReservationRules | None = None
    greeting_text: str | None = None
    menu_summary: str | None = None
    voice_profile: VoiceProfile | None = None
    rag_profile: RagProfile | None = None

    @model_validator(mode="after")
    def validate_operating_hours(self) -> "BusinessUpdate":
        """Validate operating hours structure."""
        if self.operating_hours:
            for day, hours in self.operating_hours.items():
                if day.lower() not in VALID_DAYS:
                    raise ValueError(f"Invalid day name: {day}. Must be one of: {VALID_DAYS}")
                # Allow "closed" string or OperatingHours object
                if isinstance(hours, str) and hours.lower() != "closed":
                    raise ValueError(
                        f"Invalid hours for {day}: '{hours}'. "
                        "Use 'closed' or {{open: 'HH:MM', close: 'HH:MM'}}"
                    )
        return self

    @model_validator(mode="after")
    def validate_phone_numbers(self) -> "BusinessUpdate":
        """Validate phone numbers are E.164 format."""
        if self.phone_numbers:
            for phone in self.phone_numbers:
                if not phone.startswith("+") or not phone[1:].isdigit():
                    raise ValueError(f"Invalid E.164 phone number: {phone}")
        return self

    @model_validator(mode="after")
    def validate_timezone(self) -> "BusinessUpdate":
        """Validate timezone is a valid IANA name."""
        if self.timezone:
            try:
                ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError as e:
                raise ValueError(
                    f"Invalid timezone: '{self.timezone}'. "
                    "Use IANA timezone names like 'Asia/Kolkata' or 'America/New_York'."
                ) from e
        return self


class BusinessCreate(BaseModel):
    """Create request for onboarding a new business."""

    id: str = Field(
        min_length=3,
        max_length=50,
        pattern=r"^[a-z0-9_]+$",
        description="Slug ID (lowercase letters, numbers, underscores)",
    )
    name: str = Field(min_length=1, max_length=200)
    type: BusinessType = BusinessType.other
    timezone: str = Field(default="Asia/Kolkata")
    status: BusinessStatus = BusinessStatus.onboarding
    phone_numbers: list[str] = Field(default_factory=list)
    operating_hours: dict[str, OperatingHours | str] = Field(default_factory=dict)
    reservation_rules: ReservationRules = Field(default_factory=default_reservation_rules)
    greeting_text: str | None = None
    menu_summary: str | None = None
    voice_profile: VoiceProfile = Field(default_factory=default_voice_profile)
    rag_profile: RagProfile = Field(default_factory=default_rag_profile)

    @model_validator(mode="after")
    def validate_timezone(self) -> "BusinessCreate":
        """Validate timezone is a valid IANA name."""
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as e:
            raise ValueError(
                f"Invalid timezone: '{self.timezone}'. "
                "Use IANA timezone names like 'Asia/Kolkata' or 'America/New_York'."
            ) from e
        return self

    @model_validator(mode="after")
    def validate_phone_numbers(self) -> "BusinessCreate":
        """Validate phone numbers are E.164 format."""
        for phone in self.phone_numbers:
            if not phone.startswith("+") or not phone[1:].isdigit():
                raise ValueError(f"Invalid E.164 phone number: {phone}")
        return self


# =============================================================================
# Helper Functions
# =============================================================================


def parse_json_field(json_str: str | None, default: dict | list) -> dict | list:
    """Safely parse JSON field."""
    if not json_str:
        return default
    try:
        import json

        result = json.loads(json_str)
        return result  # type: ignore[no-any-return]
    except (json.JSONDecodeError, TypeError):
        return default


def serialize_json_field(value: dict | list | None) -> str | None:
    """Serialize to JSON string."""
    if value is None:
        return None
    import json

    return json.dumps(value)


def normalize_reservation_rules(data: dict[str, Any] | None) -> ReservationRules:
    """Normalize reservation rules to canonical API schema."""
    rules = data or {}
    return ReservationRules(**rules)


def parse_profile(
    json_str: str | None,
    profile_type: type[VoiceProfile] | type[RagProfile],
) -> VoiceProfile | RagProfile:
    """Parse a profile JSON column into a typed profile object."""
    if not json_str:
        return profile_type()
    try:
        raw = json.loads(json_str)
        if isinstance(raw, dict):
            return profile_type(**raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return profile_type()


def business_to_response(business: Business) -> BusinessResponse:
    """Convert Business model to response."""
    phone_numbers = parse_json_field(business.phone_numbers_json, [])
    operating_hours = parse_json_field(business.operating_hours_json, {})
    reservation_rules_dict = parse_json_field(business.reservation_rules_json, {})
    reservation_rules = (
        normalize_reservation_rules(reservation_rules_dict)
        if isinstance(reservation_rules_dict, dict)
        else default_reservation_rules()
    )

    return BusinessResponse(
        id=business.id,
        name=business.name,
        type=business.type,
        timezone=business.timezone,
        status=business.status,
        phone_numbers=phone_numbers if isinstance(phone_numbers, list) else [],
        operating_hours=operating_hours if isinstance(operating_hours, dict) else {},
        reservation_rules=reservation_rules,
        greeting_text=business.greeting_text,
        menu_summary=business.menu_summary,
        voice_profile=parse_profile(business.voice_profile_json, VoiceProfile),  # type: ignore[arg-type]
        rag_profile=parse_profile(business.rag_profile_json, RagProfile),  # type: ignore[arg-type]
    )


async def sync_phone_numbers(
    session: AsyncSession, business_id: str, phone_numbers: list[str]
) -> None:
    """Sync phone numbers to the lookup table.

    Removes old numbers and adds new ones to ensure call routing works.
    """
    # Delete existing phone numbers for this business
    await session.execute(
        delete(BusinessPhoneNumber).where(BusinessPhoneNumber.business_id == business_id)  # type: ignore[arg-type]
    )

    # Add new phone numbers
    for i, phone in enumerate(phone_numbers):
        phone_record = BusinessPhoneNumber(
            phone_number=phone,
            business_id=business_id,
            is_primary=(i == 0),  # First number is primary
        )
        session.add(phone_record)


def _is_hindi_like(*values: str | None) -> bool:
    combined = " ".join(v.lower() for v in values if v)
    return "hindi" in combined or "hi-" in combined or " hi" in combined


def _voice_item(
    item_id: str,
    name: str,
    language: str | None = None,
    *,
    hindi_recommended: bool = False,
) -> VoiceCatalogItem:
    return VoiceCatalogItem(
        id=item_id,
        name=name,
        language=language,
        hindi_recommended=hindi_recommended,
    )


async def _fetch_elevenlabs_models() -> list[VoiceCatalogItem]:
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        return [
            _voice_item(
                item["id"],
                item["name"],
                item["language"],
                hindi_recommended="multilingual" in (item["language"] or ""),
            )
            for item in ELEVENLABS_MODEL_FALLBACKS
        ]

    url = "https://api.elevenlabs.io/v1/models"
    headers = {"xi-api-key": settings.elevenlabs_api_key.get_secret_value()}

    models: list[VoiceCatalogItem] = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        payload = []

    if isinstance(payload, list):
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            model_id = raw.get("model_id") or raw.get("id")
            if not model_id:
                continue

            # If the API exposes capability flags, keep only TTS-capable models.
            can_tts = raw.get("can_do_text_to_speech")
            if can_tts is False:
                continue

            name = str(raw.get("name") or model_id)
            language = "multilingual" if "multilingual" in name.lower() else None
            if language is None:
                langs = raw.get("languages") or raw.get("supported_languages")
                if isinstance(langs, list):
                    collected: list[str] = []
                    for lang_item in langs:
                        if isinstance(lang_item, dict):
                            code = lang_item.get("language_id") or lang_item.get("language")
                            if isinstance(code, str):
                                collected.append(code)
                        elif isinstance(lang_item, str):
                            collected.append(lang_item)
                    if collected:
                        language = ", ".join(collected[:3])

            models.append(
                _voice_item(
                    str(model_id),
                    name,
                    language,
                    hindi_recommended=_is_hindi_like(language, name)
                    or "multilingual" in name.lower(),
                )
            )

    if not models:
        models = [
            _voice_item(
                item["id"],
                item["name"],
                item["language"],
                hindi_recommended="multilingual" in (item["language"] or ""),
            )
            for item in ELEVENLABS_MODEL_FALLBACKS
        ]

    models.sort(key=lambda item: (not item.hindi_recommended, item.name.lower()))
    return models


async def _fetch_elevenlabs_voices() -> list[VoiceCatalogItem]:
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        return [
            _voice_item(
                item["id"],
                item["name"],
                item["language"],
                hindi_recommended="multilingual" in (item["language"] or ""),
            )
            for item in ELEVENLABS_VOICE_FALLBACKS
        ]

    url = "https://api.elevenlabs.io/v1/voices"
    headers = {"xi-api-key": settings.elevenlabs_api_key.get_secret_value()}

    voices: list[VoiceCatalogItem] = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        payload = {}

    raw_voices = payload.get("voices") if isinstance(payload, dict) else None
    if isinstance(raw_voices, list):
        for raw in raw_voices:
            if not isinstance(raw, dict):
                continue
            voice_id = raw.get("voice_id") or raw.get("id")
            if not voice_id:
                continue
            name = str(raw.get("name") or voice_id)
            labels = raw.get("labels")

            language = None
            accent = None
            if isinstance(labels, dict):
                raw_language = labels.get("language")
                raw_accent = labels.get("accent")
                language = raw_language if isinstance(raw_language, str) else None
                accent = raw_accent if isinstance(raw_accent, str) else None

            combined_language = language
            if accent and language:
                combined_language = f"{language} ({accent})"

            voices.append(
                _voice_item(
                    str(voice_id),
                    name,
                    combined_language,
                    hindi_recommended=_is_hindi_like(language, accent, name)
                    or "multilingual" in str(raw.get("category", "")).lower(),
                )
            )

    if not voices:
        voices = [
            _voice_item(
                item["id"],
                item["name"],
                item["language"],
                hindi_recommended="multilingual" in (item["language"] or ""),
            )
            for item in ELEVENLABS_VOICE_FALLBACKS
        ]

    voices.sort(key=lambda item: (not item.hindi_recommended, item.name.lower()))
    return voices


def _discover_piper_voices() -> list[VoiceCatalogItem]:
    settings = get_settings()
    voices: list[VoiceCatalogItem] = []

    model_root = Path("data/models/piper")
    if model_root.exists():
        for model_file in sorted(model_root.glob("*.onnx")):
            voice_id = model_file.stem
            voices.append(
                _voice_item(
                    voice_id,
                    voice_id,
                    "local",
                    hindi_recommended=_is_hindi_like(voice_id),
                )
            )

    configured = settings.piper_voice
    if configured and configured not in {v.id for v in voices}:
        voices.insert(
            0,
            _voice_item(
                configured,
                configured,
                "configured",
                hindi_recommended=_is_hindi_like(configured),
            ),
        )

    if not voices:
        voices.append(_voice_item(configured, configured, "configured", hindi_recommended=True))

    voices.sort(key=lambda item: (not item.hindi_recommended, item.name.lower()))
    return voices


def _edge_voice_items() -> list[VoiceCatalogItem]:
    return [
        _voice_item(
            item["id"],
            item["name"],
            item["language"],
            hindi_recommended=_is_hindi_like(item["language"], item["name"]),
        )
        for item in EDGE_VOICE_OPTIONS
    ]


def _recommended_presets(
    elevenlabs_models: list[VoiceCatalogItem],
    elevenlabs_voices: list[VoiceCatalogItem],
    piper_voices: list[VoiceCatalogItem],
    edge_voices: list[VoiceCatalogItem],
    provider_status: dict[str, bool],
) -> list[VoicePreset]:
    presets: list[VoicePreset] = [
        VoicePreset(
            id="auto_quality",
            name="Auto Quality",
            description="Production default. Tries managed quality first, then local fallback.",
            provider="auto",
        )
    ]

    if provider_status.get("elevenlabs"):
        preferred_model = next(
            (m.id for m in elevenlabs_models if m.hindi_recommended),
            elevenlabs_models[0].id if elevenlabs_models else None,
        )
        preferred_voice = next(
            (v.id for v in elevenlabs_voices if v.hindi_recommended),
            elevenlabs_voices[0].id if elevenlabs_voices else None,
        )
        presets.append(
            VoicePreset(
                id="elevenlabs_hindi",
                name="ElevenLabs Hindi/Multilingual",
                description="Managed voice tuned for natural Hindi/Hinglish output.",
                provider="elevenlabs",
                model_id=preferred_model,
                voice_id=preferred_voice,
            )
        )

    if provider_status.get("piper") and piper_voices:
        presets.append(
            VoicePreset(
                id="piper_local_hindi",
                name="Piper Local Hindi",
                description="CPU-first local Hindi voice for resilient fallback testing.",
                provider="piper",
                piper_voice=piper_voices[0].id,
            )
        )

    if provider_status.get("edge") and edge_voices:
        presets.append(
            VoicePreset(
                id="edge_hindi",
                name="Edge Hindi Neural",
                description="Edge neural Hindi voice path for comparison.",
                provider="edge",
                edge_voice=edge_voices[0].id,
            )
        )

    return presets


# =============================================================================
# Routes
# =============================================================================


@router.get("", response_model=list[BusinessResponse])
async def list_businesses(
    user: RequireAuth,
    session: AsyncSession = Depends(get_session),
) -> list[BusinessResponse]:
    """List businesses visible to the authenticated user.

    Admins can view all businesses. Non-admin users can only view their tenant list.
    """
    query = select(Business).order_by(Business.name)
    if not user.is_admin:
        allowed_ids = user.business_ids or []
        if not allowed_ids:
            return []
        query = query.where(Business.id.in_(allowed_ids))  # type: ignore[attr-defined]

    result = await session.execute(query)
    businesses = result.scalars().all()
    return [business_to_response(b) for b in businesses]


@router.post("", response_model=BusinessResponse, status_code=201)
async def create_business(
    payload: BusinessCreate,
    user: RequireAuth,
    session: AsyncSession = Depends(get_session),
) -> BusinessResponse:
    """Create a new business (admin only)."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can create businesses")

    existing = await session.get(Business, payload.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Business '{payload.id}' already exists")

    operating_hours: dict[str, Any] = {}
    for day, hours in payload.operating_hours.items():
        if isinstance(hours, str):
            operating_hours[day] = hours
        else:
            operating_hours[day] = hours.model_dump()

    business = Business(
        id=payload.id,
        name=payload.name,
        type=payload.type,
        timezone=payload.timezone,
        status=payload.status,
        phone_numbers_json=serialize_json_field(payload.phone_numbers),
        operating_hours_json=serialize_json_field(operating_hours),
        reservation_rules_json=serialize_json_field(payload.reservation_rules.model_dump()),
        greeting_text=payload.greeting_text,
        menu_summary=payload.menu_summary,
        voice_profile_json=serialize_json_field(payload.voice_profile.model_dump()),
        rag_profile_json=serialize_json_field(payload.rag_profile.model_dump()),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(business)

    if payload.phone_numbers:
        await sync_phone_numbers(session, payload.id, payload.phone_numbers)

    await session.commit()
    await session.refresh(business)
    return business_to_response(business)


@router.get("/{business_id}/voice-options", response_model=VoiceOptionsResponse)
async def get_voice_options(
    business_id: str,
    auth_business_id: RequireBusinessAccess,
) -> VoiceOptionsResponse:
    """Return available provider/model/voice options for frontend voice toggles."""
    if business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to access business '{business_id}'",
        )

    settings = get_settings()
    elevenlabs_models = await _fetch_elevenlabs_models()
    elevenlabs_voices = await _fetch_elevenlabs_voices()
    piper_voices = _discover_piper_voices()
    edge_voices = _edge_voice_items()

    provider_status = {
        "auto": True,
        "elevenlabs": bool(settings.elevenlabs_api_key),
        "piper": bool(piper_voices),
        "edge": bool(settings.edge_tts_enabled),
    }

    providers: list[Literal["auto", "elevenlabs", "piper", "edge"]] = [
        "auto",
        "elevenlabs",
        "piper",
    ]
    if provider_status["edge"]:
        providers.append("edge")

    return VoiceOptionsResponse(
        providers=providers,
        provider_status=provider_status,
        elevenlabs_models=elevenlabs_models,
        elevenlabs_voices=elevenlabs_voices,
        piper_voices=piper_voices,
        edge_voices=edge_voices,
        recommended_presets=_recommended_presets(
            elevenlabs_models=elevenlabs_models,
            elevenlabs_voices=elevenlabs_voices,
            piper_voices=piper_voices,
            edge_voices=edge_voices,
            provider_status=provider_status,
        ),
    )


@router.get("/{business_id}", response_model=BusinessResponse)
async def get_business(
    business_id: str,
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
) -> BusinessResponse:
    """Get business settings by ID.

    Requires JWT authentication and X-Business-ID header.
    User must have access to the requested business.
    """
    # Tenant isolation: only allow access to authorized business
    if business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to access business '{business_id}'",
        )

    result = await session.execute(select(Business).where(Business.id == business_id))
    business = result.scalar_one_or_none()

    if not business:
        raise HTTPException(status_code=404, detail=f"Business '{business_id}' not found")

    return business_to_response(business)


@router.patch("/{business_id}", response_model=BusinessResponse)
async def update_business(
    business_id: str,
    update: BusinessUpdate,
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
) -> BusinessResponse:
    """Update business settings.

    Requires JWT authentication and X-Business-ID header.
    User must have access to the requested business.
    """
    # Tenant isolation: only allow access to authorized business
    if business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to modify business '{business_id}'",
        )

    result = await session.execute(select(Business).where(Business.id == business_id))
    business = result.scalar_one_or_none()

    if not business:
        raise HTTPException(status_code=404, detail=f"Business '{business_id}' not found")

    # Apply updates
    if update.name is not None:
        business.name = update.name
    if update.timezone is not None:
        business.timezone = update.timezone
    if update.phone_numbers is not None:
        business.phone_numbers_json = serialize_json_field(update.phone_numbers)
        # Sync to lookup table for call routing
        await sync_phone_numbers(session, business_id, update.phone_numbers)
    if update.operating_hours is not None:
        # Convert OperatingHours to dict
        hours_dict: dict[str, Any] = {}
        for day, hours in update.operating_hours.items():
            if isinstance(hours, str):
                hours_dict[day] = hours
            else:
                hours_dict[day] = hours.model_dump()
        business.operating_hours_json = serialize_json_field(hours_dict)
    if update.reservation_rules is not None:
        business.reservation_rules_json = serialize_json_field(
            update.reservation_rules.model_dump()
        )
    if update.greeting_text is not None:
        business.greeting_text = update.greeting_text
    if update.menu_summary is not None:
        business.menu_summary = update.menu_summary
    if update.voice_profile is not None:
        business.voice_profile_json = serialize_json_field(
            update.voice_profile.model_dump()
        )
    if update.rag_profile is not None:
        business.rag_profile_json = serialize_json_field(update.rag_profile.model_dump())

    # Always update timestamp on modification
    business.updated_at = datetime.now(UTC)

    session.add(business)
    await session.commit()
    await session.refresh(business)

    return business_to_response(business)
