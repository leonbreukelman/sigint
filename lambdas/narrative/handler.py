"""
SIGINT Narrative Tracker Lambda
Detects cross-source patterns and emerging narratives
Integrates Twitter signals via correlation engine
"""

import hashlib
import json
import logging
import os
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

sys.path.insert(0, "/opt/python")

from shared.correlation_engine import CorrelationEngine
from shared.llm_client import LLMClient
from shared.models import (
    Category,
    CategoryData,
    CorrelatedNarrative,
    NarrativePattern,
    NewsItem,
    TweetItem,
    TwitterCategoryData,
)
from shared.s3_store import S3Store

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class NarrativeAnalyzer:
    """Analyzes items across categories for patterns"""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def extract_entities(self, items: list[NewsItem]) -> Counter:
        """Count entity mentions across items"""
        entity_counts = Counter()
        for item in items:
            for entity in item.entities:
                entity_counts[entity.lower()] += 1
        return entity_counts

    def extract_tags(self, items: list[NewsItem]) -> Counter:
        """Count tag occurrences across items"""
        tag_counts = Counter()
        for item in items:
            for tag in item.tags:
                tag_counts[tag.lower()] += 1
        return tag_counts

    def find_velocity_spikes(
        self, current_items: list[NewsItem], archive_items: list[NewsItem]
    ) -> list[dict[str, Any]]:
        """Find topics with unusual velocity"""
        # Count entities in current vs archive
        current_entities = self.extract_entities(current_items)
        archive_entities = self.extract_entities(archive_items)

        spikes = []
        for entity, count in current_entities.items():
            archive_count = archive_entities.get(entity, 0)
            # If entity appears 3+ times now but barely in archive
            if count >= 3 and (archive_count == 0 or count / max(archive_count, 1) > 2):
                spikes.append(
                    {
                        "entity": entity,
                        "current_count": count,
                        "archive_count": archive_count,
                        "velocity_ratio": count / max(archive_count, 1),
                    }
                )

        return sorted(spikes, key=lambda x: x["velocity_ratio"], reverse=True)[:5]

    def find_cross_category_topics(
        self, items_by_category: dict[str, list[NewsItem]]
    ) -> list[dict[str, Any]]:
        """Find topics appearing in multiple categories"""
        # Entity -> list of categories
        entity_categories: dict[str, set] = {}

        for cat, items in items_by_category.items():
            for item in items:
                for entity in item.entities:
                    entity_lower = entity.lower()
                    if entity_lower not in entity_categories:
                        entity_categories[entity_lower] = set()
                    entity_categories[entity_lower].add(cat)

        # Find entities in 2+ categories
        cross_topics = []
        for entity, categories in entity_categories.items():
            if len(categories) >= 2:
                cross_topics.append(
                    {
                        "entity": entity,
                        "categories": list(categories),
                        "category_count": len(categories),
                    }
                )

        return sorted(cross_topics, key=lambda x: x["category_count"], reverse=True)[:5]


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for narrative tracker"""
    start_time = time.time()
    logger.info("Starting narrative tracker")

    bucket_name = os.environ.get("DATA_BUCKET", "sigint-data")
    s3_store = S3Store(bucket_name)
    llm_client = LLMClient()
    analyzer = NarrativeAnalyzer(llm_client)

    try:
        # Get all current category data
        all_data = s3_store.get_all_current_data()

        # Collect all current items
        current_items: list[NewsItem] = []
        items_by_category: dict[str, list[NewsItem]] = {}

        for cat_name, cat_data in all_data.items():
            items_by_category[cat_name] = cat_data.items
            current_items.extend(cat_data.items)

        logger.info(
            f"Analyzing {len(current_items)} current items across {len(all_data)} categories"
        )

        # Get archive for velocity comparison
        archive_items: list[NewsItem] = []
        for category in Category:
            if category not in [Category.BREAKING, Category.NARRATIVE]:
                archive = s3_store.get_24h_archive(category)
                archive_items.extend(archive)

        # Find velocity spikes
        velocity_spikes = analyzer.find_velocity_spikes(current_items, archive_items)
        logger.info(f"Found {len(velocity_spikes)} velocity spikes")

        # Find cross-category topics
        cross_topics = analyzer.find_cross_category_topics(items_by_category)
        logger.info(f"Found {len(cross_topics)} cross-category topics")

        # === Twitter Correlation Analysis ===
        twitter_correlations: list[CorrelatedNarrative] = []
        correlation_engine = CorrelationEngine()

        # Load Twitter data for AI/ML category (pilot)
        twitter_data = _load_twitter_data(s3_store, Category.AI_ML)
        if twitter_data and twitter_data.tweets:
            logger.info(f"Loaded {len(twitter_data.tweets)} tweets for correlation")

            # Get AI/ML news items for correlation
            aiml_items = items_by_category.get("ai-ml", [])

            # Run correlation analysis
            twitter_correlations = correlation_engine.detect_correlations(
                twitter_data.tweets, aiml_items, Category.AI_ML
            )
            logger.info(f"Found {len(twitter_correlations)} Twitter correlations")

            # Detect divergent signals (Twitter activity not in news)
            divergent = correlation_engine.get_divergent_signals(
                twitter_data.tweets, aiml_items
            )
            if divergent:
                logger.info(f"Found {len(divergent)} divergent Twitter signals (potential breaking)")

        # Use LLM to synthesize patterns
        patterns = llm_client.detect_narratives(items_by_category)

        # Add velocity-based patterns
        for spike in velocity_spikes[:2]:
            pattern_id = hashlib.sha256(f"velocity:{spike['entity']}".encode()).hexdigest()[:12]
            patterns.append(
                NarrativePattern(
                    id=pattern_id,
                    title=f"Rising: {spike['entity'].title()}",
                    description=f"'{spike['entity']}' mentions spiking ({spike['current_count']} current vs {spike['archive_count']} in archive)",
                    sources=["velocity_analysis"],
                    item_ids=[],
                    strength=min(spike["velocity_ratio"] / 5, 1.0),  # Cap at 1.0
                    first_seen=datetime.now(UTC),
                    last_seen=datetime.now(UTC),
                )
            )

        # Add cross-category patterns
        for topic in cross_topics[:2]:
            pattern_id = hashlib.sha256(f"cross:{topic['entity']}".encode()).hexdigest()[:12]
            patterns.append(
                NarrativePattern(
                    id=pattern_id,
                    title=f"Cross-Signal: {topic['entity'].title()}",
                    description=f"'{topic['entity']}' appearing across {topic['category_count']} categories: {', '.join(topic['categories'])}",
                    sources=topic["categories"],
                    item_ids=[],
                    strength=min(topic["category_count"] / 4, 1.0),
                    first_seen=datetime.now(UTC),
                    last_seen=datetime.now(UTC),
                )
            )

        # Add Twitter correlation patterns
        for corr in twitter_correlations[:3]:
            pattern_id = hashlib.sha256(f"twitter:{corr.correlation_id}".encode()).hexdigest()[:12]

            # Format lead/lag indicator
            lead_indicator = ""
            if corr.lead_lag_hours is not None:
                if corr.lead_lag_hours > 0:
                    lead_indicator = f" 📡 Twitter led by {abs(corr.lead_lag_hours):.1f}h"
                else:
                    lead_indicator = f" 📰 News led by {abs(corr.lead_lag_hours):.1f}h"

            patterns.append(
                NarrativePattern(
                    id=pattern_id,
                    title=f"🐦 {corr.title}",
                    description=f"{corr.evidence_summary}{lead_indicator}",
                    sources=["Twitter", "AI/ML News"],
                    item_ids=corr.news_article_ids[:3],
                    strength=corr.confidence_score,
                    first_seen=corr.tweet_spike_time or datetime.now(UTC),
                    last_seen=datetime.now(UTC),
                )
            )

        # Merge with existing patterns
        existing = s3_store.get_narrative_patterns()
        existing_ids = {p.id for p in existing}

        for pattern in patterns:
            if pattern.id in existing_ids:
                # Update last_seen for existing pattern
                for ep in existing:
                    if ep.id == pattern.id:
                        ep.last_seen = datetime.now(UTC)
                        break
            else:
                existing.append(pattern)

        # Prune old patterns (not seen in 6 hours)
        cutoff = datetime.now(UTC) - timedelta(hours=6)
        existing = [p for p in existing if p.last_seen > cutoff]

        # Keep top 10 by strength
        existing.sort(key=lambda x: x.strength, reverse=True)
        existing = existing[:10]

        # Save patterns
        s3_store.save_narrative_patterns(existing)

        # Create narrative category data with top items from patterns
        narrative_items = []
        for pattern in existing[:5]:
            # Build extended summary with implications if available
            summary_parts = [pattern.description]
            if pattern.paragraph:
                summary_parts.append(pattern.paragraph)
            if pattern.implications:
                summary_parts.append("Key implications: " + "; ".join(pattern.implications[:3]))

            extended_summary = " | ".join(summary_parts)

            # Create pseudo-item for each pattern
            narrative_item = NewsItem(
                id=pattern.id,
                title=pattern.title,
                summary=extended_summary,
                url="",  # No direct URL
                source="SIGINT Analysis",
                source_url="",
                category=Category.NARRATIVE,
                relevance_score=pattern.strength,
                entities=pattern.related_entities if pattern.related_entities else [],
                tags=pattern.sources,
            )
            narrative_items.append(narrative_item)

        narrative_data = CategoryData(
            category=Category.NARRATIVE,
            items=narrative_items,
            last_updated=datetime.now(UTC),
            agent_notes=f"Tracking {len(existing)} active narratives",
        )
        s3_store.save_category_data(narrative_data)

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(f"Narrative tracker completed in {duration_ms}ms")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "success": True,
                    "patterns_detected": len(patterns),
                    "total_patterns": len(existing),
                    "velocity_spikes": len(velocity_spikes),
                    "cross_topics": len(cross_topics),
                    "twitter_correlations": len(twitter_correlations),
                    "duration_ms": duration_ms,
                }
            ),
        }

    except Exception as e:
        logger.error(f"Narrative tracker error: {e}", exc_info=True)
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def _load_twitter_data(s3_store: S3Store, category: Category) -> TwitterCategoryData | None:
    """Load Twitter data for a category from S3"""
    key = f"current/twitter-{category.value}.json"
    try:
        data = s3_store.get_json(key)
        if data:
            return TwitterCategoryData(**data)
    except Exception as e:
        logger.debug(f"No Twitter data for {category.value}: {e}")
    return None


if __name__ == "__main__":
    result = handler({}, None)
    print(json.dumps(json.loads(result["body"]), indent=2))
