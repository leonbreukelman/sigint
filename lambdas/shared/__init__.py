# SIGINT Shared Modules
from .correlation_engine import CorrelationEngine
from .feed_fetcher import FeedFetcher, RawFeedItem
from .llm_client import LLMClient
from .models import (
    AgentResult,
    AnalyzedItem,
    Category,
    CategoryData,
    CorrelatedNarrative,
    DashboardState,
    NarrativePattern,
    NewsItem,
    RawSourceData,
    SourceType,
    TweetItem,
    TwitterCategoryData,
    TwitterSignal,
    UnifiedAnalysisResult,
    Urgency,
    VelocitySpike,
)
from .s3_store import S3Store
from .twitter_client import RateLimitError, TwitterAPIError, TwitterClient
from .unified_prompt import build_unified_prompt, estimate_token_count

__all__ = [
    "CorrelationEngine",
    "FeedFetcher",
    "RawFeedItem",
    "S3Store",
    "LLMClient",
    "NewsItem",
    "CategoryData",
    "AgentResult",
    "Category",
    "Urgency",
    "NarrativePattern",
    "DashboardState",
    "TweetItem",
    "CorrelatedNarrative",
    "VelocitySpike",
    "TwitterCategoryData",
    "TwitterClient",
    "TwitterAPIError",
    "RateLimitError",
    # New unified architecture
    "SourceType",
    "TwitterSignal",
    "RawSourceData",
    "AnalyzedItem",
    "UnifiedAnalysisResult",
    "build_unified_prompt",
    "estimate_token_count",
]
