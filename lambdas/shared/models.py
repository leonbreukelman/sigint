"""
SIGINT Data Models
Pydantic models for type safety and serialization
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

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
    MARKETS = "markets"
    NARRATIVE = "narrative"
    BREAKING = "breaking"


class PredictionMarket(BaseModel):
    """A prediction market related to a news item"""

    question: str = Field(..., description="The prediction market question")
    probability: float | None = Field(default=None, ge=0, le=1, description="Current probability (0-1)")
    source: str = Field(..., description="Market source (Polymarket, Kalshi, Metaculus)")
    volume: str | None = Field(default=None, description="Trading volume if available")
    url: str | None = Field(default=None, description="Link to the market")
    end_date: str | None = Field(default=None, description="Market resolution date")


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
    prediction_market: PredictionMarket | None = Field(
        default=None, description="Related prediction market if found"
    )


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
    # Enhanced narrative fields
    paragraph: str | None = Field(
        default=None,
        description="Explanatory paragraph with context and implications",
    )
    implications: list[str] = Field(
        default_factory=list,
        description="Key implications or 'so what' points",
    )
    related_entities: list[str] = Field(
        default_factory=list,
        description="Key entities involved in this narrative",
    )


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


class TweetItem(BaseModel):
    """A single tweet from Twitter/X API v2"""

    tweet_id: str = Field(..., description="Twitter tweet ID")
    author_handle: str = Field(..., description="Author's @handle")
    author_id: str = Field(..., description="Author's Twitter user ID")
    content: str = Field(..., description="Tweet text content")
    created_at: datetime = Field(..., description="Tweet creation timestamp")
    hashtags: list[str] = Field(default_factory=list, description="Hashtags in tweet")
    mentions: list[str] = Field(default_factory=list, description="@mentions in tweet")
    cashtags: list[str] = Field(default_factory=list, description="$cashtags in tweet")
    retweet_count: int = Field(default=0, description="Number of retweets")
    like_count: int = Field(default=0, description="Number of likes")
    reply_count: int = Field(default=0, description="Number of replies")
    quote_count: int = Field(default=0, description="Number of quote tweets")
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_type: str = Field(default="list", description="How tweet was collected: list, search, user")

    @property
    def engagement_score(self) -> int:
        """Total engagement (retweets + likes + replies + quotes)"""
        return self.retweet_count + self.like_count + self.reply_count + self.quote_count

    @property
    def all_entities(self) -> list[str]:
        """All entities: hashtags, mentions, cashtags"""
        return self.hashtags + self.mentions + self.cashtags


class CorrelatedNarrative(BaseModel):
    """A narrative correlation between Twitter activity and news coverage"""

    correlation_id: str = Field(..., description="Unique correlation ID")
    title: str = Field(..., description="Narrative title/summary")
    tweet_ids: list[str] = Field(default_factory=list, description="Related tweet IDs")
    news_article_ids: list[str] = Field(default_factory=list, description="Related news item IDs")
    keywords: list[str] = Field(default_factory=list, description="Matched keywords")
    hashtags: list[str] = Field(default_factory=list, description="Related hashtags")
    tweet_spike_time: datetime | None = Field(default=None, description="When tweet velocity spiked")
    news_publish_time: datetime | None = Field(default=None, description="When first news article published")
    lead_lag_hours: float | None = Field(
        default=None,
        description="Hours between tweet spike and news (negative = tweets led)"
    )
    confidence_score: float = Field(
        default=0.0, ge=0, le=1, description="Correlation confidence 0-1"
    )
    amplification_factor: float = Field(
        default=1.0, ge=0, description="Tweet velocity multiplier vs baseline"
    )
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    evidence_summary: str = Field(default="", description="LLM-generated evidence summary")
    questions: list[str] = Field(
        default_factory=list, description="Questions to investigate"
    )


class VelocitySpike(BaseModel):
    """A detected spike in tweet velocity for an entity"""

    entity: str = Field(..., description="Entity that spiked (hashtag, mention, keyword)")
    velocity: float = Field(..., description="Tweets per hour during spike")
    baseline_velocity: float = Field(default=0.0, description="Normal tweets per hour")
    magnitude: float = Field(..., ge=1.0, description="Spike magnitude (velocity / baseline)")
    spike_start: datetime = Field(..., description="When spike started")
    spike_peak: datetime = Field(..., description="When spike peaked")
    sample_tweet_ids: list[str] = Field(default_factory=list, description="Sample tweets during spike")
    triggered_search: bool = Field(default=False, description="Whether this triggered an event search")


class TwitterCategoryData(BaseModel):
    """Twitter data for a category (e.g., AI/ML pilot)"""

    category: Category
    tweets: list[TweetItem]
    velocity_spikes: list[VelocitySpike] = Field(default_factory=list)
    correlations: list[CorrelatedNarrative] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
    api_calls_today: int = Field(default=0, description="API calls made today")
    api_calls_month: int = Field(default=0, description="API calls made this month")
    cache_hits: int = Field(default=0, description="Cache hits this session")


class DashboardState(BaseModel):
    """Complete dashboard state for frontend"""

    categories: dict[str, CategoryData]
    narratives: list[NarrativePattern]
    last_updated: datetime
    system_status: str = "operational"


# =============================================================================
# Raw Data Layer Models (Stage 1 of Unified Architecture)
# =============================================================================


class SourceType(str, Enum):
    """Source types for raw data ingestion"""

    RSS = "rss"
    TWITTER = "twitter"
    POLYMARKET = "polymarket"
    TICKER = "ticker"


class TwitterSignal(BaseModel):
    """Summarized Twitter signal for unified analysis prompt"""

    entity: str = Field(..., description="Entity being tracked (hashtag, keyword, mention)")
    velocity: float = Field(..., description="Tweets per hour")
    velocity_ratio: float = Field(
        default=1.0, ge=0, description="Ratio vs baseline (2.0 = 2x normal)"
    )
    sample_tweets: list[str] = Field(
        default_factory=list, max_length=3, description="Top 3 tweet texts for context"
    )
    top_accounts: list[str] = Field(
        default_factory=list, max_length=5, description="Top accounts tweeting about this"
    )
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_spike: bool = Field(default=False, description="Whether this is a velocity spike")


class RawSourceData(BaseModel):
    """Raw data ingested from any source before unified analysis"""

    source_type: SourceType = Field(..., description="Type of source")
    category: Category = Field(..., description="Category this data belongs to")
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Source-specific data (only one populated per instance)
    rss_items: list[NewsItem] = Field(default_factory=list, description="Raw RSS items")
    tweets: list[TweetItem] = Field(default_factory=list, description="Raw tweets")
    twitter_signals: list[TwitterSignal] = Field(
        default_factory=list, description="Aggregated Twitter signals"
    )
    prediction_markets: list[PredictionMarket] = Field(
        default_factory=list, description="Prediction market data"
    )
    ticker_data: dict[str, Any] = Field(
        default_factory=dict, description="Raw ticker/price data"
    )

    # Metadata
    item_count: int = Field(default=0, description="Number of items ingested")
    source_urls: list[str] = Field(default_factory=list, description="Source URLs fetched")
    errors: list[str] = Field(default_factory=list, description="Any errors during ingestion")


class AnalyzedItem(BaseModel):
    """Output from unified multi-source analysis"""

    id: str = Field(..., description="Unique item ID")
    title: str = Field(..., description="Headline/title")
    summary: str = Field(..., description="AI-generated summary")
    url: str = Field(..., description="Source URL")
    source: str = Field(..., description="Primary source name")
    source_url: str = Field(default="", description="Original feed URL")
    category: Category
    urgency: Urgency = Urgency.NORMAL
    relevance_score: float = Field(..., ge=0, le=1, description="Base relevance 0-1")
    published_at: datetime | None = None
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    entities: list[str] = Field(default_factory=list, description="Extracted entities")

    # Multi-source attribution
    source_tags: list[SourceType] = Field(
        default_factory=list, description="Sources contributing to this item"
    )
    twitter_boost: float | None = Field(
        default=None, ge=0, le=1, description="Boost factor from Twitter correlation"
    )
    twitter_signals: list[str] = Field(
        default_factory=list, description="Related Twitter signals/entities"
    )
    market_probability: float | None = Field(
        default=None, ge=0, le=1, description="Related prediction market probability"
    )
    market_question: str | None = Field(
        default=None, description="Related prediction market question"
    )

    # Final confidence (combines base relevance + cross-source boosts)
    confidence: float = Field(
        default=0.5, ge=0, le=1, description="Overall confidence after cross-source analysis"
    )

    # Original item reference
    prediction_market: PredictionMarket | None = None


class UnifiedAnalysisResult(BaseModel):
    """Result from unified multi-source analysis for a category"""

    category: Category
    items: list[AnalyzedItem]
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Source availability
    sources_used: list[SourceType] = Field(default_factory=list)
    sources_missing: list[SourceType] = Field(default_factory=list)

    # Analysis metadata
    rss_count: int = Field(default=0, description="RSS items considered")
    twitter_signals_count: int = Field(default=0, description="Twitter signals used")
    markets_count: int = Field(default=0, description="Prediction markets checked")
    items_boosted: int = Field(default=0, description="Items with cross-source boost")

    # LLM metadata
    llm_model: str = Field(default="", description="Model used for analysis")
    llm_tokens: int = Field(default=0, description="Tokens used")
    analysis_duration_ms: int = Field(default=0, description="Analysis time")

    agent_notes: str | None = None
