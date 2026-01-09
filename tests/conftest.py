"""
SIGINT Test Configuration and Shared Fixtures
"""

import os
import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

# Add lambdas to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))


# =============================================================================
# Environment Setup
# =============================================================================


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Set up required environment variables for all tests."""
    monkeypatch.setenv("DATA_BUCKET", "test-sigint-data")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")


# =============================================================================
# S3 Fixtures
# =============================================================================


@pytest.fixture
def aws_credentials():
    """Mock AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def s3_client(aws_credentials):
    """Create a mocked S3 client."""
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        yield client


@pytest.fixture
def s3_bucket(s3_client):
    """Create a test S3 bucket."""
    bucket_name = "test-sigint-data"
    s3_client.create_bucket(Bucket=bucket_name)
    return bucket_name


@pytest.fixture
def s3_store(s3_bucket):
    """Create an S3Store instance with mocked S3."""
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=s3_bucket)

        from shared.s3_store import S3Store

        store = S3Store(bucket_name=s3_bucket, region="us-east-1")
        yield store


# =============================================================================
# LLM Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client responses."""
    with patch("anthropic.Anthropic") as mock_class:
        mock_client = MagicMock()
        mock_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"selected_items": [], "agent_notes": "Test"}')]
        mock_client.messages.create.return_value = mock_response

        yield mock_client


@pytest.fixture
def mock_llm_analysis_response():
    """Sample LLM analysis response."""
    return {
        "selected_items": [
            {
                "item_number": 1,
                "summary": "Test summary for item 1",
                "urgency": "normal",
                "relevance_score": 0.85,
                "entities": ["Entity1", "Entity2"],
                "tags": ["tag1", "tag2"],
            }
        ],
        "agent_notes": "Testing the analysis pipeline",
    }


# =============================================================================
# Feed Data Fixtures
# =============================================================================


@pytest.fixture
def sample_rss_content():
    """Sample RSS feed content for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>Test Feed</title>
        <link>https://example.com</link>
        <item>
            <title>Breaking: Major AI Breakthrough</title>
            <link>https://example.com/article1</link>
            <description>Scientists announce a major breakthrough in AI.</description>
            <pubDate>Wed, 08 Jan 2026 10:00:00 GMT</pubDate>
        </item>
    </channel>
</rss>"""


@pytest.fixture
def sample_coingecko_response():
    """Sample CoinGecko API response."""
    return {
        "bitcoin": {"usd": 95000.50, "usd_24h_change": 2.35},
        "ethereum": {"usd": 3500.25, "usd_24h_change": -1.20},
    }


# =============================================================================
# Model Fixtures
# =============================================================================


@pytest.fixture
def sample_news_item():
    """Create a sample NewsItem for testing."""
    from shared.models import Category, NewsItem, Urgency

    return NewsItem(
        id="abc123def456",
        title="Test News Article",
        summary="This is a test summary.",
        url="https://example.com/article",
        source="Test Source",
        source_url="https://example.com/feed.xml",
        category=Category.AI_ML,
        urgency=Urgency.NORMAL,
        relevance_score=0.75,
        published_at=datetime(2026, 1, 8, 10, 0, 0, tzinfo=UTC),
        entities=["OpenAI", "GPT-5"],
        tags=["ai", "research"],
    )


@pytest.fixture
def sample_category_data(sample_news_item):
    """Create sample CategoryData for testing."""
    from shared.models import Category, CategoryData

    return CategoryData(
        category=Category.AI_ML, items=[sample_news_item], agent_notes="Test agent notes"
    )


@pytest.fixture
def sample_raw_feed_items():
    """Create sample RawFeedItem instances for testing."""
    from shared.feed_fetcher import RawFeedItem

    return [
        RawFeedItem(
            id="feed1",
            title="AI Research Update",
            link="https://example.com/ai-research",
            description="Latest developments in AI research",
            source="ArXiv",
            source_url="https://arxiv.org/rss/cs.AI",
            published=datetime(2026, 1, 8, 10, 0, 0, tzinfo=UTC),
            raw_data={},
        ),
    ]


@pytest.fixture
def lambda_context():
    """Mock AWS Lambda context object."""
    context = MagicMock()
    context.function_name = "test-function"
    context.memory_limit_in_mb = 512
    context.aws_request_id = "test-request-id"
    context.get_remaining_time_in_millis.return_value = 300000
    return context
