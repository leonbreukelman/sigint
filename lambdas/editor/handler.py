"""
SIGINT Editor Agent Lambda
Synthesizes across categories, identifies breaking news, updates dashboard
"""

import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from typing import Any

sys.path.insert(0, "/opt/python")

from shared.llm_client import LLMClient
from shared.models import Category, CategoryData, DashboardState, NewsItem, Urgency
from shared.s3_store import S3Store

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for editor agent"""
    start_time = time.time()
    logger.info("Starting editor agent")

    bucket_name = os.environ.get("DATA_BUCKET", "sigint-data")
    s3_store = S3Store(bucket_name)
    llm_client = LLMClient()

    try:
        # Get all current category data
        all_data = s3_store.get_all_current_data()
        logger.info(f"Loaded data from {len(all_data)} categories")

        # Collect all items with high urgency as breaking candidates
        breaking_candidates: list[NewsItem] = []
        all_items_by_category: dict[str, list[NewsItem]] = {}

        for cat_name, cat_data in all_data.items():
            all_items_by_category[cat_name] = cat_data.items

            for item in cat_data.items:
                # Items already marked high urgency or breaking
                if item.urgency in [Urgency.BREAKING, Urgency.HIGH] or item.relevance_score >= 0.9:
                    breaking_candidates.append(item)

        # Evaluate breaking candidates with LLM
        breaking_items: list[NewsItem] = []
        for item in breaking_candidates:
            if llm_client.evaluate_breaking(item):
                item.urgency = Urgency.BREAKING
                breaking_items.append(item)

        # Limit to top 3 breaking items
        breaking_items = breaking_items[:3]
        logger.info(f"Identified {len(breaking_items)} breaking items")

        # Create breaking category data
        if breaking_items:
            breaking_data = CategoryData(
                category=Category.BREAKING,
                items=breaking_items,
                last_updated=datetime.now(UTC),
                agent_notes="Editor-selected breaking news",
            )
            s3_store.save_category_data(breaking_data)

        # Detect narrative patterns
        narratives = llm_client.detect_narratives(all_items_by_category)
        if narratives:
            # Merge with existing patterns
            existing = s3_store.get_narrative_patterns()
            existing_titles = {p.title.lower() for p in existing}

            for new_pattern in narratives:
                if new_pattern.title.lower() not in existing_titles:
                    existing.append(new_pattern)

            # Keep only recent patterns (last 5)
            existing = existing[-5:]
            s3_store.save_narrative_patterns(existing)

        # Generate complete dashboard state
        dashboard_state = DashboardState(
            categories=dict(all_data.items()),
            narratives=s3_store.get_narrative_patterns(),
            last_updated=datetime.now(UTC),
            system_status="operational",
        )
        s3_store.save_dashboard_state(dashboard_state)

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(f"Editor completed in {duration_ms}ms")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "success": True,
                    "breaking_count": len(breaking_items),
                    "narrative_count": len(narratives),
                    "duration_ms": duration_ms,
                }
            ),
        }

    except Exception as e:
        logger.error(f"Editor error: {e}", exc_info=True)
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


if __name__ == "__main__":
    result = handler({}, None)
    print(json.dumps(json.loads(result["body"]), indent=2))
