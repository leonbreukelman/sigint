"""
Tests for shared/s3_store.py
"""

import json
from datetime import UTC, datetime

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def s3_store_with_bucket():
    """Create S3Store with mocked bucket."""
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="test-sigint-data")

        from shared.s3_store import S3Store

        store = S3Store(bucket_name="test-sigint-data", region="us-east-1")
        yield store, client


class TestS3StoreBasics:
    """Basic S3Store tests."""

    def test_init(self):
        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")

            from shared.s3_store import S3Store

            store = S3Store(bucket_name="test-bucket", region="us-east-1")

            assert store.bucket_name == "test-bucket"

    def test_json_serializer_datetime(self):
        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")

            from shared.s3_store import S3Store

            store = S3Store(bucket_name="test-bucket")

            dt = datetime(2026, 1, 8, 12, 0, 0, tzinfo=UTC)
            result = store._json_serializer(dt)

            assert result == "2026-01-08T12:00:00+00:00"

    def test_json_serializer_unsupported_type(self):
        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")

            from shared.s3_store import S3Store

            store = S3Store(bucket_name="test-bucket")

            with pytest.raises(TypeError):
                store._json_serializer(object())


class TestS3StoreReadWrite:
    """Tests for S3 read/write operations."""

    def test_write_and_read_json(self, s3_store_with_bucket):
        store, _ = s3_store_with_bucket

        test_data = {"key": "value", "number": 42}
        store._write_json("test/data.json", test_data)

        result = store._read_json("test/data.json")

        assert result == test_data

    def test_read_nonexistent_key(self, s3_store_with_bucket):
        store, _ = s3_store_with_bucket

        result = store._read_json("nonexistent/file.json")

        assert result is None

    def test_read_invalid_json(self, s3_store_with_bucket):
        store, client = s3_store_with_bucket

        # Write invalid JSON directly
        client.put_object(Bucket="test-sigint-data", Key="invalid.json", Body=b"not valid json {")

        result = store._read_json("invalid.json")

        assert result is None


class TestS3StoreCategoryOperations:
    """Tests for category data operations."""

    def test_save_and_get_category_data(self, s3_store_with_bucket, sample_category_data):
        store, _ = s3_store_with_bucket

        store.save_category_data(sample_category_data)

        from shared.models import Category

        result = store.get_category_data(Category.AI_ML)

        assert result is not None
        assert result.category == sample_category_data.category
        assert len(result.items) == len(sample_category_data.items)

    def test_get_category_data_not_found(self, s3_store_with_bucket):
        store, _ = s3_store_with_bucket

        from shared.models import Category

        result = store.get_category_data(Category.GEOPOLITICAL)

        assert result is None

    def test_get_all_current_data(self, s3_store_with_bucket, sample_news_item):
        store, _ = s3_store_with_bucket

        from shared.models import Category, CategoryData

        # Save data for multiple categories
        for cat in [Category.AI_ML, Category.GEOPOLITICAL]:
            data = CategoryData(
                category=cat,
                items=[sample_news_item.model_copy(update={"category": cat})],
            )
            store.save_category_data(data)

        result = store.get_all_current_data()

        assert len(result) >= 2
        assert "ai-ml" in result
        assert "geopolitical" in result


class TestS3StoreArchive:
    """Tests for archive operations."""

    def test_archive_items(self, s3_store_with_bucket, sample_news_item):
        store, client = s3_store_with_bucket

        from shared.models import Category

        store.archive_items(Category.AI_ML, [sample_news_item])

        # Verify archive was created
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        key = f"archive/{today}/ai-ml.json"

        response = client.get_object(Bucket="test-sigint-data", Key=key)
        data = json.loads(response["Body"].read())

        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == sample_news_item.id

    def test_archive_deduplication(self, s3_store_with_bucket, sample_news_item):
        store, _ = s3_store_with_bucket

        from shared.models import Category

        # Archive same item twice
        store.archive_items(Category.AI_ML, [sample_news_item])
        store.archive_items(Category.AI_ML, [sample_news_item])

        # Should still only have one item
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        result = store.get_archive(Category.AI_ML, today)

        assert len(result) == 1

    def test_get_24h_archive(self, s3_store_with_bucket, sample_news_item):
        store, _ = s3_store_with_bucket

        from shared.models import Category

        store.archive_items(Category.AI_ML, [sample_news_item])

        result = store.get_24h_archive(Category.AI_ML)

        # Should find the item we just archived
        assert len(result) >= 1


