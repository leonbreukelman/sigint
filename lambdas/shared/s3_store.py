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

from .models import (
    Category,
    CategoryData,
    DashboardState,
    NarrativePattern,
    NewsItem,
    RawSourceData,
    SourceType,
    UnifiedAnalysisResult,
)

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
    # Public JSON Operations (for generic key/value storage)
    # =========================================================================

    def get_json(self, key: str) -> dict[str, Any] | None:
        """Read JSON file from S3 by key.

        Public wrapper around _read_json for generic storage needs
        (e.g., Twitter data, cache files).
        """
        return self._read_json(key)

    def put_json(
        self, key: str, data: dict[str, Any], cache_control: str = "max-age=60"
    ) -> None:
        """Write JSON file to S3 by key.

        Public wrapper around _write_json for generic storage needs
        (e.g., Twitter data, cache files).
        """
        self._write_json(key, data, cache_control)

    # =========================================================================
    # Raw Data Layer Operations (Stage 1 of Unified Architecture)
    # =========================================================================

    def _raw_key(self, category: Category, source_type: SourceType) -> str:
        """Generate S3 key for raw data storage."""
        return f"raw/{category.value}/{source_type.value}.json"

    def save_raw_data(self, raw_data: RawSourceData) -> str:
        """Save raw ingested data to S3.

        Stores raw data from any source (RSS, Twitter, Polymarket, Ticker)
        in the raw/ prefix for later unified analysis.

        Args:
            raw_data: RawSourceData object with source-specific data

        Returns:
            S3 key where data was saved
        """
        key = self._raw_key(raw_data.category, raw_data.source_type)
        self._write_json(key, raw_data.model_dump(mode="json"), cache_control="max-age=120")
        logger.info(
            f"Saved raw {raw_data.source_type.value} data for {raw_data.category.value}: "
            f"{raw_data.item_count} items"
        )
        return key

    def load_raw_data(
        self, category: Category, source_type: SourceType
    ) -> RawSourceData | None:
        """Load raw ingested data from S3.

        Args:
            category: Category to load data for
            source_type: Type of source data to load

        Returns:
            RawSourceData if found, None otherwise
        """
        key = self._raw_key(category, source_type)
        data = self._read_json(key)
        if data:
            try:
                return RawSourceData(**data)
            except Exception as e:
                logger.error(f"Failed to parse raw data from {key}: {e}")
                return None
        return None

    def load_all_raw_data(self, category: Category) -> dict[SourceType, RawSourceData]:
        """Load all available raw data for a category.

        Args:
            category: Category to load data for

        Returns:
            Dict mapping SourceType to RawSourceData for available sources
        """
        result: dict[SourceType, RawSourceData] = {}
        for source_type in SourceType:
            raw_data = self.load_raw_data(category, source_type)
            if raw_data and raw_data.item_count > 0:
                result[source_type] = raw_data
                logger.debug(
                    f"Loaded {raw_data.item_count} {source_type.value} items for {category.value}"
                )
        logger.info(f"Loaded raw data from {len(result)} sources for {category.value}")
        return result

    def save_unified_analysis(self, result: UnifiedAnalysisResult) -> str:
        """Save unified analysis result to current/ for dashboard consumption.

        This replaces the old save_category_data for analyzed output.

        Args:
            result: UnifiedAnalysisResult from analyzer Lambda

        Returns:
            S3 key where data was saved
        """
        key = f"current/{result.category.value}.json"

        # Convert to CategoryData-compatible format for backward compatibility
        news_items = []
        for item in result.items:
            news_item = NewsItem(
                id=item.id,
                title=item.title,
                summary=item.summary,
                url=item.url,
                source=item.source,
                source_url=item.url,  # Use URL as source_url
                category=item.category,
                urgency=item.urgency,
                relevance_score=item.confidence,  # Use confidence as relevance
                published_at=item.published_at,
                fetched_at=item.analyzed_at,
                entities=item.entities,
                tags=[st.value for st in item.source_tags],  # Convert source tags to tags
                prediction_market=item.prediction_market,
            )
            news_items.append(news_item)

        category_data = CategoryData(
            category=result.category,
            items=news_items,
            last_updated=result.analyzed_at,
            agent_notes=result.agent_notes,
        )

        self._write_json(key, category_data.model_dump(mode="json"), cache_control="max-age=30")
        logger.info(
            f"Saved unified analysis for {result.category.value}: "
            f"{len(result.items)} items from {len(result.sources_used)} sources"
        )
        return key

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

    def get_archive_range(
        self, category: Category, days: int = 7
    ) -> list[NewsItem]:
        """Get archived items for the last N days.
        
        Args:
            category: The news category to fetch archives for
            days: Number of days to look back (default 7, max 30)
        
        Returns:
            List of NewsItem objects from the archive, sorted newest first.
            Missing archive files for specific days are handled gracefully.
        """
        # Clamp days to valid range
        days = max(1, min(days, 30))
        
        items = []
        for i in range(days):
            date = (datetime.now(UTC) - timedelta(days=i)).strftime("%Y-%m-%d")
            try:
                day_items = self.get_archive(category, date)
                items.extend(day_items)
            except Exception as e:
                # Log but continue - missing days are expected
                logger.debug(f"No archive for {category.value} on {date}: {e}")
        
        # Sort by published date (newest first)
        items.sort(
            key=lambda x: x.published_at or x.fetched_at or datetime.min.replace(tzinfo=UTC),
            reverse=True
        )
        
        logger.info(f"Archive range: fetched {len(items)} items for {category.value} over {days} days")
        return items

    def list_archive_dates(self) -> list[str]:
        """List all available archive dates.
        
        Returns:
            List of date strings (YYYY-MM-DD) that have archive data,
            sorted newest first.
        """
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix="archive/",
                Delimiter="/"
            )
            
            dates = []
            for prefix in response.get("CommonPrefixes", []):
                # Extract date from prefix like "archive/2026-01-09/"
                date_str = prefix["Prefix"].replace("archive/", "").rstrip("/")
                if date_str:
                    dates.append(date_str)
            
            # Sort newest first
            dates.sort(reverse=True)
            return dates
        except Exception as e:
            logger.error(f"Error listing archive dates: {e}")
            return []

    def update_archive_index(self) -> dict[str, Any]:
        """Update the archive index with available dates and item counts.
        
        Creates/updates archive/index.json with:
        - available_dates: List of dates with archive data
        - total_items_by_category: Count of items per category
        - last_updated: Timestamp of index update
        
        Returns:
            The index data that was written.
        """
        available_dates = self.list_archive_dates()
        
        # Count items per category across all dates
        category_counts: dict[str, int] = {cat.value: 0 for cat in Category}
        
        for date in available_dates[:30]:  # Limit to last 30 days for performance
            for category in Category:
                try:
                    items = self.get_archive(category, date)
                    category_counts[category.value] += len(items)
                except Exception:
                    pass  # Skip missing files
        
        index_data = {
            "available_dates": available_dates,
            "total_items_by_category": category_counts,
            "last_updated": datetime.now(UTC).isoformat(),
            "retention_days": 30,
        }
        
        self._write_json("archive/index.json", index_data, cache_control="max-age=3600")
        logger.info(f"Updated archive index: {len(available_dates)} dates, {sum(category_counts.values())} total items")
        return index_data

    def get_archive_index(self) -> dict[str, Any] | None:
        """Get the archive index.
        
        Returns:
            Archive index data or None if not found.
        """
        return self._read_json("archive/index.json")

    def cleanup_old_archives(self, retention_days: int = 30) -> dict[str, Any]:
        """Delete archives older than retention_days.
        
        Args:
            retention_days: Number of days to retain (default 30)
        
        Returns:
            Summary of cleanup operation.
        """
        cutoff_date = (datetime.now(UTC) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
        available_dates = self.list_archive_dates()
        
        deleted_dates = []
        deleted_count = 0
        errors = []
        
        for date in available_dates:
            if date < cutoff_date:
                try:
                    # List all objects in this date folder
                    prefix = f"archive/{date}/"
                    response = self.s3.list_objects_v2(
                        Bucket=self.bucket_name,
                        Prefix=prefix
                    )
                    
                    # Delete each object
                    for obj in response.get("Contents", []):
                        self.s3.delete_object(
                            Bucket=self.bucket_name,
                            Key=obj["Key"]
                        )
                        deleted_count += 1
                    
                    deleted_dates.append(date)
                    logger.info(f"Deleted archive for {date}")
                except Exception as e:
                    errors.append({"date": date, "error": str(e)})
                    logger.error(f"Error deleting archive for {date}: {e}")
        
        result = {
            "deleted_dates": deleted_dates,
            "deleted_files": deleted_count,
            "errors": errors,
            "cutoff_date": cutoff_date,
        }
        
        logger.info(f"Archive cleanup: deleted {len(deleted_dates)} dates, {deleted_count} files")
        return result

    def export_archive_json(self, category: Category, days: int = 7) -> str:
        """Export archive data as JSON string.
        
        Args:
            category: The category to export
            days: Number of days to include
        
        Returns:
            JSON string of archive data
        """
        items = self.get_archive_range(category, days)
        export_data = {
            "category": category.value,
            "days": days,
            "exported_at": datetime.now(UTC).isoformat(),
            "item_count": len(items),
            "items": [item.model_dump() for item in items],
        }
        return json.dumps(export_data, default=self._json_serializer, indent=2)

    def export_archive_csv(self, category: Category, days: int = 7) -> str:
        """Export archive data as CSV string.
        
        Args:
            category: The category to export
            days: Number of days to include
        
        Returns:
            CSV string of archive data
        """
        import csv
        from io import StringIO
        
        items = self.get_archive_range(category, days)
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "id", "title", "summary", "url", "source", "category",
            "urgency", "relevance_score", "published_at", "fetched_at"
        ])
        
        # Data rows
        for item in items:
            writer.writerow([
                item.id,
                item.title,
                item.summary[:200] if item.summary else "",  # Truncate summary
                item.url,
                item.source,
                item.category.value,
                item.urgency.value,
                item.relevance_score,
                item.published_at.isoformat() if item.published_at else "",
                item.fetched_at.isoformat() if item.fetched_at else "",
            ])
        
        return output.getvalue()

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
