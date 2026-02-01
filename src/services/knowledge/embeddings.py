"""Embedding service using sentence-transformers.

Uses a multilingual model that supports Hindi and English for
bilingual code-switching scenarios common in Indian voice calls.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from functools import lru_cache
from typing import Any

import numpy as np

from src.logging_config import get_logger

logger: Any = get_logger(__name__)

# Model selection:
# - all-MiniLM-L6-v2: Fast, 80MB, good general performance
# - paraphrase-multilingual-MiniLM-L12-v2: Better for Hindi, 420MB
# We start with the smaller model and can upgrade if needed
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingService:
    """Wrapper around sentence-transformers for text embeddings."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model = None
        self._dimension: int | None = None

    @property
    def model(self):
        """Lazy load the model on first use."""
        if self._model is None:
            self._model = _load_model(self._model_name)
            # Get dimension from a test embedding
            test_emb = self._model.encode(["test"])
            self._dimension = test_emb.shape[1]
            logger.info(
                f"Loaded embedding model {self._model_name} "
                f"(dimension={self._dimension})"
            )
        return self._model

    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        if self._dimension is None:
            _ = self.model  # Load model to get dimension
        return self._dimension or 384  # Default for MiniLM

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode texts to embeddings synchronously.

        Args:
            texts: List of text strings to encode

        Returns:
            numpy array of shape (len(texts), dimension)
        """
        if not texts:
            return np.array([])

        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,  # L2 normalize for cosine similarity
            show_progress_bar=False,
        )
        return embeddings  # type: ignore[no-any-return]

    async def encode_async(self, texts: list[str]) -> np.ndarray:
        """Encode texts to embeddings asynchronously.

        Runs the encoding in a thread pool to avoid blocking.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.encode, texts)

    def encode_single(self, text: str) -> list[float]:
        """Encode a single text to embedding.

        Returns a list for ChromaDB compatibility.
        """
        embeddings = self.encode([text])
        return embeddings[0].tolist()  # type: ignore[no-any-return]

    async def encode_single_async(self, text: str) -> list[float]:
        """Encode a single text asynchronously."""
        embeddings = await self.encode_async([text])
        return embeddings[0].tolist()  # type: ignore[no-any-return]


@lru_cache(maxsize=1)
def _load_model(model_name: str):
    """Load and cache the sentence-transformers model."""
    try:
        from sentence_transformers import SentenceTransformer

        logger.info(f"Loading sentence-transformers model: {model_name}")
        model = SentenceTransformer(model_name)
        return model
    except ImportError:
        logger.error(
            "sentence-transformers not installed. "
            "Install with: pip install sentence-transformers"
        )
        raise
    except Exception as e:
        logger.error(f"Failed to load embedding model: {e}")
        raise


def normalize_query(text: str) -> str:
    """Normalize query text for better retrieval.

    Applies:
    - Unicode NFC normalization (important for Hindi/Devanagari)
    - Lowercase conversion
    - Whitespace normalization (collapse multiple spaces)
    - Strip leading/trailing whitespace

    Args:
        text: Raw query text

    Returns:
        Normalized text
    """
    # Unicode normalization - NFC for consistent representation
    # This is important for Hindi where the same character can have
    # multiple Unicode representations
    text = unicodedata.normalize("NFC", text)

    # Lowercase (works for both Latin and Devanagari)
    text = text.lower()

    # Collapse multiple whitespace to single space
    text = re.sub(r"\s+", " ", text)

    # Strip
    text = text.strip()

    return text


def create_search_text(
    title: str,
    content: str,
    title_hindi: str | None = None,
    content_hindi: str | None = None,
) -> str:
    """Create combined text for embedding.

    Combines English and Hindi versions for better multilingual retrieval.
    Text is normalized for consistent embeddings.
    """
    parts = [normalize_query(title), normalize_query(content)]
    if title_hindi:
        parts.append(normalize_query(title_hindi))
    if content_hindi:
        parts.append(normalize_query(content_hindi))
    return " | ".join(parts)


# Singleton instance
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get the singleton embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
