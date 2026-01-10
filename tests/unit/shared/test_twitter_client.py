"""
Unit tests for Twitter client
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lambdas.shared.twitter_client import (
    RATE_LIMIT_CONFIG,
    RateLimitError,
    TwitterAPIError,
    TwitterClient,
)


@pytest.fixture
def mock_s3_client():
    """Mock boto3 S3 client"""
    with patch("boto3.client") as mock:
        s3_mock = MagicMock()
        mock.return_value = s3_mock
        yield s3_mock


@pytest.fixture
def twitter_client(mock_s3_client):
    """Create TwitterClient with mocked dependencies"""
    client = TwitterClient(
        bucket_name="test-bucket",
        bearer_token="test-bearer-token",
    )
    client._s3_client = mock_s3_client
    return client


class TestTwitterClientInit:
    """Test TwitterClient initialization"""

    def test_init_with_bearer_token(self):
        """Client initializes with explicit bearer token"""
        client = TwitterClient(
            bucket_name="test-bucket",
            bearer_token="test-token",
        )
        assert client.bucket_name == "test-bucket"
        assert client._bearer_token == "test-token"

    def test_init_without_bearer_token(self):
        """Client initializes without token, will fetch from SSM"""
        client = TwitterClient(bucket_name="test-bucket")
        assert client._bearer_token is None
        assert client._ssm_parameter == "/sigint/x-bearer-token"


class TestParseTweet:
    """Test tweet parsing logic"""

    def test_parse_tweet_full_data(self, twitter_client):
        """Parse tweet with all fields"""
        tweet_data = {
            "id": "123456789",
            "text": "Test tweet with #hashtag and @mention and $CASHTAG",
            "author_id": "user123",
            "created_at": "2026-01-09T10:00:00.000Z",
            "public_metrics": {
                "retweet_count": 10,
                "like_count": 50,
                "reply_count": 5,
                "quote_count": 2,
            },
            "entities": {
                "hashtags": [{"tag": "hashtag"}],
                "mentions": [{"username": "mention"}],
                "cashtags": [{"tag": "CASHTAG"}],
            },
        }
        users_map = {"user123": {"id": "user123", "username": "testuser"}}

        tweet = twitter_client._parse_tweet(tweet_data, users_map)

        assert tweet.tweet_id == "123456789"
        assert tweet.author_handle == "testuser"
        assert tweet.author_id == "user123"
        assert tweet.content == "Test tweet with #hashtag and @mention and $CASHTAG"
        assert tweet.hashtags == ["hashtag"]
        assert tweet.mentions == ["mention"]
        assert tweet.cashtags == ["CASHTAG"]
        assert tweet.retweet_count == 10
        assert tweet.like_count == 50
        assert tweet.reply_count == 5
        assert tweet.quote_count == 2

    def test_parse_tweet_minimal_data(self, twitter_client):
        """Parse tweet with minimal fields"""
        tweet_data = {
            "id": "123",
            "text": "Minimal tweet",
            "author_id": "user1",
        }
        users_map = {}

        tweet = twitter_client._parse_tweet(tweet_data, users_map)

        assert tweet.tweet_id == "123"
        assert tweet.author_handle == "unknown"
        assert tweet.content == "Minimal tweet"
        assert tweet.hashtags == []
        assert tweet.retweet_count == 0

    def test_engagement_score(self, twitter_client):
        """Test engagement score calculation"""
        tweet_data = {
            "id": "123",
            "text": "Test",
            "author_id": "user1",
            "public_metrics": {
                "retweet_count": 10,
                "like_count": 50,
                "reply_count": 5,
                "quote_count": 2,
            },
        }
        tweet = twitter_client._parse_tweet(tweet_data, {})

        assert tweet.engagement_score == 67  # 10 + 50 + 5 + 2


class TestCaching:
    """Test S3 caching logic"""

    def test_cache_key_generation(self, twitter_client):
        """Cache key follows expected pattern"""
        key = twitter_client._cache_key("list", "12345")
        assert key == "twitter/cache/list/12345.json"

    def test_usage_key_generation(self, twitter_client):
        """Usage key includes year-month"""
        key = twitter_client._usage_key()
        now = datetime.now(UTC)
        assert key == f"twitter/usage/{now.year}-{now.month:02d}.json"

    @pytest.mark.asyncio
    async def test_get_cached_hit(self, twitter_client, mock_s3_client):
        """Cache hit returns data"""
        cached_data = {
            "data": [{"id": "123"}],
            "_cached_at": datetime.now(UTC).isoformat(),
        }
        mock_s3_client.get_object.return_value = {
            "Body": MagicMock(read=lambda: json.dumps(cached_data).encode())
        }

        result = await twitter_client._get_cached("twitter/cache/test/key.json")

        assert result is not None
        assert result["data"] == [{"id": "123"}]

    @pytest.mark.asyncio
    async def test_get_cached_miss(self, twitter_client, mock_s3_client):
        """Cache miss returns None"""
        from botocore.exceptions import ClientError

        mock_s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}}, "GetObject"
        )

        result = await twitter_client._get_cached("twitter/cache/test/key.json")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_expired(self, twitter_client, mock_s3_client):
        """Expired cache returns None"""
        expired_time = (
            datetime.now(UTC) - timedelta(hours=RATE_LIMIT_CONFIG["cache_ttl_hours"] + 1)
        ).isoformat()
        cached_data = {
            "data": [{"id": "123"}],
            "_cached_at": expired_time,
        }
        mock_s3_client.get_object.return_value = {
            "Body": MagicMock(read=lambda: json.dumps(cached_data).encode())
        }

        result = await twitter_client._get_cached("twitter/cache/test/key.json")

        assert result is None


class TestRateLimiting:
    """Test rate limiting logic"""

    def test_update_rate_limits(self, twitter_client):
        """Rate limits extracted from headers"""
        headers = {
            "x-rate-limit-remaining": "10",
            "x-rate-limit-reset": "1736420400",
        }

        twitter_client._update_rate_limits(headers)

        assert twitter_client._rate_limit_remaining == 10
        assert twitter_client._rate_limit_reset is not None

    @pytest.mark.asyncio
    async def test_monthly_usage_tracking(self, twitter_client, mock_s3_client):
        """Monthly usage counter works"""
        from botocore.exceptions import ClientError

        # First call - no existing usage
        mock_s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}}, "GetObject"
        )

        count = await twitter_client._increment_usage()

        assert count == 1
        mock_s3_client.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_monthly_usage(self, twitter_client, mock_s3_client):
        """Get monthly usage stats"""
        usage_data = {"count": 100, "month": "2026-01"}
        mock_s3_client.get_object.return_value = {
            "Body": MagicMock(read=lambda: json.dumps(usage_data).encode())
        }

        result = await twitter_client.get_monthly_usage()

        assert result["count"] == 100
        assert result["limit"] == RATE_LIMIT_CONFIG["monthly_limit"]
        assert result["remaining"] == RATE_LIMIT_CONFIG["monthly_limit"] - 100


class TestRateLimitError:
    """Test RateLimitError exception"""

    def test_rate_limit_error_message(self):
        """Error includes reset time"""
        reset_time = datetime(2026, 1, 9, 12, 0, 0, tzinfo=UTC)
        error = RateLimitError(reset_time)

        assert "Rate limit exceeded" in str(error)
        assert "2026" in str(error)


class TestTwitterAPIError:
    """Test TwitterAPIError exception"""

    def test_api_error_message(self):
        """Error includes status code and message"""
        error = TwitterAPIError(401, "Unauthorized")

        assert "401" in str(error)
        assert "Unauthorized" in str(error)


class TestBuildUsersMap:
    """Test users map building"""

    def test_build_users_map(self, twitter_client):
        """Users map built from includes"""
        includes = {
            "users": [
                {"id": "user1", "username": "alice"},
                {"id": "user2", "username": "bob"},
            ]
        }

        users_map = twitter_client._build_users_map(includes)

        assert users_map["user1"]["username"] == "alice"
        assert users_map["user2"]["username"] == "bob"

    def test_build_users_map_empty(self, twitter_client):
        """Empty includes returns empty map"""
        users_map = twitter_client._build_users_map({})
        assert users_map == {}
