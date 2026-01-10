"""
SIGINT Unified Analyzer Lambda

Stage 2 of the unified multi-source analysis pipeline.
Loads raw data from all sources (RSS, Twitter, Polymarket, Tickers),
combines them in a single LLM call with cross-source boosting, and saves
analyzed results back to S3.

Flow:
1. Load raw/{category}/rss.json (from RSS Ingest Lambda)
2. Load raw/{category}/twitter.json (from Twitter Lambda)
3. Load raw/{category}/polymarket.json (from Polymarket Lambda, if available)
4. Call LLMClient.analyze_unified() with all sources
5. Save analyzed results to current/{category}.json (backward compatible)
6. Return metrics and status
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Add lambdas directory to path for imports
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared import Category, LLMClient, S3Store, SourceType
from shared.models import NewsItem, PredictionMarket, RawSourceData, TwitterSignal

# Environment
DATA_BUCKET = os.environ.get("DATA_BUCKET", "sigint-data")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Categories eligible for unified analysis
UNIFIED_CATEGORIES = [
    Category.AI_ML,
    Category.GEOPOLITICAL,
    Category.DEEP_TECH,
    Category.CRYPTO_FINANCE,
]


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Unified analyzer Lambda handler.

    Event:
        category (str): Category to analyze (e.g., 'ai-ml')

    Returns:
        Dict with status, metrics, and analyzed item count
    """
    start_time = time.time()

    # Parse category
    category_str = event.get("category", "ai-ml")
    try:
        category = Category(category_str)
    except ValueError:
        logger.error(f"Invalid category: {category_str}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Invalid category: {category_str}"}),
        }

    if category not in UNIFIED_CATEGORIES:
        logger.warning(f"Category {category.value} not eligible for unified analysis")
        return {
            "statusCode": 400,
            "body": json.dumps(
                {"error": f"Category {category.value} not eligible for unified analysis"}
            ),
        }

    logger.info(f"Starting unified analysis for {category.value}")

    # Initialize clients
    store = S3Store(bucket_name=DATA_BUCKET)
    llm = LLMClient(api_key=ANTHROPIC_API_KEY)

    # Metrics tracking
    metrics = {
        "rss_items_loaded": 0,
        "twitter_signals_loaded": 0,
        "polymarket_loaded": 0,
        "items_analyzed": 0,
        "items_boosted": 0,
        "sources_used": [],
        "sources_missing": [],
        "llm_tokens": 0,
        "llm_model": llm.model,
    }

    try:
        # Stage 2a: Load raw data from all sources
        rss_items, twitter_signals, prediction_markets = _load_raw_sources(
            store, category, metrics
        )

        if not rss_items:
            logger.warning(f"No RSS items found for {category.value}")
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "message": "No RSS items to analyze",
                        "category": category.value,
                        "metrics": metrics,
                    }
                ),
            }

        # Stage 2b: Run unified LLM analysis
        result = llm.analyze_unified(
            category=category,
            rss_items=rss_items,
            twitter_signals=twitter_signals,
            prediction_markets=prediction_markets,
        )

        # Update metrics
        metrics["items_analyzed"] = len(result.items)
        metrics["items_boosted"] = result.items_boosted
        metrics["llm_tokens"] = result.llm_tokens
        metrics["sources_used"] = [s.value for s in result.sources_used]
        metrics["sources_missing"] = [s.value for s in result.sources_missing]

        # Stage 2c: Save analyzed results (backward compatible format)
        _save_analyzed_results(store, category, result)

        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"Unified analysis complete for {category.value}: "
            f"{metrics['items_analyzed']} items, "
            f"{metrics['items_boosted']} boosted, "
            f"{metrics['llm_tokens']} tokens in {duration_ms}ms"
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "category": category.value,
                    "items_analyzed": metrics["items_analyzed"],
                    "items_boosted": metrics["items_boosted"],
                    "sources": metrics["sources_used"],
                    "llm_tokens": metrics["llm_tokens"],
                    "duration_ms": duration_ms,
                    "agent_notes": result.agent_notes,
                    "metrics": metrics,
                }
            ),
        }

    except Exception as e:
        logger.exception(f"Unified analysis failed for {category.value}: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "error": str(e),
                    "category": category.value,
                    "metrics": metrics,
                }
            ),
        }


