"""
SIGINT Data Models
Pydantic models for type safety and serialization
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class Urgency(str, Enum):
    BREAKING = "breaking"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class Category(str, Enum):
    GEOPOLITICAL = "geopolitical"
    AI_ML = "ai-ml"
    DEEP_TECH = "deep-tech"
    CRYPTO_FINANCE = "crypto-finance"
    NARRATIVE = "narrative"
    BREAKING = "breaking"


class NewsItem(BaseModel):
    """A single news item processed by an agent"""

    id: str = Field(..., description="Unique identifier (hash of url+title)")
    title: str = Field(..., description="Headline/title")
    summary: str = Field(..., description="AI-generated summary, 1-2 sentences")
    url: str = Field(..., description="Source URL")
    source: str = Field(..., description="Source name (BBC, ArXiv, etc.)")
    source_url: str = Field(..., description="Original feed URL")
    category: Category
    urgency: Urgency = Urgency.NORMAL
    relevance_score: float = Field(..., ge=0, le=1, description="0-1 relevance score")
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    entities: list[str] = Field(default_factory=list, description="Key entities mentioned")
    tags: list[str] = Field(default_factory=list, description="Topic tags")
    related_items: list[str] = Field(default_factory=list, description="IDs of related items")


class CategoryData(BaseModel):
    """Data for a single category panel"""

    category: Category
    items: list[NewsItem]
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent_notes: str | None = None  # Agent's meta-commentary


class NarrativePattern(BaseModel):
    """A detected cross-source narrative pattern"""

    id: str
    title: str
    description: str
    sources: list[str]  # Source names where pattern detected
    item_ids: list[str]  # Related news item IDs
    strength: float = Field(..., ge=0, le=1, description="Pattern strength 0-1")
    first_seen: datetime
    last_seen: datetime


class AgentResult(BaseModel):
    """Result from an agent run"""

    category: Category
    success: bool
    items_processed: int
    items_selected: int
    top_items: list[NewsItem]
    patterns_detected: list[NarrativePattern] = Field(default_factory=list)
    run_duration_ms: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None


class DashboardState(BaseModel):
    """Complete dashboard state for frontend"""

    categories: dict[str, CategoryData]
    narratives: list[NarrativePattern]
    last_updated: datetime
    system_status: str = "operational"
