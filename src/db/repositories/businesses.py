"""Business repository for multi-tenant support."""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session

from src.db.models import (
    Business,
    BusinessPhoneNumber,
    BusinessStatus,
    KnowledgeCategory,
    KnowledgeItem,
)


class BusinessRepository:
    """Sync repository for admin UI."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, business_id: str) -> Business | None:
        return self.session.get(Business, business_id)

    def get_by_phone_number(self, phone_number: str) -> Business | None:
        """Look up business by incoming phone number."""
        query = select(BusinessPhoneNumber).where(
            BusinessPhoneNumber.phone_number == phone_number  # type: ignore[arg-type]
        )
        result = self.session.execute(query)
        mapping = result.scalar_one_or_none()
        if mapping:
            return self.get_by_id(mapping.business_id)
        return None

    def list_active(self) -> list[Business]:
        """List all active businesses."""
        query = select(Business).where(Business.status == BusinessStatus.active)  # type: ignore[arg-type]
        result = self.session.execute(query)
        return list(result.scalars().all())

    def list_all(self) -> list[Business]:
        """List all businesses."""
        query = select(Business).order_by(Business.name)
        result = self.session.execute(query)
        return list(result.scalars().all())

    def create(self, **fields) -> Business:
        """Create a new business."""
        business = Business(**fields)
        self.session.add(business)
        return business

    def update(self, business_id: str, **fields) -> Business | None:
        """Update a business."""
        business = self.get_by_id(business_id)
        if not business:
            return None
        for key, value in fields.items():
            setattr(business, key, value)
        business.updated_at = datetime.now(UTC)
        self.session.add(business)
        return business

    def get_config_dict(self, business_id: str) -> dict | None:
        """Get business config as dict (backward compat with YAML)."""
        business = self.get_by_id(business_id)
        if not business:
            return None
        return _business_to_config_dict(business)

    def add_phone_number(
        self, business_id: str, phone_number: str, is_primary: bool = False
    ) -> BusinessPhoneNumber:
        """Add a phone number mapping."""
        mapping = BusinessPhoneNumber(
            phone_number=phone_number,
            business_id=business_id,
            is_primary=is_primary,
        )
        self.session.add(mapping)
        return mapping

    def get_phone_numbers(self, business_id: str) -> list[BusinessPhoneNumber]:
        """Get all phone numbers for a business."""
        query = select(BusinessPhoneNumber).where(
            BusinessPhoneNumber.business_id == business_id  # type: ignore[arg-type]
        )
        result = self.session.execute(query)
        return list(result.scalars().all())

    def remove_phone_number(self, phone_number: str) -> bool:
        """Remove a phone number mapping."""
        mapping = self.session.get(BusinessPhoneNumber, phone_number)
        if mapping:
            self.session.delete(mapping)
            return True
        return False


class AsyncBusinessRepository:
    """Async repository for workers and API."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, business_id: str) -> Business | None:
        return await self.session.get(Business, business_id)

    async def get_by_phone_number(self, phone_number: str) -> Business | None:
        """Look up business by incoming phone number.

        This is called during call routing to resolve which business
        should handle the call based on the "To" phone number.
        """
        query = select(BusinessPhoneNumber).where(
            BusinessPhoneNumber.phone_number == phone_number  # type: ignore[arg-type]
        )
        result = await self.session.execute(query)
        mapping = result.scalar_one_or_none()
        if mapping:
            return await self.get_by_id(mapping.business_id)
        return None

    async def get_config_dict(self, business_id: str) -> dict | None:
        """Get business config as dict (backward compat with YAML)."""
        business = await self.get_by_id(business_id)
        if not business:
            return None
        return _business_to_config_dict(business)

    async def list_active(self) -> list[Business]:
        """List all active businesses."""
        query = select(Business).where(Business.status == BusinessStatus.active)  # type: ignore[arg-type]
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, **fields) -> Business:
        """Create a new business."""
        business = Business(**fields)
        self.session.add(business)
        return business

    async def update(self, business_id: str, **fields) -> Business | None:
        """Update a business."""
        business = await self.get_by_id(business_id)
        if not business:
            return None
        for key, value in fields.items():
            setattr(business, key, value)
        business.updated_at = datetime.now(UTC)
        self.session.add(business)
        return business

    async def add_phone_number(
        self, business_id: str, phone_number: str, is_primary: bool = False
    ) -> BusinessPhoneNumber:
        """Add a phone number mapping."""
        mapping = BusinessPhoneNumber(
            phone_number=phone_number,
            business_id=business_id,
            is_primary=is_primary,
        )
        self.session.add(mapping)
        return mapping

    async def get_phone_numbers(self, business_id: str) -> list[BusinessPhoneNumber]:
        """Get all phone numbers for a business."""
        query = select(BusinessPhoneNumber).where(
            BusinessPhoneNumber.business_id == business_id  # type: ignore[arg-type]
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())


