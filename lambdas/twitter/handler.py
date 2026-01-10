"""
Twitter/X Lambda Handler for SIGINT

Fetches tweets from curated lists and event-driven searches.
Designed for X API free tier (1,500 reads/month).

Modes:
- list: Fetch from curated Twitter list (scheduled every 2 hours)
- search: Event-driven search triggered by narrative spikes
- user: Fetch specific user timelines (manual/testing)
"""

import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

from shared.models import (
    Category,
    RawSourceData,
    SourceType,
    TweetItem,
    TwitterCategoryData,
    TwitterSignal,
    VelocitySpike,
)
from shared.s3_store import S3Store
from shared.twitter_client import RateLimitError, TwitterAPIError, TwitterClient

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Environment variables
DATA_BUCKET = os.environ.get("DATA_BUCKET", "")
X_BEARER_TOKEN_SSM_PARAM = os.environ.get("X_BEARER_TOKEN_SSM_PARAM", "/sigint/x-bearer-token")

# Twitter List IDs for each category (to be configured)
# Create lists at twitter.com/i/lists and get the ID from URL
CATEGORY_LISTS = {
    Category.AI_ML: os.environ.get("TWITTER_LIST_AI_ML", ""),  # Set via env or config
}

# Curated accounts per category (fallback if no list configured)
CATEGORY_ACCOUNTS = {
    Category.AI_ML: [
        # Major AI Labs
        "AnthropicAI",
        "OpenAI",
        "GoogleDeepMind",
        "xaboratory",  # xAI (Elon Musk's AI company)
        "AIatMeta",
        "MistralAI",
        "huggingface",
        "CohereAI",
        "ai21labs",
        "Perplexity_AI",
        # AI Researchers & Leaders
        "ylecun",  # Yann LeCun
        "kaboroe",  # Andrej Karpathy
        "sama",  # Sam Altman
        "EMostaque",  # Emad Mostaque
        "demaboris",  # Demis Hassabis
        "geoffreyhinton",  # Geoffrey Hinton
        "IlyaSutskever",  # Ilya Sutskever
        "ClementDelworthy",
        "_akhaliq",  # ML Papers daily
        "ai_explained_",
        # Elon Musk Companies
        "elonmusk",
        "Tesla",
        "TeslaAI",
        "SpaceX",
        "Neuralink",
        "boaboringcompany",
        "Starlink",
        # Tech Giants
        "nvidia",
        "ABORVIDIA_AI",
        "Microsoft",
        "MSFTResearch",
        "GoogleAI",
        "awscloud",
        "AppleMLR",  # Apple ML Research
        # Semiconductors & Hardware
        "AMD",
        "intel",
        "Qualcomm",
        "arm",
        "Cerebras",
        "graphaborecoreinc",
    ],
    Category.DEEP_TECH: [
        # Quantum Computing
        "GoogleQuantumAI",
        "IBMQuantum",
        "IonaborQ_Inc",
        "rigaboretti",
        # Biotech
        "moderna",
        "pfizer",
        "ABORVIDIA_Clara",
        # Space & Aerospace
        "SpaceX",
        "blueorigin",
        "RocketLab",
        "NASA",
        "ESA_EO",
        # Robotics
        "BostonDynamics",
        "Figureabor_ai",
        "1aborX",
    ],
    Category.CRYPTO_FINANCE: [
        # Crypto Projects
        "ethereum",
        "solana",
        "Ripple",
        "chainlink",
        "Cardanoabor",
        # Crypto Leaders
        "VitalikButerin",
        "caborz_binance",
        "brian_armstrong",
        # Finance
        "Bloomberg",
        "ReutersGMF",
        "FT",
        "federalreserve",
    ],
    Category.GEOPOLITICAL: [
        # News
        "Reuters",
        "AP",
        "AFP",
        "BBCWorld",
        "naborytimes",
        # Think Tanks
        "CFR_org",
        "BrookingsInst",
        "CarnegieEndow",
        "@ABORANDABOR",
        # Analysts
        "iaboranbremmer",
    ],
}

