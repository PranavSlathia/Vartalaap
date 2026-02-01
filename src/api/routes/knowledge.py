"""CRUD endpoints for knowledge items (menu items, FAQs, policies, announcements).

Used by the admin frontend to manage the knowledge base for RAG retrieval.
Security: All endpoints require JWT authentication and tenant authorization.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import RequireBusinessAccess
from src.db.models import KnowledgeCategory, KnowledgeItem
from src.db.session import get_session
from src.logging_config import get_logger
from src.services.knowledge.chromadb_store import get_chromadb_store
from src.services.knowledge.protocol import KnowledgeQuery
from src.services.knowledge.retriever import KnowledgeRetriever

logger: Any = get_logger(__name__)

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
    """Search result with similarity score.

    When using vector search, score is a real similarity value (0.0-1.0).
    When falling back to keyword search, score is None.
    """

    item: KnowledgeItemResponse
    score: float | None = Field(
        None, description="Similarity score (0.0-1.0) or null for keyword-only matches"
    )


# =============================================================================
# CRUD Endpoints
# =============================================================================


@router.get("", response_model=list[KnowledgeItemResponse])
async def list_knowledge_items(
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
    business_id: str = Query(..., description="Required for tenant isolation"),
    category: KnowledgeCategory | None = Query(None),
    is_active: bool | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> list[KnowledgeItemResponse]:
    """List knowledge items with optional filters.

    Security: Requires JWT authentication. business_id must match authorized tenant.
    """
    # Verify tenant access matches requested business
    if business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to access business '{business_id}'",
        )

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
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeItemResponse:
    """Get a knowledge item by ID.

    Security: Requires JWT authentication. Item must belong to authorized tenant.
    """
    result = await session.execute(
        select(KnowledgeItem).where(KnowledgeItem.id == item_id)  # type: ignore[arg-type]
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    # Verify tenant access
    if item.business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this knowledge item",
        )

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
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeItemResponse:
    """Create a new knowledge item.

    Security: Requires JWT authentication. Can only create items for authorized tenant.
    """
    # Verify tenant access matches requested business
    if data.business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to create items for business '{data.business_id}'",
        )

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
    await session.commit()  # Commit DB first to ensure consistency
    await session.refresh(item)

    # Sync to ChromaDB after successful DB commit (prevents orphaned embeddings)
    if item.is_active:
        store = None
        try:
            store = get_chromadb_store()
            await store.add_item_async(data.business_id, item)
            item.embedding_id = item.id
            await session.commit()
        except Exception as e:
            logger.warning(f"Failed to index item {item.id} in ChromaDB: {e}")
            # If embedding was created but commit failed, clean up the orphan
            if store and item.embedding_id:
                try:
                    await store.remove_item_async(data.business_id, item.id)
                except Exception:
                    pass  # Best effort cleanup
            item.embedding_id = None  # Reset since not persisted
            # Don't fail the request - DB is source of truth, ChromaDB can be resynced

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
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
) -> KnowledgeItemResponse:
    """Update a knowledge item (partial update).

    Security: Requires JWT authentication. Item must belong to authorized tenant.
    """
    result = await session.execute(
        select(KnowledgeItem).where(KnowledgeItem.id == item_id)  # type: ignore[arg-type]
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    # Verify tenant access
    if item.business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to update this knowledge item",
        )

    # Track if content or active status changed for ChromaDB sync
    update_data = data.model_dump(exclude_unset=True)
    content_fields = {"title", "content", "title_hindi", "content_hindi"}
    content_changed = any(k in update_data for k in content_fields)
    active_changed = "is_active" in update_data
    was_active = item.is_active

    # Apply updates only for provided fields
    for field, value in update_data.items():
        setattr(item, field, value)

    item.updated_at = datetime.now(UTC)
    await session.commit()  # Commit DB first to ensure consistency
    await session.refresh(item)

    # Sync to ChromaDB after successful DB commit (prevents orphaned embeddings)
    store = None
    embedding_added = False
    try:
        store = get_chromadb_store()

        if item.is_active and content_changed:
            # Reindex with new content
            await store.add_item_async(item.business_id, item)
            embedding_added = True
            item.embedding_id = item.id
            await session.commit()
        elif active_changed:
            if item.is_active and not was_active:
                # Activated - add to index
                await store.add_item_async(item.business_id, item)
                embedding_added = True
                item.embedding_id = item.id
                await session.commit()
            elif not item.is_active and was_active:
                # Deactivated - remove from index
                await store.remove_item_async(item.business_id, item.id)
                item.embedding_id = None
                await session.commit()
    except Exception as e:
        logger.warning(f"Failed to sync item {item.id} to ChromaDB: {e}")
        # If embedding was added but commit failed, clean up the orphan
        if store and embedding_added:
            try:
                await store.remove_item_async(item.business_id, item.id)
            except Exception:
                pass  # Best effort cleanup
            item.embedding_id = None
        # Don't fail the request - DB is source of truth, ChromaDB can be resynced

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
    auth_business_id: RequireBusinessAccess,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a knowledge item.

    Security: Requires JWT authentication. Item must belong to authorized tenant.
    """
    result = await session.execute(
        select(KnowledgeItem).where(KnowledgeItem.id == item_id)  # type: ignore[arg-type]
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Knowledge item not found")

    # Verify tenant access
    if item.business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to delete this knowledge item",
        )

    # Remove from ChromaDB before deleting from DB
    if item.embedding_id:
        try:
            store = get_chromadb_store()
            await store.remove_item_async(item.business_id, item.id)
        except Exception as e:
            logger.warning(f"Failed to remove item {item.id} from ChromaDB: {e}")
            # Continue with DB deletion - ChromaDB can be cleaned up later

    await session.delete(item)