class TestS3StoreNarratives:
    """Tests for narrative pattern operations."""

    def test_save_and_get_narrative_patterns(self, s3_store_with_bucket):
        store, _ = s3_store_with_bucket

        from shared.models import NarrativePattern

        now = datetime.now(UTC)
        patterns = [
            NarrativePattern(
                id="p1",
                title="Pattern 1",
                description="Test pattern",
                sources=["source1"],
                item_ids=[],
                strength=0.8,
                first_seen=now,
                last_seen=now,
            )
        ]

        store.save_narrative_patterns(patterns)
        result = store.get_narrative_patterns()

        assert len(result) == 1
        assert result[0].title == "Pattern 1"

    def test_get_narrative_patterns_empty(self, s3_store_with_bucket):
        store, _ = s3_store_with_bucket

        result = store.get_narrative_patterns()

        assert result == []


class TestS3StoreSeenIds:
    """Tests for deduplication tracking."""

    def test_get_seen_ids(self, s3_store_with_bucket, sample_category_data):
        store, _ = s3_store_with_bucket

        from shared.models import Category

        store.save_category_data(sample_category_data)

        seen = store.get_seen_ids(Category.AI_ML)

        assert len(seen) > 0
        assert sample_category_data.items[0].id in seen


class TestS3StoreDashboard:
    """Tests for dashboard state operations."""

    def test_get_dashboard_state(self, s3_store_with_bucket, sample_category_data):
        store, _ = s3_store_with_bucket

        store.save_category_data(sample_category_data)

        result = store.get_dashboard_state()

        assert result is not None
        assert result.system_status == "operational"
        assert "ai-ml" in result.categories

    def test_save_dashboard_state(self, s3_store_with_bucket, sample_category_data):
        store, client = s3_store_with_bucket

        from shared.models import DashboardState

        now = datetime.now(UTC)
        state = DashboardState(
            categories={"ai-ml": sample_category_data},
            narratives=[],
            last_updated=now,
        )

        store.save_dashboard_state(state)

        # Verify it was saved
        response = client.get_object(Bucket="test-sigint-data", Key="current/dashboard.json")
        data = json.loads(response["Body"].read())

        assert "categories" in data
        assert "ai-ml" in data["categories"]


class TestS3StoreArchiveEnhancements:
    """Tests for archive index, cleanup, and export methods."""

    def test_update_archive_index(self, s3_store_with_bucket, sample_category_data):
        store, client = s3_store_with_bucket

        # Create some archive data first
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        store.archive_items(sample_category_data.category, sample_category_data.items)

        # Update index
        result = store.update_archive_index()

        assert "available_dates" in result
        assert "total_items_by_category" in result
        assert "last_updated" in result
        assert "retention_days" in result
        assert result["retention_days"] == 30

    def test_get_archive_index(self, s3_store_with_bucket, sample_category_data):
        store, _ = s3_store_with_bucket

        # Create archive and index
        store.archive_items(sample_category_data.category, sample_category_data.items)
        store.update_archive_index()

        # Get the index
        result = store.get_archive_index()

        assert result is not None
        assert "available_dates" in result
        assert "total_items_by_category" in result

    def test_get_archive_index_not_found(self, s3_store_with_bucket):
        store, _ = s3_store_with_bucket

        result = store.get_archive_index()

        assert result is None

    def test_cleanup_old_archives_no_old_data(self, s3_store_with_bucket, sample_category_data):
        store, _ = s3_store_with_bucket

        # Create archive for today (not old)
        store.archive_items(sample_category_data.category, sample_category_data.items)

        # Cleanup with 30 day retention - should not delete today's data
        result = store.cleanup_old_archives(retention_days=30)

        assert "deleted_dates" in result
        assert len(result["deleted_dates"]) == 0
        assert result["deleted_files"] == 0

    def test_export_archive_json(self, s3_store_with_bucket, sample_category_data):
        store, _ = s3_store_with_bucket
        from shared.models import Category

        # Create archive data
        store.archive_items(sample_category_data.category, sample_category_data.items)

        # Export
        result = store.export_archive_json(Category.AI_ML, days=1)

        assert isinstance(result, str)
        data = json.loads(result)
        assert data["category"] == "ai-ml"
        assert "items" in data
        assert "item_count" in data
        assert "exported_at" in data

    def test_export_archive_csv(self, s3_store_with_bucket, sample_category_data):
        store, _ = s3_store_with_bucket
        from shared.models import Category

        # Create archive data
        store.archive_items(sample_category_data.category, sample_category_data.items)

        # Export
        result = store.export_archive_csv(Category.AI_ML, days=1)

        assert isinstance(result, str)
        lines = result.strip().split("\n")
        assert len(lines) >= 2  # Header + at least one data row
        
        # Check header
        header = lines[0]
        assert "id" in header
        assert "title" in header
        assert "source" in header
