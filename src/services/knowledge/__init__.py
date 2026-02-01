"""Knowledge retrieval service for RAG during voice calls.

This package provides:
- KnowledgeService: Main interface for retrieving relevant knowledge
- ChromaDB integration for vector similarity search
- Sentence-transformers embeddings for Hindi/English support
"""

from src.services.knowledge.protocol import (
    KnowledgeQuery,
    KnowledgeResult,
    RetrievedKnowledge,
)
from src.services.knowledge.retriever import KnowledgeRetriever

__all__ = [
    "KnowledgeQuery",
    "KnowledgeResult",
    "RetrievedKnowledge",
    "KnowledgeRetriever",
]
