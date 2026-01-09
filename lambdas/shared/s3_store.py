"""
SIGINT S3 Store
Handles reading/writing data to S3
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError

from .models import Category, CategoryData, DashboardState, NarrativePattern, NewsItem

logger = logging.getLogger(__name__)


class S3Store:
    """S3-based data store for SIGINT"""

    def __init__(self, bucket_name: str, region: str = "us-east-1"):
        self.bucket_name = bucket_name
        self.s3 = boto3.client("s3", region_name=region)

    def _json_serializer(self, obj):
        """Custom JSON serializer for datetime objects"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    def _read_json(self, key: str) -> dict[str, Any] | None:
        """Read JSON file from S3"""
        try:
            response = self.s3.get_object(Bucket=self.bucket_name, Key=key)
            content = response["Body"].read().decode("utf-8")
            return json.loads(content)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.info(f"Key {key} not found in S3")
                return None
            logger.error(f"Error reading {key} from S3: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {key}: {e}")
            return None

    def _write_json(self, key: str, data: dict[str, Any], cache_control: str = "max-age=60"):
        """Write JSON file to S3"""
        try:
            content = json.dumps(data, default=self._json_serializer, indent=2)
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType="application/json",
                CacheControl=cache_control,
            )
            logger.info(f"Wrote {key} to S3")
        except Exception as e:
            logger.error(f"Error writing {key} to S3: {e}")
            raise

    # =========================================================================
    # Current Data Operations
    # =========================================================================

    def get_category_data(self, category: Category) -> CategoryData | None:
        """Get current data for a category"""
        key = f"current/{category.value}.json"
        data = self._read_json(key)
        if data:
            return CategoryData(**data)
        return None

    def save_category_data(self, category_data: CategoryData):
        """Save current data for a category"""
        key = f"current/{category_data.category.value}.json"
        self._write_json(key, category_data.model_dump(), cache_control="max-age=30")

    def get_all_current_data(self) -> dict[str, CategoryData]:
        """Get current data for all categories"""
        result = {}
        for category in Category:
            data = self.get_category_data(category)
            if data:
                result[category.value] = data
        return result

    # =========================================================================
    # Archive Operations
    # =========================================================================

    def archive_items(self, category: Category, items: list[NewsItem]):
        """Archive items to daily archive"""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        key = f"archive/{today}/{category.value}.json"

        # Read existing archive
        existing = self._read_json(key) or {"items": []}
        existing_ids = {item["id"] for item in existing["items"]}

        # Add new items (serialize datetime to ISO format for consistency)
        for item in items:
            if item.id not in existing_ids:
                item_data = item.model_dump()
                # Ensure datetime fields are serialized as strings
                for dt_field in ["published_at", "fetched_at"]:
                    if dt_field in item_data and item_data[dt_field] is not None:
                        if hasattr(item_data[dt_field], "isoformat"):
                            item_data[dt_field] = item_data[dt_field].isoformat()
                existing["items"].append(item_data)

        # Sort by published date (ensure string comparison)
        def get_sort_key(x):
            val = x.get("published_at") or x.get("fetched_at", "")
            if hasattr(val, "isoformat"):
                return val.isoformat()
            return str(val) if val else ""
        
        existing["items"].sort(key=get_sort_key, reverse=True)

        # Limit to last 100 items per category per day
        existing["items"] = existing["items"][:100]
        existing["last_updated"] = datetime.now(UTC).isoformat()

        self._write_json(key, existing, cache_control="max-age=300")

    def get_archive(self, category: Category, date: str) -> list[NewsItem]:
        """Get archived items for a category and date"""
        key = f"archive/{date}/{category.value}.json"
        data = self._read_json(key)
        if data and "items" in data:
            return [NewsItem(**item) for item in data["items"]]
        return []

    def get_24h_archive(self, category: Category) -> list[NewsItem]:
        """Get last 24 hours of archived items"""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")

        items = []
        items.extend(self.get_archive(category, today))
        items.extend(self.get_archive(category, yesterday))

        # Filter to last 24h
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        items = [item for item in items if item.fetched_at and item.fetched_at > cutoff]

        return items

    # =========================================================================
    # Narrative Patterns
    # =========================================================================

    def get_narrative_patterns(self) -> list[NarrativePattern]:
        """Get current narrative patterns"""
        key = "current/narratives.json"
        data = self._read_json(key)
        if data and "patterns" in data:
            return [NarrativePattern(**p) for p in data["patterns"]]
        return []

    def save_narrative_patterns(self, patterns: list[NarrativePattern]):
        """Save narrative patterns"""
        key = "current/narratives.json"
        data = {
            "patterns": [p.model_dump() for p in patterns],
            "last_updated": datetime.now(UTC).isoformat(),
        }
        self._write_json(key, data, cache_control="max-age=60")

    # =========================================================================
    # Dashboard State (for frontend)
    # =========================================================================

    def get_dashboard_state(self) -> DashboardState:
        """Get complete dashboard state for frontend"""
        categories = self.get_all_current_data()
        narratives = self.get_narrative_patterns()

        return DashboardState(
            categories=categories,
            narratives=narratives,
            last_updated=datetime.now(UTC),
            system_status="operational",
        )

    def save_dashboard_state(self, state: DashboardState):
        """Save complete dashboard state"""
        key = "current/dashboard.json"
        self._write_json(key, state.model_dump(), cache_control="max-age=30")

    # =========================================================================
    # Seen Items Tracking (for deduplication)
    # =========================================================================

    def get_seen_ids(self, category: Category, hours: int = 24) -> set:
        """Get IDs of items seen in the last N hours"""
        seen = set()

        # Check current
        current = self.get_category_data(category)
        if current:
            seen.update(item.id for item in current.items)

        # Check archive
        archive = self.get_24h_archive(category)
        seen.update(item.id for item in archive)

        return seen

    # =========================================================================
    # Feed Configuration
    # =========================================================================

    def get_feed_config(self) -> dict[str, Any]:
        """Get feed configuration"""
        key = "config/feeds.json"
        return self._read_json(key) or {}

    def save_feed_config(self, config: dict[str, Any]):
        """Save feed configuration"""
        key = "config/feeds.json"
        self._write_json(key, config, cache_control="max-age=3600")