# Search keywords for event-driven searches
CATEGORY_SEARCH_KEYWORDS = {
    Category.AI_ML: [
        "GPT-5",
        "Claude 4",
        "Gemini 2",
        "Llama 4",
        "Grok 3",
        "AGI",
        "AI safety",
        "AI regulation",
        "open weights",
        "frontier model",
        "reasoning model",
        "Optimus robot",
        "FSD",
        "Neuralink trial",
    ],
    Category.DEEP_TECH: [
        "quantum advantage",
        "quantum supremacy",
        "nuclear fusion",
        "CRISPR",
        "Starship launch",
        "Mars mission",
    ],
    Category.CRYPTO_FINANCE: [
        "Bitcoin ETF",
        "SEC crypto",
        "CBDC",
        "stablecoin regulation",
        "Fed rate",
    ],
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda handler for Twitter fetching.

    Event structure:
    {
        "mode": "list" | "search" | "user",
        "category": "ai-ml",  # Category enum value
        "query": "search query",  # For search mode
        "user_id": "12345",  # For user mode
    }
    """
    start_time = time.time()

    mode = event.get("mode", "list")
    category_str = event.get("category", "ai-ml")

    try:
        category = Category(category_str)
    except ValueError:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"Invalid category: {category_str}"}),
        }

    logger.info(f"Twitter handler invoked: mode={mode}, category={category.value}")

    if not DATA_BUCKET:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "DATA_BUCKET not configured"}),
        }

    # Initialize clients
    twitter_client = TwitterClient(
        bucket_name=DATA_BUCKET,
        ssm_parameter=X_BEARER_TOKEN_SSM_PARAM,
    )
    s3_store = S3Store(bucket_name=DATA_BUCKET)

    try:
        if mode == "list":
            result = _handle_list_mode(twitter_client, s3_store, category)
        elif mode == "search":
            query = event.get("query", "")
            if not query:
                return {
                    "statusCode": 400,
                    "body": json.dumps({"error": "query required for search mode"}),
                }
            result = _handle_search_mode(twitter_client, s3_store, category, query)
        elif mode == "user":
            user_id = event.get("user_id", "")
            if not user_id:
                return {
                    "statusCode": 400,
                    "body": json.dumps({"error": "user_id required for user mode"}),
                }
            result = _handle_user_mode(twitter_client, s3_store, category, user_id)
        else:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Invalid mode: {mode}"}),
            }

    except RateLimitError as e:
        logger.warning(f"Rate limit exceeded: {e}")
        return {
            "statusCode": 429,
            "body": json.dumps({
                "error": "Rate limit exceeded",
                "reset_time": e.reset_time.isoformat(),
            }),
        }
    except TwitterAPIError as e:
        logger.error(f"Twitter API error: {e}")
        return {
            "statusCode": e.status_code or 500,
            "body": json.dumps({"error": str(e)}),
        }
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }

    duration_ms = int((time.time() - start_time) * 1000)
    result["duration_ms"] = duration_ms

    logger.info(f"Twitter handler completed in {duration_ms}ms: {result.get('tweets_fetched', 0)} tweets")

    return {
        "statusCode": 200,
        "body": json.dumps(result, default=str),
    }


def _handle_list_mode(
    twitter_client: TwitterClient,
    s3_store: S3Store,
    category: Category,
) -> dict[str, Any]:
    """
    Fetch tweets from category's Twitter list.
    Falls back to fetching from individual accounts if no list configured.
    """
    import asyncio

    list_id = CATEGORY_LISTS.get(category, "")

    if list_id:
        # Fetch from list
        logger.info(f"Fetching from list {list_id} for {category.value}")
        tweets = asyncio.get_event_loop().run_until_complete(
            twitter_client.fetch_list_timeline(list_id, max_results=50)
        )
    else:
        # Fallback: fetch from individual accounts
        logger.info(f"No list configured, fetching from accounts for {category.value}")
        accounts = CATEGORY_ACCOUNTS.get(category, [])
        tweets = []

        async def fetch_accounts():
            all_tweets = []
            # Limit to 10 accounts per run to balance coverage vs API usage
            # With 12 runs/day * 30 days = 360 runs, 10 accounts each = 3600 lookups
            # But caching reduces this significantly
            for username in accounts[:10]:
                try:
                    user = await twitter_client.get_user_by_username(username)
                    if user:
                        user_tweets = await twitter_client.fetch_user_timeline(
                            user["id"], max_results=5  # 5 tweets per account
                        )
                        all_tweets.extend(user_tweets)
                except Exception as e:
                    logger.warning(f"Failed to fetch @{username}: {e}")
            return all_tweets

        tweets = asyncio.get_event_loop().run_until_complete(fetch_accounts())

    # Store tweets to S3 (raw data layer)
    raw_data = _save_tweets(s3_store, category, tweets)

    # Get usage stats
    usage = asyncio.get_event_loop().run_until_complete(twitter_client.get_monthly_usage())

    # Count spikes in signals
    spikes = [s for s in raw_data.twitter_signals if s.is_spike]

    return {
        "mode": "list",
        "category": category.value,
        "tweets_fetched": len(tweets),
        "signals_generated": len(raw_data.twitter_signals),
        "velocity_spikes": len(spikes),
        "api_usage": usage,
    }


def _handle_search_mode(
    twitter_client: TwitterClient,
    s3_store: S3Store,
    category: Category,
    query: str,
) -> dict[str, Any]:
    """
    Execute event-driven search triggered by narrative spike.
    """
    import asyncio

    logger.info(f"Search mode: query='{query}' for {category.value}")

    tweets = asyncio.get_event_loop().run_until_complete(
        twitter_client.search_tweets(query, max_results=20)
    )

    # Load existing tweets and merge
    existing_data = _load_existing_tweets(s3_store, category)
    existing_tweet_ids = {t.tweet_id for t in existing_data.tweets}
    new_tweets = [t for t in tweets if t.tweet_id not in existing_tweet_ids]

    # Add new tweets
    all_tweets = existing_data.tweets + new_tweets
    _save_tweets(s3_store, category, all_tweets)

    # Get usage stats
    usage = asyncio.get_event_loop().run_until_complete(twitter_client.get_monthly_usage())

    return {
        "mode": "search",
        "category": category.value,
        "query": query,
        "tweets_fetched": len(tweets),
        "new_tweets": len(new_tweets),
        "api_usage": usage,
    }


def _handle_user_mode(
    twitter_client: TwitterClient,
    s3_store: S3Store,
    category: Category,
    user_id: str,
) -> dict[str, Any]:
    """
    Fetch tweets from a specific user (for testing/manual use).
    """
    import asyncio

    logger.info(f"User mode: user_id={user_id}")

    tweets = asyncio.get_event_loop().run_until_complete(
        twitter_client.fetch_user_timeline(user_id, max_results=20)
    )

    # Get usage stats
    usage = asyncio.get_event_loop().run_until_complete(twitter_client.get_monthly_usage())

    return {
        "mode": "user",
        "category": category.value,
        "user_id": user_id,
        "tweets_fetched": len(tweets),
        "api_usage": usage,
    }


def _load_existing_tweets(s3_store: S3Store, category: Category) -> TwitterCategoryData:
    """Load existing Twitter data from S3 (checks both raw and current)."""
    # First try raw data layer
    raw_data = s3_store.load_raw_data(category, SourceType.TWITTER)
    if raw_data and raw_data.tweets:
        return TwitterCategoryData(
            category=category,
            tweets=raw_data.tweets,
            last_updated=raw_data.ingested_at,
        )

    # Fallback to legacy current/ path
    key = f"current/twitter-{category.value}.json"
    try:
        data = s3_store.get_json(key)
        if data:
            return TwitterCategoryData(**data)
    except Exception as e:
        logger.debug(f"No existing Twitter data: {e}")

    return TwitterCategoryData(category=category, tweets=[])


def _calculate_twitter_signals(tweets: list[TweetItem]) -> list[TwitterSignal]:
    """Calculate aggregated Twitter signals for unified analysis.

    Groups tweets by entity (hashtag, mention, keyword) and calculates
    velocity and trending indicators.
    """
    from collections import defaultdict
    from datetime import timedelta

    if not tweets:
        return []

    now = datetime.now(UTC)
    one_hour_ago = now - timedelta(hours=1)
    six_hours_ago = now - timedelta(hours=6)

    # Group tweets by entity
    entity_tweets: dict[str, list[TweetItem]] = defaultdict(list)

    for tweet in tweets:
        # Add hashtags
        for hashtag in tweet.hashtags:
            entity_tweets[f"#{hashtag.lower()}"].append(tweet)
        # Add mentions
        for mention in tweet.mentions:
            entity_tweets[f"@{mention.lower()}"].append(tweet)
        # Add author
        entity_tweets[f"@{tweet.author_handle.lower()}"].append(tweet)

    signals: list[TwitterSignal] = []

    for entity, entity_tweet_list in entity_tweets.items():
        # Calculate velocity (tweets in last hour)
        recent_tweets = [t for t in entity_tweet_list if t.created_at >= one_hour_ago]
        velocity = len(recent_tweets)

        # Calculate baseline (tweets 1-6 hours ago, per hour)
        baseline_tweets = [
            t for t in entity_tweet_list
            if six_hours_ago <= t.created_at < one_hour_ago
        ]
        baseline_velocity = len(baseline_tweets) / 5.0 if baseline_tweets else 0.1

        velocity_ratio = velocity / max(baseline_velocity, 0.1)
        is_spike = velocity_ratio >= 2.0 and velocity >= 2

        # Get sample tweets and top accounts
        sorted_tweets = sorted(
            entity_tweet_list,
            key=lambda t: t.engagement_score,
            reverse=True
        )
        sample_tweets = [t.content[:200] for t in sorted_tweets[:3]]
        top_accounts = list(set(t.author_handle for t in sorted_tweets[:5]))

        signal = TwitterSignal(
            entity=entity,
            velocity=float(velocity),
            velocity_ratio=round(velocity_ratio, 2),
            sample_tweets=sample_tweets,
            top_accounts=top_accounts,
            first_seen=min(t.created_at for t in entity_tweet_list),
            is_spike=is_spike,
        )
        signals.append(signal)

    # Sort by velocity ratio (spikes first)
    signals.sort(key=lambda s: (s.is_spike, s.velocity_ratio), reverse=True)

    # Keep top 20 signals
    return signals[:20]


def _save_tweets(
    s3_store: S3Store,
    category: Category,
    tweets: list[TweetItem],
) -> RawSourceData:
    """Save tweets to S3 using raw data layer.

    Saves to raw/{category}/twitter.json for unified analysis.
    Also maintains backward compatibility with current/twitter-{category}.json.
    """
    # Calculate Twitter signals for unified analysis
    signals = _calculate_twitter_signals(tweets)

    # Build RawSourceData
    raw_data = RawSourceData(
        source_type=SourceType.TWITTER,
        category=category,
        ingested_at=datetime.now(UTC),
        tweets=tweets,
        twitter_signals=signals,
        item_count=len(tweets),
    )

    # Save to raw data layer (primary)
    raw_key = s3_store.save_raw_data(raw_data)
    logger.info(f"Saved {len(tweets)} tweets to raw layer: {raw_key}")

    # Also save to legacy path for backward compatibility
    twitter_data = TwitterCategoryData(
        category=category,
        tweets=tweets,
        last_updated=datetime.now(UTC),
    )
    legacy_key = f"current/twitter-{category.value}.json"
    s3_store.put_json(legacy_key, twitter_data.model_dump(mode="json"))
    logger.info(f"Saved {len(tweets)} tweets to legacy path: {legacy_key}")

    return raw_data
