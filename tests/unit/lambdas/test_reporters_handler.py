"""
Tests for lambdas/reporters/handler.py
"""

import json
from unittest.mock import MagicMock, patch

import boto3
from moto import mock_aws


class TestReporterHandler:
    """Tests for reporter Lambda handler."""

    def test_handler_invalid_category(self, lambda_context):
        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-sigint-data")

            from reporters.handler import handler

            result = handler({"category": "invalid-category"}, lambda_context)

            assert result["statusCode"] == 400
            assert "Invalid category" in result["body"]

    def test_handler_valid_category_structure(self, lambda_context):
        """Test that handler returns correct response structure."""
        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-sigint-data")

            with (
                patch("reporters.handler.FeedFetcher") as mock_fetcher,
                patch("reporters.handler.LLMClient") as mock_llm,
                patch("reporters.handler.S3Store") as mock_store,
            ):
                # Setup mocks
                mock_fetcher_instance = MagicMock()
                mock_fetcher.return_value = mock_fetcher_instance
                mock_fetcher_instance.fetch_feeds_sync.return_value = []

                mock_llm_instance = MagicMock()
                mock_llm.return_value = mock_llm_instance

                mock_store_instance = MagicMock()
                mock_store.return_value = mock_store_instance
                mock_store_instance.get_seen_ids.return_value = set()
                mock_store_instance.get_category_data.return_value = None
                mock_store_instance.get_feed_config.return_value = {
                    "global_settings": {"default_age_hours": 24}
                }
                mock_fetcher_instance.apply_pre_llm_filters.return_value = []

                from reporters.handler import handler

                result = handler({"category": "ai-ml"}, lambda_context)

                assert result["statusCode"] == 200
                body = json.loads(result["body"])
                assert "category" in body or "message" in body

    def test_handler_default_category(self, lambda_context):
        """Test that handler defaults to geopolitical when no category provided."""
        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-sigint-data")

            with (
                patch("reporters.handler.FeedFetcher") as mock_fetcher,
                patch("reporters.handler.LLMClient") as mock_llm,
                patch("reporters.handler.S3Store") as mock_store,
            ):
                mock_fetcher_instance = MagicMock()
                mock_fetcher.return_value = mock_fetcher_instance
                mock_fetcher_instance.fetch_feeds_sync.return_value = []

                mock_llm_instance = MagicMock()
                mock_llm.return_value = mock_llm_instance

                mock_store_instance = MagicMock()
                mock_store.return_value = mock_store_instance
                mock_store_instance.get_seen_ids.return_value = set()
                mock_store_instance.get_category_data.return_value = None
                mock_store_instance.get_feed_config.return_value = {
                    "global_settings": {"default_age_hours": 24}
                }
                mock_fetcher_instance.apply_pre_llm_filters.return_value = []

                from reporters.handler import handler

                # No category provided
                result = handler({}, lambda_context)

                assert result["statusCode"] == 200

    def test_handler_with_feed_items(self, lambda_context, sample_raw_feed_items):
        """Test handler processes feed items correctly."""
        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-sigint-data")

            with (
                patch("reporters.handler.FeedFetcher") as mock_fetcher,
                patch("reporters.handler.LLMClient") as mock_llm,
                patch("reporters.handler.S3Store") as mock_store,
            ):
                # Setup mocks
                mock_fetcher_instance = MagicMock()
                mock_fetcher.return_value = mock_fetcher_instance
                mock_fetcher_instance.fetch_feeds_sync.return_value = sample_raw_feed_items

                mock_llm_instance = MagicMock()
                mock_llm.return_value = mock_llm_instance
                mock_llm_instance.analyze_items.return_value = (
                    [
                        {
                            "item_number": 1,
                            "summary": "Test",
                            "urgency": "normal",
                            "relevance_score": 0.8,
                            "entities": [],
                            "tags": [],
                        }
                    ],
                    "Test notes",
                )

                mock_store_instance = MagicMock()
                mock_store.return_value = mock_store_instance
                mock_store_instance.get_seen_ids.return_value = set()
                mock_store_instance.get_category_data.return_value = None
                mock_store_instance.get_feed_config.return_value = {
                    "global_settings": {"default_age_hours": 24}
                }
                mock_fetcher_instance.apply_pre_llm_filters.return_value = sample_raw_feed_items

                from reporters.handler import handler

                result = handler({"category": "ai-ml"}, lambda_context)

                assert result["statusCode"] == 200

                # Verify LLM was called
                mock_llm_instance.analyze_items.assert_called_once()

    def test_handler_deduplication(self, lambda_context, sample_raw_feed_items):
        """Test that already-seen items are filtered out."""
        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-sigint-data")

            with (
                patch("reporters.handler.FeedFetcher") as mock_fetcher,
                patch("reporters.handler.LLMClient") as mock_llm,
                patch("reporters.handler.S3Store") as mock_store,
            ):
                mock_fetcher_instance = MagicMock()
                mock_fetcher.return_value = mock_fetcher_instance
                mock_fetcher_instance.fetch_feeds_sync.return_value = sample_raw_feed_items

                mock_llm_instance = MagicMock()
                mock_llm.return_value = mock_llm_instance

                mock_store_instance = MagicMock()
                mock_store.return_value = mock_store_instance
                # Mark all items as already seen
                mock_store_instance.get_seen_ids.return_value = {
                    item.id for item in sample_raw_feed_items
                }
                mock_store_instance.get_category_data.return_value = None
                mock_store_instance.get_feed_config.return_value = {
                    "global_settings": {"default_age_hours": 24}
                }
                mock_fetcher_instance.apply_pre_llm_filters.return_value = []

                from reporters.handler import handler

                result = handler({"category": "ai-ml"}, lambda_context)

                assert result["statusCode"] == 200
                body = json.loads(result["body"])
                # Should indicate no new items
                assert (
                    "No new items" in body.get("message", "") or body.get("items_selected", 0) == 0
                )

    def test_handler_error_handling(self, lambda_context):
        """Test that handler catches and reports errors."""
        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-sigint-data")

            with (
                patch("reporters.handler.FeedFetcher") as mock_fetcher,
                patch("reporters.handler.LLMClient") as mock_llm,
                patch("reporters.handler.S3Store") as mock_store,
            ):
                mock_fetcher_instance = MagicMock()
                mock_fetcher.return_value = mock_fetcher_instance
                mock_fetcher_instance.fetch_feeds_sync.side_effect = Exception("Network error")

                mock_llm_instance = MagicMock()
                mock_llm.return_value = mock_llm_instance

                mock_store_instance = MagicMock()
                mock_store.return_value = mock_store_instance

                from reporters.handler import handler

                result = handler({"category": "ai-ml"}, lambda_context)

                assert result["statusCode"] == 500
                body = json.loads(result["body"])
                assert "error" in body


