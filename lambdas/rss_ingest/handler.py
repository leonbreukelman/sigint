"""
SIGINT RSS Ingestion Lambda

Stage 1 of Unified Analysis Architecture.
Fetches RSS feeds for a category and stores raw items to S3.
Does NOT perform LLM analysis - that's handled by the Analyzer Lambda.

This Lambda:
1. Fetches all RSS feeds for a category
2. Deduplicates against previously seen items
3. Filters by age (default 72h)
4. Saves raw items to raw/{category}/rss.json
"""

import json
import logging
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any

# Add shared to path for Lambda layer
sys.path.insert(0, "/opt/python")

from shared.feed_fetcher import FeedFetcher, RawFeedItem
from shared.models import (
    Category,
    NewsItem,
    RawSourceData,
    SourceType,
    Urgency,
)
from shared.s3_store import S3Store

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Environment
DATA_BUCKET = os.environ.get("DATA_BUCKET", "")
MAX_AGE_HOURS = int(os.environ.get("MAX_AGE_HOURS", "72"))

# Feed configurations per category (copied from reporters)
CATEGORY_FEEDS = {
    Category.GEOPOLITICAL: [
        # Major news outlets
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.npr.org/1001/rss.xml",
        "https://www.theguardian.com/world/rss",
        "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://feeds.washingtonpost.com/rss/world",
        "https://www.aljazeera.com/xml/rss/all.xml",
        # Think tanks & analysis
        "https://www.csis.org/analysis/feed",
        "https://www.brookings.edu/feed/",
        "https://www.cfr.org/rss.xml",
        "https://carnegieendowment.org/rss/solr/?fa=topStories",
        # Defense & security
        "https://www.defenseone.com/rss/all/",
        "https://warontherocks.com/feed/",
        "https://breakingdefense.com/feed/",
        # Regional specialists
        "https://thediplomat.com/feed/",
        "https://foreignpolicy.com/feed/",
        # OSINT
        "https://www.bellingcat.com/feed/",
    ],
    Category.AI_ML: [
        # Tech news
        "https://hnrss.org/frontpage",
        "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "https://www.theverge.com/rss/index.xml",
        "https://www.technologyreview.com/feed/",
        "https://www.wired.com/feed/category/artificial-intelligence/latest/rss",
        "https://venturebeat.com/category/ai/feed/",
        # Research
        "https://rss.arxiv.org/rss/cs.AI",
        "https://rss.arxiv.org/rss/cs.LG",
        "https://rss.arxiv.org/rss/cs.CL",
        # Company blogs
        "https://openai.com/blog/rss.xml",
        "https://www.anthropic.com/rss.xml",
        "https://blog.google/technology/ai/rss/",
        "https://deepmind.google/blog/rss.xml",
        "https://ai.meta.com/blog/rss/",
        "https://huggingface.co/blog/feed.xml",
        # Newsletters
        "https://www.marktechpost.com/feed/",
        "https://jack-clark.net/feed/",
        "https://lastweekin.ai/feed",
    ],
    Category.DEEP_TECH: [
        "https://feeds.arstechnica.com/arstechnica/science",
        "https://www.quantamagazine.org/feed/",
        "https://www.technologyreview.com/feed/",
        "https://spectrum.ieee.org/feeds/feed.rss",
        "https://rss.arxiv.org/rss/quant-ph",
        "https://phys.org/rss-feed/breaking/physics-news/quantum-physics/",
        "https://www.nature.com/nature.rss",
        "https://www.science.org/rss/news_current.xml",
        "https://semianalysis.com/feed/",
    ],
    Category.CRYPTO_FINANCE: [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
        "https://thedefiant.io/feed",
        "https://www.theblock.co/rss.xml",
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://www.ft.com/markets?format=rss",
        "https://feeds.reuters.com/reuters/businessNews",
    ],
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    RSS Ingestion Lambda handler.

    Event structure:
    {
        "category": "ai-ml",  # Category to ingest
        "max_age_hours": 72   # Optional age filter override
    }
    """
    start_time = time.time()

    category_str = event.get("category", "")
    max_age_hours = event.get("max_age_hours", MAX_AGE_HOURS)

    # Validate category
    try:
        category = Category(category_str)
    except ValueError:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Invalid category: {category_str}"}),
        }

    if not DATA_BUCKET:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "DATA_BUCKET not configured"}),
        }

    logger.info(f"RSS Ingest starting for {category.value}, max_age={max_age_hours}h")

    # Initialize clients
    s3_store = S3Store(DATA_BUCKET)
    feed_fetcher = FeedFetcher()

    try:
        # Get feeds for this category
        feeds = CATEGORY_FEEDS.get(category, [])
        if not feeds:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"No feeds configured for {category.value}"}),
            }

        # Fetch all feeds
        logger.info(f"Fetching {len(feeds)} feeds")
        raw_items = feed_fetcher.fetch_feeds_sync(feeds)
        logger.info(f"Fetched {len(raw_items)} raw items")

        # Get already-seen items for deduplication
        seen_ids = s3_store.get_seen_ids(category)
        new_items = [item for item in raw_items if item.id not in seen_ids]
        logger.info(f"Found {len(new_items)} new items after deduplication")

        # Filter by age
        cutoff_time = datetime.now(UTC) - timedelta(hours=max_age_hours)
        age_filtered = []
        for item in new_items:
            if item.published and item.published >= cutoff_time:
                age_filtered.append(item)
            elif not item.published:
                # Include items without published date (assume recent)
                age_filtered.append(item)

        logger.info(f"Kept {len(age_filtered)} items after age filter ({max_age_hours}h)")

        # Convert RawFeedItem to NewsItem for storage
        news_items = _convert_to_news_items(age_filtered, category)

        # Save to raw data layer
        raw_data = RawSourceData(
            source_type=SourceType.RSS,
            category=category,
            ingested_at=datetime.now(UTC),
            rss_items=news_items,
            item_count=len(news_items),
            source_urls=feeds,
        )

        s3_key = s3_store.save_raw_data(raw_data)

        duration_ms = int((time.time() - start_time) * 1000)

        result = {
            "category": category.value,
            "feeds_fetched": len(feeds),
            "items_fetched": len(raw_items),
            "items_new": len(new_items),
            "items_after_age_filter": len(age_filtered),
            "items_saved": len(news_items),
            "s3_key": s3_key,
            "duration_ms": duration_ms,
        }

        logger.info(f"RSS Ingest completed: {result}")

        return {
            "statusCode": 200,
            "body": json.dumps(result),
        }

    except Exception as e:
        logger.exception(f"RSS Ingest failed: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


def _convert_to_news_items(
    raw_items: list[RawFeedItem], category: Category
) -> list[NewsItem]:
    """Convert RawFeedItem objects to NewsItem for storage.

    At this stage, we don't have LLM analysis, so:
    - summary = description (raw, will be refined by analyzer)
    - relevance_score = 0.5 (neutral, will be set by analyzer)
    - urgency = NORMAL (will be set by analyzer)
    - entities = empty (will be extracted by analyzer)
    """
    news_items = []

    for raw in raw_items:
        # Use description as initial summary, truncate if too long
        summary = raw.description[:500] if raw.description else raw.title

        news_item = NewsItem(
            id=raw.id,
            title=raw.title,
            summary=summary,
            url=raw.link,
            source=raw.source,
            source_url=raw.source_url,
            category=category,
            urgency=Urgency.NORMAL,
            relevance_score=0.5,  # Neutral - will be updated by analyzer
            published_at=raw.published,
            fetched_at=datetime.now(UTC),
            entities=[],  # Will be extracted by analyzer
            tags=[],
        )
        news_items.append(news_item)

    return news_items
