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

# Prediction market APIs - fetched by all reporters to find relevant markets
PREDICTION_MARKET_APIS = {
    "polymarket": "https://gamma-api.polymarket.com/markets?closed=false&order=volume&ascending=false&limit=50",
    # Metaculus public API - multiple topic-specific queries for better matching
    "metaculus_general": "https://www.metaculus.com/api2/questions/?status=open&order_by=-activity&limit=15",
    "metaculus_ai": "https://www.metaculus.com/api2/questions/?status=open&search=AI+OpenAI+Anthropic&limit=10",
    "metaculus_tech": "https://www.metaculus.com/api2/questions/?status=open&search=technology+crypto+bitcoin&limit=10",
    "metaculus_geopolitics": "https://www.metaculus.com/api2/questions/?status=open&search=election+war+military&limit=10",
}

# Feed configurations per category
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
        "https://www.rand.org/pubs/rss.xml",
        "https://rusi.org/rss.xml",
        "https://www.iiss.org/en/publications/rss",
        "https://www.aspistrategist.org.au/feed/",
        # Defense & security
        "https://www.defenseone.com/rss/all/",
        "https://warontherocks.com/feed/",
        "https://breakingdefense.com/feed/",
        "https://www.thedrive.com/the-war-zone/feed",
        "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
        # Regional specialists
        "https://thediplomat.com/feed/",
        "https://www.al-monitor.com/rss",
        "https://foreignpolicy.com/feed/",
        "https://www.euractiv.com/feed/",
        # OSINT & investigations
        "https://www.bellingcat.com/feed/",
        "https://www.state.gov/rss-feed/press-releases/feed/",
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
        "https://blogs.microsoft.com/ai/feed/",
        "https://aws.amazon.com/blogs/machine-learning/feed/",
        # Newsletters & analysis
        "https://www.marktechpost.com/feed/",
        "https://thegradient.pub/rss/",
        "https://jack-clark.net/feed/",
        "https://lastweekin.ai/feed",
    ],
    Category.DEEP_TECH: [
        # Tech news
        "https://hnrss.org/frontpage",
        "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "https://www.theverge.com/rss/index.xml",
        "https://www.technologyreview.com/feed/",
        "https://spectrum.ieee.org/feeds/feed.rss",
        "https://www.quantamagazine.org/feed/",
        # Semiconductors & hardware
        "https://semiengineering.com/feed/",
        "https://www.nextplatform.com/feed/",
        "https://www.anandtech.com/rss/",
        "https://www.tomshardware.com/feeds/all",
        "https://semianalysis.com/feed/",
        # Quantum & physics
        "https://rss.arxiv.org/rss/quant-ph",
        "https://phys.org/rss-feed/physics-news/quantum-physics/",
        # Biotech & life sciences
        "https://www.statnews.com/feed/",
        "https://www.fiercebiotech.com/rss/xml",
        # Space & aerospace
        "https://spacenews.com/feed/",
        "https://arstechnica.com/space/feed/",
        # Energy & climate tech
        "https://www.canarymedia.com/feed",
        # Security
        "https://krebsonsecurity.com/feed/",
        "https://www.cisa.gov/news-events/rss/news-and-press-releases",
    ],
    Category.CRYPTO_FINANCE: [
        # Traditional finance
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.marketwatch.com/marketwatch/topstories",
        "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://www.wsj.com/xml/rss/3_7031.xml",
        # Central banks & regulators
        "https://www.federalreserve.gov/feeds/press_all.xml",
        "https://www.sec.gov/news/pressreleases.rss",
        "https://www.ecb.europa.eu/rss/press.html",
        # Crypto news
        "https://decrypt.co/feed",
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://thedefiant.io/feed",
        "https://www.theblock.co/rss.xml",
        "https://www.dlnews.com/feed/",
        "https://cointelegraph.com/rss",
        # DeFi & analysis
        "https://newsletter.banklesshq.com/feed",
        "https://messari.io/rss/news",
        # Crypto price API
        "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true",
        # Polymarket
        "https://gamma-api.polymarket.com/markets?closed=false&order=volume&ascending=false&limit=25",
    ],
    Category.MARKETS: [
        # Expanded crypto prices - no API key needed
        "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,dogecoin,ripple,cardano,polkadot,avalanche-2,chainlink,polygon&vs_currencies=usd&include_24hr_change=true&include_market_cap=true",
        # Top coins by market cap for broader market view
        "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=20&page=1&sparkline=false&price_change_percentage=24h",
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

        # Special handling for markets - skip deduplication and LLM, just format prices
        if category == Category.MARKETS:
            news_items = []
            for raw_item in raw_items:
                # Format price data for ticker display
                news_item = NewsItem(
                    id=raw_item.id,
                    title=raw_item.title,  # Already formatted as "Bitcoin: $X,XXX.XX (+Y.YY%)"
                    summary=raw_item.description,
                    url=raw_item.link,
                    source=raw_item.source,
                    source_url=raw_item.source_url,
                    category=category,
                    urgency=Urgency.NORMAL,
                    relevance_score=0.5,
                    published_at=raw_item.published,
                    entities=[],
                    tags=[],
                )
                news_items.append(news_item)
            
            # Take top 20 for ticker
            top_items = news_items[:20]
            
            # Create category data
            category_data = CategoryData(
                category=category,
                items=top_items,
                last_updated=datetime.now(UTC),
                agent_notes=f"Market data from {len(raw_items)} sources",
            )
            
            # Save to S3
            s3_store.save_category_data(category_data)
            
            duration_ms = int((time.time() - start_time) * 1000)
            result = AgentResult(
                category=category,
                success=True,
                items_processed=len(raw_items),
                items_selected=len(top_items),
                top_items=top_items,
                run_duration_ms=duration_ms,
            )
            logger.info(f"Markets reporter completed in {duration_ms}ms with {len(top_items)} items")
            return {"statusCode": 200, "body": json.dumps(result.model_dump(), default=str)}

        # Get already-seen items for deduplication
        seen_ids = s3_store.get_seen_ids(category)
        new_items = [item for item in raw_items if item.id not in seen_ids]
        logger.info(f"Found {len(new_items)} new items after deduplication")

        # Apply pre-LLM filters to reduce costs
        # Includes: age filter, title similarity, source diversity
        feed_config = s3_store.get_feed_config()
        max_age_hours = feed_config.get("global_settings", {}).get("default_age_hours", 24)
        new_items = feed_fetcher.apply_pre_llm_filters(
            new_items,
            max_age_hours=max_age_hours,
            similarity_threshold=0.7,
            max_per_source=5,
        )
        logger.info(f"Found {len(new_items)} items after pre-LLM filtering")

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

        # Fetch prediction markets for context matching
        # Fetch from multiple sources: Polymarket + topic-specific Metaculus queries
        prediction_markets = []
        try:
            all_markets = []
            
            # Fetch from all Metaculus topic queries
            metaculus_urls = [
                PREDICTION_MARKET_APIS.get("metaculus_general"),
                PREDICTION_MARKET_APIS.get("metaculus_ai"),
                PREDICTION_MARKET_APIS.get("metaculus_tech"),
                PREDICTION_MARKET_APIS.get("metaculus_geopolitics"),
            ]
            for url in metaculus_urls:
                if url:
                    markets = feed_fetcher.fetch_feeds_sync([url])
                    all_markets.extend(markets)
            
            # Fetch Polymarket
            polymarket_url = PREDICTION_MARKET_APIS.get("polymarket")
            if polymarket_url:
                polymarket_markets = feed_fetcher.fetch_feeds_sync([polymarket_url])
                all_markets.extend(polymarket_markets)
            
            # Deduplicate by title
            seen_titles = set()
            unique_markets = []
            for m in all_markets:
                if m.title not in seen_titles:
                    seen_titles.add(m.title)
                    unique_markets.append(m)
            
            prediction_markets = unique_markets
            logger.info(f"Fetched {len(prediction_markets)} prediction markets for matching")
        except Exception as e:
            logger.warning(f"Failed to fetch prediction markets: {e}")

        # Analyze with LLM (including prediction markets for matching)
        logger.info(f"Analyzing {len(new_items)} items with LLM")
        selected, agent_notes = llm_client.analyze_items(
            category, new_items, prediction_markets if prediction_markets else None
        )
        logger.info(f"LLM selected {len(selected)} items")

        # Convert to NewsItem objects
        news_items = []
        for sel in selected:
            # Robust extraction of item_number (LLM sometimes returns list)
            item_num = sel.get("item_number", 1)
            if isinstance(item_num, list):
                item_num = item_num[0] if item_num else 1
            item_idx = int(item_num) - 1
            if 0 <= item_idx < len(new_items):
                raw_item = new_items[item_idx]
                
                # Extract prediction market if matched by LLM
                pm_data = None
                if sel.get("prediction_market") and prediction_markets:
                    pm_num = sel["prediction_market"].get("pm_number", 0)
                    if isinstance(pm_num, list):
                        pm_num = pm_num[0] if pm_num else 0
                    pm_idx = int(pm_num) - 1
                    if 0 <= pm_idx < len(prediction_markets):
                        pm_item = prediction_markets[pm_idx]
                        pm_raw = pm_item.raw_data
                        pm_data = {
                            "question": pm_item.title.replace("📊 ", "").replace("🔮 ", ""),
                            "probability": pm_raw.get("_parsed_probability"),
                            "source": pm_raw.get("_source", pm_item.source),
                            "volume": pm_raw.get("_parsed_volume"),
                            "url": pm_item.link,
                        }
                
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
                    prediction_market=pm_data,
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