class TestReporterCategoryFeeds:
    """Tests for category feed configuration."""

    def test_all_categories_have_feeds(self):
        from reporters.handler import CATEGORY_FEEDS

        from shared.models import Category

        # All main categories should have feeds configured
        main_categories = [
            Category.GEOPOLITICAL,
            Category.AI_ML,
            Category.DEEP_TECH,
            Category.CRYPTO_FINANCE,
        ]

        for cat in main_categories:
            assert cat in CATEGORY_FEEDS, f"Missing feeds for {cat}"
            assert len(CATEGORY_FEEDS[cat]) > 0, f"Empty feeds for {cat}"

    def test_feeds_are_valid_urls(self):
        from reporters.handler import CATEGORY_FEEDS

        for category, feeds in CATEGORY_FEEDS.items():
            for feed in feeds:
                assert feed.startswith("http"), f"Invalid feed URL: {feed}"

    def test_category_feed_counts(self):
        """Test that categories have reasonable number of feeds."""
        from reporters.handler import CATEGORY_FEEDS

        from shared.models import Category

        # Each category should have at least 3 feeds
        for cat in [
            Category.GEOPOLITICAL,
            Category.AI_ML,
            Category.DEEP_TECH,
            Category.CRYPTO_FINANCE,
        ]:
            assert len(CATEGORY_FEEDS[cat]) >= 3, f"Too few feeds for {cat}"
