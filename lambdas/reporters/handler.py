"""
SIGINT Reporter Agent Lambda
Handles fetching and analyzing news for a specific category
"""

import json
import logging
import os

# Add shared to path
import sys
import time
from datetime import UTC, datetime
from typing import Any

sys.path.insert(0, "/opt/python")

from shared.feed_fetcher import FeedFetcher
from shared.llm_client import LLMClient
from shared.models import AgentResult, Category, CategoryData, NewsItem, Urgency
from shared.s3_store import S3Store

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Feed configurations per category
CATEGORY_FEEDS = {
    Category.GEOPOLITICAL: [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.npr.org/1001/rss.xml",
        "https://www.theguardian.com/world/rss",
        "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best",
        "https://www.csis.org/analysis/feed",
        "https://www.brookings.edu/feed/",
        "https://www.cfr.org/rss.xml",
        "https://www.defenseone.com/rss/all/",
        "https://warontherocks.com/feed/",
        "https://breakingdefense.com/feed/",
        "https://www.thedrive.com/the-war-zone/feed",
        "https://thediplomat.com/feed/",
        "https://www.al-monitor.com/rss",
        "https://www.bellingcat.com/feed/",
        "https://www.state.gov/rss-feed/press-releases/feed/",
    ],
    Category.AI_ML: [
        "https://hnrss.org/frontpage",
        "https://rss.arxiv.org/rss/cs.AI",
        "https://openai.com/blog/rss.xml",
        "https://www.anthropic.com/rss.xml",
        "https://blog.google/technology/ai/rss/",
        "https://deepmind.google/blog/rss.xml",
        "https://ai.meta.com/blog/rss/",
        "https://huggingface.co/blog/feed.xml",
        "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "https://www.theverge.com/rss/index.xml",
        "https://www.technologyreview.com/feed/",
    ],
    Category.DEEP_TECH: [
        "https://hnrss.org/frontpage",
        "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "https://www.theverge.com/rss/index.xml",
        "https://www.technologyreview.com/feed/",
        "https://rss.arxiv.org/rss/cs.AI",
        "https://rss.arxiv.org/rss/quant-ph",  # Quantum
    ],
    Category.CRYPTO_FINANCE: [
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.marketwatch.com/marketwatch/topstories",
        "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
        "https://www.federalreserve.gov/feeds/press_all.xml",
        "https://www.sec.gov/news/pressreleases.rss",
        # Crypto price API
        "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true",
        # Polymarket
        "https://gamma-api.polymarket.com/markets?closed=false&order=volume&ascending=false&limit=25",
    ],
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for reporter agent"""
    start_time = time.time()

    # Get category from event
    category_str = event.get("category", "geopolitical")
    try:
        category = Category(category_str)
    except ValueError:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Invalid category: {category_str}"}),
        }

    logger.info(f"Starting reporter for category: {category.value}")

    # Initialize components
    bucket_name = os.environ.get("DATA_BUCKET", "sigint-data")
    s3_store = S3Store(bucket_name)
    feed_fetcher = FeedFetcher()
    llm_client = LLMClient()

    try:
        # Get feeds for this category
        feeds = CATEGORY_FEEDS.get(category, [])
        if not feeds:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"No feeds configured for {category.value}"}),
            }

        # Fetch all feeds
        logger.info(f"Fetching {len(feeds)} feeds for {category.value}")
        raw_items = feed_fetcher.fetch_feeds_sync(feeds)
        logger.info(f"Fetched {len(raw_items)} raw items")

        # Get already-seen items for deduplication
        seen_ids = s3_store.get_seen_ids(category)
        new_items = [item for item in raw_items if item.id not in seen_ids]
        logger.info(f"Found {len(new_items)} new items after deduplication")

        # If no new items, return current data
        if not new_items:
            current = s3_store.get_category_data(category)
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "category": category.value,
                        "message": "No new items",
                        "current_items": len(current.items) if current else 0,
                    }
                ),
            }

        # Analyze with LLM
        logger.info(f"Analyzing {len(new_items)} items with LLM")
        selected, agent_notes = llm_client.analyze_items(category, new_items)
        logger.info(f"LLM selected {len(selected)} items")

        # Convert to NewsItem objects
        news_items = []
        for sel in selected:
            item_idx = sel.get("item_number", 1) - 1
            if 0 <= item_idx < len(new_items):
                raw_item = new_items[item_idx]
                news_item = NewsItem(
                    id=raw_item.id,
                    title=raw_item.title,
                    summary=sel.get("summary", raw_item.description[:200]),
                    url=raw_item.link,
                    source=raw_item.source,
                    source_url=raw_item.source_url,
                    category=category,
                    urgency=Urgency(sel.get("urgency", "normal")),
                    relevance_score=sel.get("relevance_score", 0.5),
                    published_at=raw_item.published,
                    entities=sel.get("entities", []),
                    tags=sel.get("tags", []),
                )
                news_items.append(news_item)

        # Get current data and merge
        current = s3_store.get_category_data(category)
        if current:
            # Keep existing items that aren't in new selection
            existing_ids = {item.id for item in news_items}
            for item in current.items:
                if item.id not in existing_ids:
                    news_items.append(item)

        # Sort by relevance and take top 5
        news_items.sort(key=lambda x: x.relevance_score, reverse=True)
        top_items = news_items[:5]

        # Create category data
        category_data = CategoryData(
            category=category,
            items=top_items,
            last_updated=datetime.now(UTC),
            agent_notes=agent_notes,
        )

        # Save to S3
        s3_store.save_category_data(category_data)

        # Archive all processed items
        s3_store.archive_items(category, news_items)

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Create result
        result = AgentResult(
            category=category,
            success=True,
            items_processed=len(raw_items),
            items_selected=len(top_items),
            top_items=top_items,
            run_duration_ms=duration_ms,
        )

        logger.info(f"Reporter completed for {category.value} in {duration_ms}ms")

        return {"statusCode": 200, "body": json.dumps(result.model_dump(), default=str)}

    except Exception as e:
        logger.error(f"Reporter error for {category.value}: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e), "category": category.value}),
        }


# For local testing
if __name__ == "__main__":
    import sys

    category = sys.argv[1] if len(sys.argv) > 1 else "geopolitical"
    result = handler({"category": category}, None)
    print(json.dumps(json.loads(result["body"]), indent=2))