def _load_raw_sources(
    store: S3Store, category: Category, metrics: dict[str, Any]
) -> tuple[list[NewsItem], list[TwitterSignal] | None, list[PredictionMarket] | None]:
    """
    Load raw data from all sources for a category.

    Returns:
        Tuple of (rss_items, twitter_signals, prediction_markets)
    """
    rss_items: list[NewsItem] = []
    twitter_signals: list[TwitterSignal] | None = None
    prediction_markets: list[PredictionMarket] | None = None

    # Load RSS data
    try:
        rss_data = store.load_raw_data(category, SourceType.RSS)
        if rss_data and rss_data.rss_items:
            rss_items = rss_data.rss_items
            metrics["rss_items_loaded"] = len(rss_items)
            logger.info(f"Loaded {len(rss_items)} RSS items for {category.value}")
    except Exception as e:
        logger.warning(f"Could not load RSS data for {category.value}: {e}")

    # Load Twitter signals
    try:
        twitter_data = store.load_raw_data(category, SourceType.TWITTER)
        if twitter_data and twitter_data.twitter_signals:
            twitter_signals = twitter_data.twitter_signals
            metrics["twitter_signals_loaded"] = len(twitter_signals)
            logger.info(f"Loaded {len(twitter_signals)} Twitter signals for {category.value}")
    except Exception as e:
        logger.warning(f"Could not load Twitter data for {category.value}: {e}")

    # Load Polymarket data (if available)
    try:
        polymarket_data = store.load_raw_data(category, SourceType.POLYMARKET)
        if polymarket_data and polymarket_data.prediction_markets:
            prediction_markets = polymarket_data.prediction_markets
            metrics["polymarket_loaded"] = len(prediction_markets)
            logger.info(f"Loaded {len(prediction_markets)} markets for {category.value}")
    except Exception as e:
        # Polymarket data is optional, don't warn
        logger.debug(f"No Polymarket data for {category.value}: {e}")

    return rss_items, twitter_signals, prediction_markets


def _save_analyzed_results(store: S3Store, category: Category, result) -> None:
    """
    Save analyzed results in backward-compatible CategoryData format.

    This ensures the existing frontend continues to work without changes.
    The items are converted from AnalyzedItem to NewsItem format with
    extra fields preserved in the serialization.
    """
    from shared.models import AnalyzedItem, CategoryData, UnifiedAnalysisResult

    # Convert AnalyzedItem objects to NewsItem for backward compatibility
    # The NewsItem model already supports serialization of extra fields
    news_items = []
    for analyzed in result.items:
        # Build a NewsItem with AnalyzedItem's extra data preserved
        item_data = {
            "id": analyzed.id,
            "title": analyzed.title,
            "summary": analyzed.summary,
            "url": analyzed.url,
            "source": analyzed.source,
            "category": analyzed.category.value,
            "urgency": analyzed.urgency.value,
            "relevance_score": analyzed.relevance_score,
            "entities": analyzed.entities,
            "published_at": analyzed.published_at.isoformat() if analyzed.published_at else None,
            "fetched_at": analyzed.analyzed_at.isoformat() if analyzed.analyzed_at else None,
            # Extra unified analysis fields (preserved in JSON but not in Pydantic model)
            "source_tags": [st.value for st in analyzed.source_tags],
            "twitter_boost": analyzed.twitter_boost,
            "twitter_signals": analyzed.twitter_signals,
            "market_probability": analyzed.market_probability,
            "market_question": analyzed.market_question,
            "confidence": analyzed.confidence,
        }

        # Create NewsItem for the items list
        news_item = NewsItem(
            id=analyzed.id,
            title=analyzed.title,
            summary=analyzed.summary,
            url=analyzed.url,
            source=analyzed.source,
            source_url=analyzed.source_url or analyzed.url,  # Fallback to url if not set
            category=analyzed.category,
            urgency=analyzed.urgency,
            relevance_score=analyzed.relevance_score,
            entities=analyzed.entities,
            published_at=analyzed.published_at,
        )
        news_items.append(news_item)

    # Create CategoryData for backward compatibility
    category_data = CategoryData(
        category=category,
        items=news_items,
        agent_summary=result.agent_notes or f"Unified analysis: {len(news_items)} items selected",
    )

    # Save to current/{category}.json
    store.save_category_data(category_data)

    # Also save full UnifiedAnalysisResult for debugging/future use
    store.save_unified_analysis(result)

    logger.info(f"Saved {len(news_items)} analyzed items for {category.value}")


# For local testing
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    category = sys.argv[1] if len(sys.argv) > 1 else "ai-ml"
    result = handler({"category": category}, None)
    print(json.dumps(json.loads(result["body"]), indent=2))
