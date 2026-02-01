"""Knowledge retriever service combining database and vector search."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import KnowledgeCategory, KnowledgeItem
from src.db.repositories.businesses import AsyncKnowledgeItemRepository
from src.logging_config import get_logger
from src.observability.metrics import record_rag_metrics
from src.services.knowledge.chromadb_store import ChromaDBStore, get_chromadb_store
from src.services.knowledge.embeddings import normalize_query
from src.services.knowledge.protocol import (
    KnowledgeQuery,
    KnowledgeResult,
    RetrievedKnowledge,
    parse_metadata,
)

logger: Any = get_logger(__name__)


class KnowledgeRetriever:
    """Main knowledge retrieval service.

    Combines ChromaDB vector search with database lookups
    for comprehensive knowledge retrieval during voice calls.
    """

    def __init__(
        self,
        session: AsyncSession,
        chromadb_store: ChromaDBStore | None = None,
    ):
        self._session = session
        self._chromadb = chromadb_store or get_chromadb_store()
        self._repo = AsyncKnowledgeItemRepository(session)

    async def search(self, query: KnowledgeQuery) -> KnowledgeResult:
        """Search for relevant knowledge items.

        Uses vector similarity search to find the most relevant items
        for the user's query, then enriches with full database records.

        Args:
            query: The knowledge query with business_id, query_text, etc.

        Returns:
            KnowledgeResult with retrieved items and timing info
        """
        start_time = time.perf_counter()

        # Normalize query text for better matching
        normalized_query = normalize_query(query.query_text)

        # Vector search in ChromaDB
        search_results = await self._chromadb.search_async(
            business_id=query.business_id,
            query_text=normalized_query,
            max_results=query.max_results,
            categories=query.categories,
        )

        # Filter by minimum score and enrich with database records
        items: list[RetrievedKnowledge] = []
        for result in search_results:
            if result["score"] < query.min_score:
                continue

            # Get full record from database
            db_item = await self._repo.get_by_id(result["id"])
            if not db_item or not db_item.is_active:
                continue

            # Parse and validate metadata using category-specific schema
            metadata = parse_metadata(db_item.metadata_json, db_item.category)

            items.append(
                RetrievedKnowledge(
                    id=db_item.id,
                    category=db_item.category,
                    title=db_item.title,
                    title_hindi=db_item.title_hindi,
                    content=db_item.content,
                    content_hindi=db_item.content_hindi,
                    metadata=metadata,
                    priority=db_item.priority,
                    score=result["score"],
                )
            )

        # Sort by combined score (similarity + priority boost)
        items.sort(
            key=lambda x: x.score + (x.priority / 100 * 0.2),  # Priority adds up to 20%
            reverse=True,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(
            f"Knowledge retrieval: {len(items)} items in {elapsed_ms:.1f}ms "
            f"for query '{query.query_text[:50]}...'"
        )

        # Record Prometheus metrics
        top_score = items[0].score if items else None
        record_rag_metrics(
            business_id=query.business_id,
            retrieval_time_ms=elapsed_ms,
            top_score=top_score,
            result_count=len(items),
        )

        return KnowledgeResult(
            query=query,
            items=items,
            retrieval_time_ms=elapsed_ms,
        )

    async def index_item(
        self,
        business_id: str,
        item_id: str,
        title: str,
        content: str,
        title_hindi: str | None = None,
        content_hindi: str | None = None,
    ) -> str:
        """Index a knowledge item for retrieval.

        Called when a new item is created or updated.
        """
        # Create a temporary KnowledgeItem for indexing
        item = KnowledgeItem(
            id=item_id,
            business_id=business_id,
            category=KnowledgeCategory.faq,  # Default, actual category in DB
            title=title,
            title_hindi=title_hindi,
            content=content,
            content_hindi=content_hindi,
        )

        return await self._chromadb.add_item_async(business_id, item)

    async def index_db_item(self, item: KnowledgeItem) -> str:
        """Index a database KnowledgeItem directly."""
        return await self._chromadb.add_item_async(item.business_id, item)

    async def remove_item(self, business_id: str, embedding_id: str) -> bool:
        """Remove a knowledge item from the index."""
        return await self._chromadb.remove_item_async(business_id, embedding_id)

    async def reindex_business(self, business_id: str) -> int:
        """Reindex all items for a business.

        Useful when the embedding model changes or to fix inconsistencies.
        """
        # Get all active items from database
        items = await self._repo.get_items_for_embedding(business_id)

        if not items:
            logger.info(f"No items to index for {business_id}")
            return 0

        # Clear existing collection and reindex
        self._chromadb.delete_collection(business_id)

        indexed = 0
        for item in items:
            try:
                await self._chromadb.add_item_async(business_id, item)
                indexed += 1
            except Exception as e:
                logger.error(f"Failed to index item {item.id}: {e}")

        logger.info(f"Reindexed {indexed}/{len(items)} items for {business_id}")
        return indexed

    async def health_check(self) -> bool:
        """Check if the service is operational."""
        return self._chromadb.health_check()


async def search_knowledge(
    session: AsyncSession,
    business_id: str,
    query_text: str,
    *,
    max_results: int = 5,
    categories: list[KnowledgeCategory] | None = None,
    min_score: float = 0.3,
) -> KnowledgeResult:
    """Convenience function for knowledge search.

    Creates a retriever instance and performs the search.
    Useful for one-off searches in the voice pipeline.
    """
    retriever = KnowledgeRetriever(session)
    query = KnowledgeQuery(
        business_id=business_id,
        query_text=query_text,
        max_results=max_results,
        categories=categories,
        min_score=min_score,
    )
    return await retriever.search(query)
