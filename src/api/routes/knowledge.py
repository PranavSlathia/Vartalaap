"""CRUD endpoints for knowledge items (menu items, FAQs, policies, announcements).

Used by the admin frontend to manage the knowledge base for RAG retrieval.
"""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import KnowledgeCategory, KnowledgeItem
from src.db.session import get_session

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


# =============================================================================
# Request/Response Schemas
# =============================================================================


class KnowledgeItemCreate(BaseModel):
    """Schema for creating a knowledge item."""

    business_id: str
    category: KnowledgeCategory
    title: str = Field(max_length=200)
    title_hindi: str | None = Field(None, max_length=200)
    content: str = Field(max_length=2000)
    content_hindi: str | None = Field(None, max_length=2000)
    metadata_json: str | None = None
    is_active: bool = True
    priority: int = Field(50, ge=0, le=100)


class KnowledgeItemUpdate(BaseModel):
    """Schema for updating a knowledge item (all fields optional)."""

    category: KnowledgeCategory | None = None
    title: str | None = Field(None, max_length=200)
    title_hindi: str | None = Field(None, max_length=200)
    content: str | None = Field(None, max_length=2000)
    content_hindi: str | None = Field(None, max_length=2000)
    metadata_json: str | None = None
    is_active: bool | None = None
    priority: int | None = Field(None, ge=0, le=100)


class KnowledgeItemResponse(BaseModel):
    """Response schema for knowledge items."""

    id: str
    business_id: str
    category: KnowledgeCategory
    title: str
    title_hindi: str | None
    content: str
    content_hindi: str | None
    metadata_json: str | None
    is_active: bool
    priority: int
    embedding_id: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class KnowledgeSearchResult(BaseModel):
    """Search result with similarity score."""

    item: KnowledgeItemResponse
    score: float


# =============================================================================
# CRUD Endpoints
# =============================================================================


