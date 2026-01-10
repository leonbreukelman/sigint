"""
Twitter/X API v2 Client for SIGINT

Handles authentication, rate limiting, caching, and tweet parsing.
Designed for free tier API limits (1,500 reads/month).
"""

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp
import boto3
from botocore.exceptions import ClientError

from .models import TweetItem

logger = logging.getLogger(__name__)

# Twitter API v2 base URL
TWITTER_API_BASE = "https://api.twitter.com/2"

# Rate limiting configuration
RATE_LIMIT_CONFIG = {
    "list_fetch_interval_hours": 2,
    "search_cooldown_minutes": 60,
    "cache_ttl_hours": 2,
    "max_searches_per_day": 3,
    "monthly_limit": 1500,
    "alert_threshold": 0.8,  # Alert at 80% usage
}

# Tweet fields to request from API
TWEET_FIELDS = [
    "id",
    "text",
    "author_id",
    "created_at",
    "public_metrics",
    "entities",
]

USER_FIELDS = ["id", "username", "name"]

EXPANSIONS = ["author_id"]


class RateLimitError(Exception):
    """Raised when rate limit is exceeded"""

    def __init__(self, reset_time: datetime, message: str = "Rate limit exceeded"):
        self.reset_time = reset_time
        super().__init__(f"{message}. Resets at {reset_time}")


class TwitterAPIError(Exception):
    """Raised for Twitter API errors"""

    def __init__(self, status_code: int, message: str, error_code: str | None = None):
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(f"Twitter API Error {status_code}: {message}")