def _business_to_config_dict(business: Business) -> dict:
    """Convert Business model to config dict format (YAML compat)."""
    # Parse JSON fields
    operating_hours = {}
    if business.operating_hours_json:
        with contextlib.suppress(json.JSONDecodeError):
            operating_hours = json.loads(business.operating_hours_json)

    reservation_rules = {}
    if business.reservation_rules_json:
        with contextlib.suppress(json.JSONDecodeError):
            reservation_rules = json.loads(business.reservation_rules_json)

    voice_profile = {}
    if business.voice_profile_json:
        with contextlib.suppress(json.JSONDecodeError):
            voice_profile = json.loads(business.voice_profile_json)

    rag_profile = {}
    if business.rag_profile_json:
        with contextlib.suppress(json.JSONDecodeError):
            rag_profile = json.loads(business.rag_profile_json)

    return {
        "business": {
            "name": business.name,
            "type": business.type.value,
            "timezone": business.timezone,
            "operating_hours": operating_hours,
        },
        "reservation_rules": reservation_rules,
        "greeting_text": business.greeting_text,
        "menu_summary": business.menu_summary,
        "voice_profile": voice_profile,
        "rag_profile": rag_profile,
    }


class KnowledgeItemRepository:
    """Sync repository for knowledge items (admin UI)."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, item_id: str) -> KnowledgeItem | None:
        return self.session.get(KnowledgeItem, item_id)

    def list_by_business(
        self,
        business_id: str,
        *,
        category: KnowledgeCategory | None = None,
        active_only: bool = True,
    ) -> list[KnowledgeItem]:
        """List knowledge items for a business."""
        query = select(KnowledgeItem).where(KnowledgeItem.business_id == business_id)  # type: ignore[arg-type]
        if category:
            query = query.where(KnowledgeItem.category == category)  # type: ignore[arg-type]
        if active_only:
            query = query.where(KnowledgeItem.is_active == True)  # type: ignore[arg-type]  # noqa: E712
        query = query.order_by(
            KnowledgeItem.category,
            KnowledgeItem.priority.desc(),  # type: ignore[attr-defined]
            KnowledgeItem.title,
        )
        result = self.session.execute(query)
        return list(result.scalars().all())

    def create(self, **fields) -> KnowledgeItem:
        """Create a new knowledge item."""
        item = KnowledgeItem(**fields)
        self.session.add(item)
        return item

    def update(self, item_id: str, **fields) -> KnowledgeItem | None:
        """Update a knowledge item."""
        item = self.get_by_id(item_id)
        if not item:
            return None
        for key, value in fields.items():
            setattr(item, key, value)
        item.updated_at = datetime.now(UTC)
        self.session.add(item)
        return item

    def delete(self, item_id: str) -> bool:
        """Delete a knowledge item."""
        item = self.get_by_id(item_id)
        if item:
            self.session.delete(item)
            return True
        return False

    def bulk_create(self, items: list[dict]) -> list[KnowledgeItem]:
        """Bulk create knowledge items."""
        created = []
        for item_data in items:
            item = KnowledgeItem(**item_data)
            self.session.add(item)
            created.append(item)
        return created


class AsyncKnowledgeItemRepository:
    """Async repository for knowledge items (API/workers)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, item_id: str) -> KnowledgeItem | None:
        return await self.session.get(KnowledgeItem, item_id)

    async def list_by_business(
        self,
        business_id: str,
        *,
        category: KnowledgeCategory | None = None,
        active_only: bool = True,
    ) -> list[KnowledgeItem]:
        """List knowledge items for a business."""
        query = select(KnowledgeItem).where(KnowledgeItem.business_id == business_id)  # type: ignore[arg-type]
        if category:
            query = query.where(KnowledgeItem.category == category)  # type: ignore[arg-type]
        if active_only:
            query = query.where(KnowledgeItem.is_active == True)  # type: ignore[arg-type]  # noqa: E712
        query = query.order_by(
            KnowledgeItem.category,
            KnowledgeItem.priority.desc(),  # type: ignore[attr-defined]
            KnowledgeItem.title,
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, **fields) -> KnowledgeItem:
        """Create a new knowledge item."""
        item = KnowledgeItem(**fields)
        self.session.add(item)
        return item

    async def update(self, item_id: str, **fields) -> KnowledgeItem | None:
        """Update a knowledge item."""
        item = await self.get_by_id(item_id)
        if not item:
            return None
        for key, value in fields.items():
            setattr(item, key, value)
        item.updated_at = datetime.now(UTC)
        self.session.add(item)
        return item

    async def get_items_for_embedding(
        self, business_id: str
    ) -> list[KnowledgeItem]:
        """Get all active items that need embeddings generated."""
        query = (
            select(KnowledgeItem)
            .where(KnowledgeItem.business_id == business_id)  # type: ignore[arg-type]
            .where(KnowledgeItem.is_active == True)  # type: ignore[arg-type]  # noqa: E712
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
