"""Protocol and data types for knowledge retrieval service."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field as PydanticField

from src.db.models import KnowledgeCategory


# =============================================================================
# Category-specific Metadata Schemas
# =============================================================================


class MenuItemMetadata(BaseModel):
    """Metadata schema for menu_item category."""

    category: str = PydanticField(description="Menu category (e.g., Momos, Beverages)")
    price: int = PydanticField(ge=0, description="Price in INR")
    is_vegetarian: bool = PydanticField(default=False)
    is_vegan: bool = PydanticField(default=False)
    is_spicy: bool = PydanticField(default=False)
    keywords: list[str] = PydanticField(default_factory=list, description="Search keywords")


class FAQMetadata(BaseModel):
    """Metadata schema for faq category."""

    topic: str = PydanticField(description="FAQ topic category")
    variants: list[str] = PydanticField(
        default_factory=list,
        description="Alternative phrasings of the question",
    )


class PolicyMetadata(BaseModel):
    """Metadata schema for policy category."""

    effective_date: str | None = PydanticField(
        default=None,
        description="When the policy takes effect (YYYY-MM-DD)",
    )
    expiry_date: str | None = PydanticField(
        default=None,
        description="When the policy expires (YYYY-MM-DD)",
    )


class AnnouncementMetadata(BaseModel):
    """Metadata schema for announcement category."""

    start_date: str | None = PydanticField(
        default=None,
        description="When to start showing (YYYY-MM-DD)",
    )
    end_date: str | None = PydanticField(
        default=None,
        description="When to stop showing (YYYY-MM-DD)",
    )
    highlight: bool = PydanticField(
        default=False,
        description="Whether to emphasize this announcement",
    )


def parse_metadata(
    metadata_json: str | None,
    category: KnowledgeCategory,
) -> dict:
    """Parse and validate metadata JSON based on category.

    Returns validated dict, or empty dict if parsing fails.
    """
    if not metadata_json:
        return {}

    try:
        data = json.loads(metadata_json)
    except json.JSONDecodeError:
        return {}

    # Validate based on category
    try:
        if category == KnowledgeCategory.menu_item:
            return MenuItemMetadata(**data).model_dump()
        elif category == KnowledgeCategory.faq:
            return FAQMetadata(**data).model_dump()
        elif category == KnowledgeCategory.policy:
            return PolicyMetadata(**data).model_dump()
        elif category == KnowledgeCategory.announcement:
            return AnnouncementMetadata(**data).model_dump()
    except Exception:
        pass

    # Return raw data if validation fails (for backwards compat)
    return data


@dataclass(frozen=True)
class KnowledgeQuery:
    """Query for knowledge retrieval."""

    business_id: str
    query_text: str
    max_results: int = 5
    categories: list[KnowledgeCategory] | None = None  # Filter by category
    min_score: float = 0.3  # Minimum similarity score


@dataclass
class RetrievedKnowledge:
    """A single retrieved knowledge item with relevance score."""

    id: str
    category: KnowledgeCategory
    title: str
    title_hindi: str | None
    content: str
    content_hindi: str | None
    metadata: dict  # Parsed from metadata_json
    priority: int
    score: float  # Similarity score from vector search

    def to_prompt_text(self) -> str:
        """Format for injection into LLM prompt."""
        if self.category == KnowledgeCategory.menu_item:
            price = self.metadata.get("price", "N/A")
            veg = " (Veg)" if self.metadata.get("is_vegetarian") else ""
            return f"- {self.title}{veg}: {self.content} - Rs.{price}"

        elif self.category == KnowledgeCategory.faq:
            return f"Q: {self.title}\nA: {self.content}"

        elif self.category == KnowledgeCategory.policy:
            return f"Policy - {self.title}: {self.content}"

        elif self.category == KnowledgeCategory.announcement:
            return f"Note: {self.content}"

        return f"- {self.title}: {self.content}"


@dataclass
class KnowledgeResult:
    """Result of knowledge retrieval."""

    query: KnowledgeQuery
    items: list[RetrievedKnowledge] = field(default_factory=list)
    retrieval_time_ms: float = 0.0

    @property
    def has_results(self) -> bool:
        return len(self.items) > 0

    def to_prompt_section(self) -> str:
        """Format all retrieved knowledge for LLM prompt injection."""
        if not self.items:
            return ""

        lines = ["## Relevant Information"]

        # Group by category for cleaner prompt
        by_category: dict[KnowledgeCategory, list[RetrievedKnowledge]] = {}
        for item in self.items:
            by_category.setdefault(item.category, []).append(item)

        # Menu items
        if KnowledgeCategory.menu_item in by_category:
            lines.append("\n### Menu Items")
            for item in by_category[KnowledgeCategory.menu_item]:
                lines.append(item.to_prompt_text())

        # FAQs
        if KnowledgeCategory.faq in by_category:
            lines.append("\n### Frequently Asked Questions")
            for item in by_category[KnowledgeCategory.faq]:
                lines.append(item.to_prompt_text())

        # Policies
        if KnowledgeCategory.policy in by_category:
            lines.append("\n### Policies")
            for item in by_category[KnowledgeCategory.policy]:
                lines.append(item.to_prompt_text())

        # Announcements
        if KnowledgeCategory.announcement in by_category:
            lines.append("\n### Current Announcements")
            for item in by_category[KnowledgeCategory.announcement]:
                lines.append(item.to_prompt_text())

        return "\n".join(lines)


class KnowledgeService(Protocol):
    """Protocol for knowledge retrieval implementations."""

    async def search(self, query: KnowledgeQuery) -> KnowledgeResult:
        """Search for relevant knowledge items."""
        ...

    async def index_item(
        self,
        business_id: str,
        item_id: str,
        title: str,
        content: str,
        title_hindi: str | None = None,
        content_hindi: str | None = None,
    ) -> str:
        """Index a knowledge item for retrieval. Returns embedding_id."""
        ...

    async def remove_item(self, business_id: str, embedding_id: str) -> bool:
        """Remove a knowledge item from the index."""
        ...

    async def reindex_business(self, business_id: str) -> int:
        """Reindex all items for a business. Returns count indexed."""
        ...

    async def health_check(self) -> bool:
        """Check if the service is operational."""
        ...