class TwitterClient:
    """
    Async Twitter/X API v2 client with rate limiting and S3 caching.

    Usage:
        client = TwitterClient(bucket_name="sigint-data-xxx")
        tweets = await client.fetch_list_timeline("1234567890")
    """

    def __init__(
        self,
        bucket_name: str,
        bearer_token: str | None = None,
        ssm_parameter: str = "/sigint/x-bearer-token",
        region: str = "us-east-1",
    ):
        self.bucket_name = bucket_name
        self.region = region
        self._bearer_token = bearer_token
        self._ssm_parameter = ssm_parameter
        self._s3_client = None
        self._ssm_client = None

        # Rate limit tracking
        self._rate_limit_remaining: int | None = None
        self._rate_limit_reset: datetime | None = None
        self._last_search_time: datetime | None = None
        self._searches_today: int = 0
        self._searches_today_date: str | None = None

    @property
    def s3_client(self):
        """Lazy initialization of S3 client"""
        if self._s3_client is None:
            self._s3_client = boto3.client("s3", region_name=self.region)
        return self._s3_client

    @property
    def ssm_client(self):
        """Lazy initialization of SSM client"""
        if self._ssm_client is None:
            self._ssm_client = boto3.client("ssm", region_name=self.region)
        return self._ssm_client

    def _get_bearer_token(self) -> str:
        """Get bearer token from SSM or cached value"""
        if self._bearer_token:
            return self._bearer_token

        try:
            response = self.ssm_client.get_parameter(
                Name=self._ssm_parameter,
                WithDecryption=True,
            )
            self._bearer_token = response["Parameter"]["Value"]
            return self._bearer_token
        except ClientError as e:
            logger.error(f"Failed to get bearer token from SSM: {e}")
            raise

    def _get_headers(self) -> dict[str, str]:
        """Get headers for Twitter API requests"""
        return {
            "Authorization": f"Bearer {self._get_bearer_token()}",
            "Content-Type": "application/json",
        }

    def _cache_key(self, endpoint: str, identifier: str) -> str:
        """Generate S3 cache key for an API response"""
        return f"twitter/cache/{endpoint}/{identifier}.json"

    def _usage_key(self) -> str:
        """Generate S3 key for monthly usage tracking"""
        now = datetime.now(UTC)
        return f"twitter/usage/{now.year}-{now.month:02d}.json"

    async def _get_cached(self, cache_key: str) -> dict | None:
        """Check S3 cache for a response. Returns None if not cached or expired."""
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.get_object(Bucket=self.bucket_name, Key=cache_key),
            )
            data = json.loads(response["Body"].read().decode("utf-8"))

            # Check TTL
            cached_at = datetime.fromisoformat(data.get("_cached_at", "2000-01-01T00:00:00+00:00"))
            ttl_hours = RATE_LIMIT_CONFIG["cache_ttl_hours"]
            if datetime.now(UTC) - cached_at > timedelta(hours=ttl_hours):
                logger.debug(f"Cache expired for {cache_key}")
                return None

            logger.info(f"Cache hit for {cache_key}")
            return data

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.debug(f"Cache miss for {cache_key}")
                return None
            logger.error(f"S3 cache error: {e}")
            return None

    async def _set_cached(self, cache_key: str, data: dict) -> None:
        """Store response in S3 cache"""
        data["_cached_at"] = datetime.now(UTC).isoformat()
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=cache_key,
                    Body=json.dumps(data, default=str),
                    ContentType="application/json",
                ),
            )
            logger.debug(f"Cached response to {cache_key}")
        except ClientError as e:
            logger.error(f"Failed to cache response: {e}")

    async def _increment_usage(self) -> int:
        """Increment and return monthly API usage count"""
        usage_key = self._usage_key()
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.get_object(Bucket=self.bucket_name, Key=usage_key),
            )
            usage = json.loads(response["Body"].read().decode("utf-8"))
        except ClientError:
            usage = {"count": 0, "month": datetime.now(UTC).strftime("%Y-%m")}

        usage["count"] += 1
        usage["last_call"] = datetime.now(UTC).isoformat()

        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=usage_key,
                Body=json.dumps(usage),
                ContentType="application/json",
            ),
        )

        # Check alert threshold
        if usage["count"] >= RATE_LIMIT_CONFIG["monthly_limit"] * RATE_LIMIT_CONFIG["alert_threshold"]:
            logger.warning(
                f"API usage at {usage['count']}/{RATE_LIMIT_CONFIG['monthly_limit']} "
                f"({usage['count']/RATE_LIMIT_CONFIG['monthly_limit']*100:.1f}%)"
            )

        return usage["count"]

    async def get_monthly_usage(self) -> dict:
        """Get current monthly API usage stats"""
        usage_key = self._usage_key()
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.get_object(Bucket=self.bucket_name, Key=usage_key),
            )
            usage = json.loads(response["Body"].read().decode("utf-8"))
            usage["limit"] = RATE_LIMIT_CONFIG["monthly_limit"]
            usage["remaining"] = RATE_LIMIT_CONFIG["monthly_limit"] - usage.get("count", 0)
            usage["percentage"] = usage.get("count", 0) / RATE_LIMIT_CONFIG["monthly_limit"] * 100
            return usage
        except ClientError:
            return {
                "count": 0,
                "limit": RATE_LIMIT_CONFIG["monthly_limit"],
                "remaining": RATE_LIMIT_CONFIG["monthly_limit"],
                "percentage": 0.0,
            }

    def _update_rate_limits(self, headers: dict) -> None:
        """Update rate limit tracking from response headers"""
        if "x-rate-limit-remaining" in headers:
            self._rate_limit_remaining = int(headers["x-rate-limit-remaining"])
        if "x-rate-limit-reset" in headers:
            self._rate_limit_reset = datetime.fromtimestamp(
                int(headers["x-rate-limit-reset"]), tz=UTC
            )

    def _parse_tweet(self, tweet_data: dict, users_map: dict[str, dict]) -> TweetItem:
        """Parse Twitter API v2 tweet response into TweetItem model"""
        author_id = tweet_data.get("author_id", "")
        author_info = users_map.get(author_id, {})

        # Parse entities
        entities = tweet_data.get("entities", {})
        hashtags = [h["tag"] for h in entities.get("hashtags", [])]
        mentions = [m["username"] for m in entities.get("mentions", [])]
        cashtags = [c["tag"] for c in entities.get("cashtags", [])]

        # Parse metrics
        metrics = tweet_data.get("public_metrics", {})

        # Parse created_at
        created_at_str = tweet_data.get("created_at", "")
        if created_at_str:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        else:
            created_at = datetime.now(UTC)

        return TweetItem(
            tweet_id=tweet_data["id"],
            author_handle=author_info.get("username", "unknown"),
            author_id=author_id,
            content=tweet_data.get("text", ""),
            created_at=created_at,
            hashtags=hashtags,
            mentions=mentions,
            cashtags=cashtags,
            retweet_count=metrics.get("retweet_count", 0),
            like_count=metrics.get("like_count", 0),
            reply_count=metrics.get("reply_count", 0),
            quote_count=metrics.get("quote_count", 0),
        )

    def _build_users_map(self, includes: dict) -> dict[str, dict]:
        """Build a map of user_id -> user info from API includes"""
        users = includes.get("users", [])
        return {user["id"]: user for user in users}

    async def _make_request(
        self,
        endpoint: str,
        params: dict | None = None,
        use_cache: bool = True,
        cache_identifier: str | None = None,
    ) -> dict:
        """Make a rate-limited, cached request to Twitter API"""
        # Generate cache key
        if cache_identifier:
            cache_key = self._cache_key(endpoint.split("/")[-1], cache_identifier)
        else:
            param_hash = hashlib.md5(json.dumps(params or {}, sort_keys=True).encode()).hexdigest()[:8]
            cache_key = self._cache_key(endpoint.split("/")[-1], param_hash)

        # Check cache first
        if use_cache:
            cached = await self._get_cached(cache_key)
            if cached:
                return cached

        # Check rate limit
        if self._rate_limit_remaining is not None and self._rate_limit_remaining <= 0:
            if self._rate_limit_reset and datetime.now(UTC) < self._rate_limit_reset:
                raise RateLimitError(self._rate_limit_reset)

        # Check monthly limit
        usage = await self.get_monthly_usage()
        if usage["remaining"] <= 0:
            raise RateLimitError(
                datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0) + timedelta(days=32),
                "Monthly API limit reached",
            )

        # Make request
        url = f"{TWITTER_API_BASE}/{endpoint}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    url,
                    headers=self._get_headers(),
                    params=params,
                ) as response:
                    self._update_rate_limits(dict(response.headers))

                    if response.status == 429:
                        reset_time = self._rate_limit_reset or datetime.now(UTC) + timedelta(minutes=15)
                        raise RateLimitError(reset_time)

                    if response.status != 200:
                        error_data = await response.json()
                        raise TwitterAPIError(
                            status_code=response.status,
                            message=error_data.get("detail", str(error_data)),
                            error_code=error_data.get("errors", [{}])[0].get("code"),
                        )

                    data = await response.json()

            except aiohttp.ClientError as e:
                logger.error(f"HTTP error calling Twitter API: {e}")
                raise TwitterAPIError(status_code=0, message=str(e))

        # Increment usage counter
        await self._increment_usage()

        # Cache successful response
        if use_cache:
            await self._set_cached(cache_key, data)

        return data

    async def fetch_list_timeline(
        self,
        list_id: str,
        max_results: int = 50,
        use_cache: bool = True,
    ) -> list[TweetItem]:
        """
        Fetch tweets from a Twitter List.

        Args:
            list_id: Twitter List ID
            max_results: Maximum tweets to return (max 100)
            use_cache: Whether to use S3 cache

        Returns:
            List of TweetItem models
        """
        params = {
            "max_results": min(max_results, 100),
            "tweet.fields": ",".join(TWEET_FIELDS),
            "user.fields": ",".join(USER_FIELDS),
            "expansions": ",".join(EXPANSIONS),
        }

        data = await self._make_request(
            f"lists/{list_id}/tweets",
            params=params,
            use_cache=use_cache,
            cache_identifier=list_id,
        )

        tweets_data = data.get("data", [])
        includes = data.get("includes", {})
        users_map = self._build_users_map(includes)

        tweets = []
        for tweet_data in tweets_data:
            try:
                tweet = self._parse_tweet(tweet_data, users_map)
                tweet.source_type = "list"
                tweets.append(tweet)
            except Exception as e:
                logger.warning(f"Failed to parse tweet {tweet_data.get('id')}: {e}")

        logger.info(f"Fetched {len(tweets)} tweets from list {list_id}")
        return tweets

    async def search_tweets(
        self,
        query: str,
        max_results: int = 10,
        use_cache: bool = True,
    ) -> list[TweetItem]:
        """
        Search for tweets matching a query.

        Note: Free tier has very limited search access. Use sparingly.

        Args:
            query: Twitter search query
            max_results: Maximum tweets to return (max 100, recommend 10-20)
            use_cache: Whether to use S3 cache

        Returns:
            List of TweetItem models
        """
        # Check search cooldown
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self._searches_today_date != today:
            self._searches_today = 0
            self._searches_today_date = today

        if self._searches_today >= RATE_LIMIT_CONFIG["max_searches_per_day"]:
            logger.warning("Daily search limit reached")
            return []

        if self._last_search_time:
            cooldown = timedelta(minutes=RATE_LIMIT_CONFIG["search_cooldown_minutes"])
            if datetime.now(UTC) - self._last_search_time < cooldown:
                wait_seconds = (cooldown - (datetime.now(UTC) - self._last_search_time)).seconds
                logger.warning(f"Search cooldown active. Wait {wait_seconds}s")
                return []

        params = {
            "query": query,
            "max_results": min(max_results, 100),
            "tweet.fields": ",".join(TWEET_FIELDS),
            "user.fields": ",".join(USER_FIELDS),
            "expansions": ",".join(EXPANSIONS),
        }

        # Use query hash as cache identifier
        query_hash = hashlib.md5(query.encode()).hexdigest()[:12]

        data = await self._make_request(
            "tweets/search/recent",
            params=params,
            use_cache=use_cache,
            cache_identifier=f"search_{query_hash}",
        )

        # Update search tracking
        self._searches_today += 1
        self._last_search_time = datetime.now(UTC)

        tweets_data = data.get("data", [])
        includes = data.get("includes", {})
        users_map = self._build_users_map(includes)

        tweets = []
        for tweet_data in tweets_data:
            try:
                tweet = self._parse_tweet(tweet_data, users_map)
                tweet.source_type = "search"
                tweets.append(tweet)
            except Exception as e:
                logger.warning(f"Failed to parse tweet {tweet_data.get('id')}: {e}")

        logger.info(f"Search '{query[:30]}...' returned {len(tweets)} tweets")
        return tweets

    async def fetch_user_timeline(
        self,
        user_id: str,
        max_results: int = 20,
        use_cache: bool = True,
    ) -> list[TweetItem]:
        """
        Fetch tweets from a specific user's timeline.

        Args:
            user_id: Twitter user ID (not @handle)
            max_results: Maximum tweets to return
            use_cache: Whether to use S3 cache

        Returns:
            List of TweetItem models
        """
        params = {
            "max_results": min(max_results, 100),
            "tweet.fields": ",".join(TWEET_FIELDS),
            "user.fields": ",".join(USER_FIELDS),
            "expansions": ",".join(EXPANSIONS),
        }

        data = await self._make_request(
            f"users/{user_id}/tweets",
            params=params,
            use_cache=use_cache,
            cache_identifier=f"user_{user_id}",
        )

        tweets_data = data.get("data", [])
        includes = data.get("includes", {})
        users_map = self._build_users_map(includes)

        tweets = []
        for tweet_data in tweets_data:
            try:
                tweet = self._parse_tweet(tweet_data, users_map)
                tweet.source_type = "user"
                tweets.append(tweet)
            except Exception as e:
                logger.warning(f"Failed to parse tweet {tweet_data.get('id')}: {e}")

        logger.info(f"Fetched {len(tweets)} tweets from user {user_id}")
        return tweets

    async def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        """
        Look up a user by their @username.

        Args:
            username: Twitter username (without @)

        Returns:
            User data dict or None if not found
        """
        params = {
            "user.fields": ",".join(USER_FIELDS),
        }

        try:
            data = await self._make_request(
                f"users/by/username/{username}",
                params=params,
                use_cache=True,
                cache_identifier=f"username_{username}",
            )
            return data.get("data")
        except TwitterAPIError as e:
            if e.status_code == 404:
                return None
            raise