# =============================================================================
# Search Endpoint (vector search with ChromaDB)
# =============================================================================


@router.post("/search", response_model=list[KnowledgeSearchResult])
async def search_knowledge_items(
    auth_business_id: RequireBusinessAccess,
    query: str = Query(..., min_length=1, max_length=500),
    business_id: str = Query(...),
    category: KnowledgeCategory | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
) -> list[KnowledgeSearchResult]:
    """Search knowledge items using vector similarity.

    Uses ChromaDB + sentence-transformers for semantic search.
    Falls back to keyword search if vector store is unavailable.

    Security: Requires JWT authentication. business_id must match authorized tenant.
    """
    # Verify tenant access matches requested business
    if business_id != auth_business_id:
        raise HTTPException(
            status_code=403,
            detail=f"Not authorized to search business '{business_id}'",
        )

    # Try vector search first
    try:
        retriever = KnowledgeRetriever(session)

        # Check if ChromaDB is operational
        if not await retriever.health_check():
            logger.warning("ChromaDB unavailable, falling back to keyword search")
            return await _fallback_keyword_search(session, business_id, query, category, limit)

        # Perform vector search
        knowledge_query = KnowledgeQuery(
            business_id=business_id,
            query_text=query,
            max_results=limit,
            categories=[category] if category else None,
            min_score=0.3,  # Filter low relevance
        )
        result = await retriever.search(knowledge_query)

        if not result.items:
            return []

        # Fetch full records from DB to get created_at, updated_at, metadata_json
        item_ids = [item.id for item in result.items]
        stmt = select(KnowledgeItem).where(KnowledgeItem.id.in_(item_ids))  # type: ignore[arg-type]
        db_result = await session.execute(stmt)
        db_items = {item.id: item for item in db_result.scalars().all()}

        # Build scores map from vector search results
        scores_map = {item.id: item.score for item in result.items}

        # Convert to response format with full DB records and vector scores
        return [
            KnowledgeSearchResult(
                item=KnowledgeItemResponse(
                    id=db_item.id,
                    business_id=db_item.business_id,
                    category=db_item.category,
                    title=db_item.title,
                    title_hindi=db_item.title_hindi,
                    content=db_item.content,
                    content_hindi=db_item.content_hindi,
                    metadata_json=db_item.metadata_json,
                    is_active=db_item.is_active,
                    priority=db_item.priority,
                    embedding_id=db_item.embedding_id,
                    created_at=db_item.created_at.isoformat(),
                    updated_at=db_item.updated_at.isoformat(),
                ),
                score=scores_map.get(db_item.id, 0.0),
            )
            for db_item in (db_items.get(item.id) for item in result.items)
            if db_item is not None
        ]

    except Exception as e:
        logger.warning(f"Vector search failed, falling back to keyword search: {e}")
        return await _fallback_keyword_search(session, business_id, query, category, limit)


async def _fallback_keyword_search(
    session: AsyncSession,
    business_id: str,
    query: str,
    category: KnowledgeCategory | None,
    limit: int,
) -> list[KnowledgeSearchResult]:
    """Fallback to SQL LIKE search when vector store is unavailable.

    Returns results without similarity scores (score=None) to indicate
    this is keyword-only matching, not semantic search.
    """
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

    # Return with score=None to indicate keyword-only match
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
            score=None,  # No fake scores - indicates keyword-only match
        )
        for item in items
    ]
