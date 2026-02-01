"""ChromaDB vector store for knowledge retrieval.

Uses per-business collections for tenant isolation.
Stores embeddings and metadata for similarity search.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.db.models import KnowledgeCategory, KnowledgeItem
from src.logging_config import get_logger
from src.services.knowledge.embeddings import (
    create_search_text,
    get_embedding_service,
)

logger: Any = get_logger(__name__)


class ChromaDBStore:
    """ChromaDB vector store for knowledge items."""

    def __init__(self, persist_directory: str | None = None):
        self._client = None
        self._persist_directory = persist_directory or self._get_default_persist_dir()
        self._collections: dict[str, Any] = {}

    def _get_default_persist_dir(self) -> str:
        """Get default persist directory from settings or use default."""
        settings = get_settings()
        # Use data directory alongside SQLite database
        db_url = settings.database_url
        if "sqlite" in db_url:
            db_path = db_url.split("///")[-1]
            data_dir = Path(db_path).parent
        else:
            data_dir = Path("data")
        persist_dir = data_dir / "chromadb"
        persist_dir.mkdir(parents=True, exist_ok=True)
        return str(persist_dir)

    @property
    def client(self):
        """Lazy initialization of ChromaDB client."""
        if self._client is None:
            try:
                import chromadb
                from chromadb.config import Settings

                self._client = chromadb.Client(
                    Settings(
                        persist_directory=self._persist_directory,
                        anonymized_telemetry=False,
                        is_persistent=True,
                    )
                )
                logger.info(f"ChromaDB initialized at {self._persist_directory}")
            except ImportError:
                logger.error(
                    "chromadb not installed. Install with: pip install chromadb"
                )
                raise
        return self._client

    def _get_collection_name(self, business_id: str) -> str:
        """Get collection name for a business."""
        # ChromaDB collection names must be valid
        return f"kb_{business_id.replace('-', '_')}"

    def get_collection(self, business_id: str):
        """Get or create a collection for a business."""
        collection_name = self._get_collection_name(business_id)
        if collection_name not in self._collections:
            self._collections[collection_name] = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"business_id": business_id},
            )
        return self._collections[collection_name]

    def add_item(
        self,
        business_id: str,
        item: KnowledgeItem,
    ) -> str:
        """Add a knowledge item to the vector store.

        Returns the embedding_id (same as item.id for simplicity).
        """
        collection = self.get_collection(business_id)
        embedding_service = get_embedding_service()

        # Create combined text for embedding
        search_text = create_search_text(
            title=item.title,
            content=item.content,
            title_hindi=item.title_hindi,
            content_hindi=item.content_hindi,
        )

        # Generate embedding
        embedding = embedding_service.encode_single(search_text)

        # Parse metadata
        metadata_dict = {}
        if item.metadata_json:
            try:
                metadata_dict = json.loads(item.metadata_json)
            except json.JSONDecodeError:
                pass

        # Store in ChromaDB
        collection.upsert(
            ids=[item.id],
            embeddings=[embedding],
            documents=[search_text],
            metadatas=[
                {
                    "category": item.category.value,
                    "title": item.title,
                    "title_hindi": item.title_hindi or "",
                    "priority": item.priority,
                    **{k: str(v) for k, v in metadata_dict.items()},  # Flatten metadata
                }
            ],
        )

        logger.debug(f"Indexed knowledge item {item.id} for {business_id}")
        return item.id

    async def add_item_async(
        self,
        business_id: str,
        item: KnowledgeItem,
    ) -> str:
        """Add a knowledge item asynchronously."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.add_item,
            business_id,
            item,
        )

    def remove_item(self, business_id: str, item_id: str) -> bool:
        """Remove a knowledge item from the vector store."""
        try:
            collection = self.get_collection(business_id)
            collection.delete(ids=[item_id])
            logger.debug(f"Removed knowledge item {item_id} from {business_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove item {item_id}: {e}")
            return False

    async def remove_item_async(self, business_id: str, item_id: str) -> bool:
        """Remove a knowledge item asynchronously."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.remove_item,
            business_id,
            item_id,
        )

    def search(
        self,
        business_id: str,
        query_text: str,
        *,
        max_results: int = 5,
        categories: list[KnowledgeCategory] | None = None,
    ) -> list[dict]:
        """Search for similar knowledge items.

        Returns list of dicts with id, score, and metadata.
        """
        collection = self.get_collection(business_id)
        embedding_service = get_embedding_service()

        # Generate query embedding
        query_embedding = embedding_service.encode_single(query_text)

        # Build where filter for categories if specified
        where_filter = None
        if categories:
            where_filter = {
                "category": {"$in": [c.value for c in categories]}
            }

        # Search
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=max_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        # Convert to list of dicts
        items = []
        if results["ids"] and results["ids"][0]:
            for i, item_id in enumerate(results["ids"][0]):
                # ChromaDB returns L2 distance, convert to similarity score
                # Lower distance = higher similarity
                distance = results["distances"][0][i] if results["distances"] else 0
                score = 1 / (1 + distance)  # Convert to 0-1 range

                items.append({
                    "id": item_id,
                    "score": score,
                    "document": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                })

        return items

    async def search_async(
        self,
        business_id: str,
        query_text: str,
        *,
        max_results: int = 5,
        categories: list[KnowledgeCategory] | None = None,
    ) -> list[dict]:
        """Search asynchronously."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.search(
                business_id,
                query_text,
                max_results=max_results,
                categories=categories,
            ),
        )

    def get_collection_stats(self, business_id: str) -> dict:
        """Get stats for a business collection."""
        collection = self.get_collection(business_id)
        return {
            "name": collection.name,
            "count": collection.count(),
        }

    def delete_collection(self, business_id: str) -> bool:
        """Delete entire collection for a business."""
        try:
            collection_name = self._get_collection_name(business_id)
            self.client.delete_collection(collection_name)
            self._collections.pop(collection_name, None)
            logger.info(f"Deleted collection {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection for {business_id}: {e}")
            return False

    def health_check(self) -> bool:
        """Check if ChromaDB is operational."""
        try:
            # Try to list collections
            _ = self.client.list_collections()
            return True
        except Exception as e:
            logger.warning(f"ChromaDB health check failed: {e}")
            return False


# Singleton instance
_chromadb_store: ChromaDBStore | None = None


def get_chromadb_store() -> ChromaDBStore:
    """Get the singleton ChromaDB store instance."""
    global _chromadb_store
    if _chromadb_store is None:
        _chromadb_store = ChromaDBStore()
    return _chromadb_store