@router.get("", response_model=list[KnowledgeItemResponse])
async def list_knowledge_items(
    session: AsyncSession = Depends(get_session),
    business_id: str = Query(..., description="Required for tenant isolation"),
    category: KnowledgeCategory | None = Query(None),
    is_active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> list[KnowledgeItemResponse]:
    """List knowledge items with optional filters.

    Security: business_id is required to prevent cross-tenant data access.
    """
    query = select(KnowledgeItem)

    # Required: always scope by business_id
    query = query.where(KnowledgeItem.business_id == business_id)  # type: ignore[arg-type]
    if category:
        query = query.where(KnowledgeItem.category == category)  # type: ignore[arg-type]
    if is_active is not None:
        query = query.where(KnowledgeItem.is_active == is_active)  # type: ignore[arg-type]

    query = query.offset(skip).limit(limit).order_by(desc(KnowledgeItem.priority))

    result = await session.execute(query)
    items = result.scalars().all()

    return [
        KnowledgeItemResponse(
            id=item.id,
            business_id=item.business_id,
            category=item.category,
            title=item.title,
            title_hindi=item.title_hindi,
            content=item.content,
            content_hindi=item.content_hindi,
            metadata_json=item.metadata_json,
            is_active=item.is_active,
            priority=item.priority,
            embedding_id=item.embedding_id,
            created_at=item.created_at.isoformat(),
            updated_at=item.updated_at.isoformat(),
        )
        for item in items
    ]


@router.get("/{item_id}", response_model=KnowledgeItemResponse)
async def get_knowledge_item(
    item_id: str,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeItemResponse:
    """Get a knowledge item by ID."""
    result = await session.execute(
        select(KnowledgeItem).where(KnowledgeItem.id == item_id)  # type: ignore[arg-type]
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    return KnowledgeItemResponse(
        id=item.id,
        business_id=item.business_id,
        category=item.category,
        title=item.title,
        title_hindi=item.title_hindi,
        content=item.content,
        content_hindi=item.content_hindi,
        metadata_json=item.metadata_json,
        is_active=item.is_active,
        priority=item.priority,
        embedding_id=item.embedding_id,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


@router.post("", response_model=KnowledgeItemResponse, status_code=201)
async def create_knowledge_item(
    data: KnowledgeItemCreate,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeItemResponse:
    """Create a new knowledge item."""
    now = datetime.now(UTC)
    item = KnowledgeItem(
        id=str(uuid4()),
        business_id=data.business_id,
        category=data.category,
        title=data.title,
        title_hindi=data.title_hindi,
        content=data.content,
        content_hindi=data.content_hindi,
        metadata_json=data.metadata_json,
        is_active=data.is_active,
        priority=data.priority,
        created_at=now,
        updated_at=now,
    )

    session.add(item)
    await session.flush()
    await session.refresh(item)

    return KnowledgeItemResponse(
        id=item.id,
        business_id=item.business_id,
        category=item.category,
        title=item.title,
        title_hindi=item.title_hindi,
        content=item.content,
        content_hindi=item.content_hindi,
        metadata_json=item.metadata_json,
        is_active=item.is_active,
        priority=item.priority,
        embedding_id=item.embedding_id,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


@router.patch("/{item_id}", response_model=KnowledgeItemResponse)
async def update_knowledge_item(
    item_id: str,
    data: KnowledgeItemUpdate,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeItemResponse:
    """Update a knowledge item (partial update)."""
    result = await session.execute(
        select(KnowledgeItem).where(KnowledgeItem.id == item_id)  # type: ignore[arg-type]
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    # Apply updates only for provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)

    item.updated_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(item)

    return KnowledgeItemResponse(
        id=item.id,
        business_id=item.business_id,
        category=item.category,
        title=item.title,
        title_hindi=item.title_hindi,
        content=item.content,
        content_hindi=item.content_hindi,
        metadata_json=item.metadata_json,
        is_active=item.is_active,
        priority=item.priority,
        embedding_id=item.embedding_id,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


@router.delete("/{item_id}", status_code=204)
async def delete_knowledge_item(
    item_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a knowledge item."""
    result = await session.execute(
        select(KnowledgeItem).where(KnowledgeItem.id == item_id)  # type: ignore[arg-type]
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    await session.delete(item)


# =============================================================================
# Search Endpoint (placeholder for vector search)
# =============================================================================


@router.post("/search", response_model=list[KnowledgeSearchResult])
async def search_knowledge(
    query: str = Query(..., min_length=1, max_length=500),
    business_id: str = Query(...),
    category: KnowledgeCategory | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
) -> list[KnowledgeSearchResult]:
    """Search knowledge items using text matching.

    TODO: Integrate with ChromaDB for vector similarity search.
    Current implementation uses simple text matching.
    """
    # Simple text search (will be replaced with vector search)
    stmt = select(KnowledgeItem).where(
        KnowledgeItem.business_id == business_id,  # type: ignore[arg-type]
        KnowledgeItem.is_active == True,  # noqa: E712
    )

    if category:
        stmt = stmt.where(KnowledgeItem.category == category)  # type: ignore[arg-type]

    # Simple LIKE search on title and content
    stmt = stmt.where(
        (KnowledgeItem.title.ilike(f"%{query}%"))  # type: ignore[union-attr]
        | (KnowledgeItem.content.ilike(f"%{query}%"))  # type: ignore[union-attr]
        | (KnowledgeItem.title_hindi.ilike(f"%{query}%"))  # type: ignore[union-attr]
    )

    stmt = stmt.order_by(desc(KnowledgeItem.priority)).limit(limit)

    result = await session.execute(stmt)
    items = result.scalars().all()

    # Return with placeholder scores (will be real similarity scores with vector search)
    return [
        KnowledgeSearchResult(
            item=KnowledgeItemResponse(
                id=item.id,
                business_id=item.business_id,
                category=item.category,
                title=item.title,
                title_hindi=item.title_hindi,
                content=item.content,
                content_hindi=item.content_hindi,
                metadata_json=item.metadata_json,
                is_active=item.is_active,
                priority=item.priority,
                embedding_id=item.embedding_id,
                created_at=item.created_at.isoformat(),
                updated_at=item.updated_at.isoformat(),
            ),
            score=0.7 + (item.priority / 500),  # Placeholder score based on priority
        )
        for item in items
    ]
