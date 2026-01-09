"""
Tests for shared/models.py
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError


class TestUrgencyEnum:
    """Tests for Urgency enum."""

    def test_urgency_values(self):
        from shared.models import Urgency

        assert Urgency.BREAKING.value == "breaking"
        assert Urgency.HIGH.value == "high"
        assert Urgency.NORMAL.value == "normal"
        assert Urgency.LOW.value == "low"

    def test_urgency_from_string(self):
        from shared.models import Urgency

        assert Urgency("breaking") == Urgency.BREAKING
        assert Urgency("normal") == Urgency.NORMAL


class TestCategoryEnum:
    """Tests for Category enum."""

    def test_category_values(self):
        from shared.models import Category

        assert Category.GEOPOLITICAL.value == "geopolitical"
        assert Category.AI_ML.value == "ai-ml"
        assert Category.DEEP_TECH.value == "deep-tech"
        assert Category.CRYPTO_FINANCE.value == "crypto-finance"
        assert Category.NARRATIVE.value == "narrative"
        assert Category.BREAKING.value == "breaking"

    def test_all_categories_count(self):
        from shared.models import Category

        # 7 categories: geopolitical, ai-ml, deep-tech, crypto-finance, markets, narrative, breaking
        assert len(Category) == 7


class TestNewsItem:
    """Tests for NewsItem model."""

    def test_create_valid_news_item(self, sample_news_item):
        assert sample_news_item.id == "abc123def456"
        assert sample_news_item.title == "Test News Article"
        assert sample_news_item.relevance_score == 0.75

    def test_relevance_score_validation_min(self):
        from shared.models import Category, NewsItem

        with pytest.raises(ValidationError) as exc_info:
            NewsItem(
                id="test",
                title="Test",
                summary="Test",
                url="https://example.com",
                source="Test",
                source_url="https://example.com",
                category=Category.AI_ML,
                relevance_score=-0.1,  # Invalid: below 0
            )
        assert "relevance_score" in str(exc_info.value)

    def test_relevance_score_validation_max(self):
        from shared.models import Category, NewsItem

        with pytest.raises(ValidationError) as exc_info:
            NewsItem(
                id="test",
                title="Test",
                summary="Test",
                url="https://example.com",
                source="Test",
                source_url="https://example.com",
                category=Category.AI_ML,
                relevance_score=1.5,  # Invalid: above 1
            )
        assert "relevance_score" in str(exc_info.value)

    def test_relevance_score_boundary_values(self):
        from shared.models import Category, NewsItem

        # Test 0 is valid
        item_zero = NewsItem(
            id="test",
            title="Test",
            summary="Test",
            url="https://example.com",
            source="Test",
            source_url="https://example.com",
            category=Category.AI_ML,
            relevance_score=0.0,
        )
        assert item_zero.relevance_score == 0.0

        # Test 1 is valid
        item_one = NewsItem(
            id="test",
            title="Test",
            summary="Test",
            url="https://example.com",
            source="Test",
            source_url="https://example.com",
            category=Category.AI_ML,
            relevance_score=1.0,
        )
        assert item_one.relevance_score == 1.0

    def test_default_urgency(self):
        from shared.models import Category, NewsItem, Urgency

        item = NewsItem(
            id="test",
            title="Test",
            summary="Test",
            url="https://example.com",
            source="Test",
            source_url="https://example.com",
            category=Category.AI_ML,
            relevance_score=0.5,
        )
        assert item.urgency == Urgency.NORMAL

    def test_default_lists_are_empty(self):
        from shared.models import Category, NewsItem

        item = NewsItem(
            id="test",
            title="Test",
            summary="Test",
            url="https://example.com",
            source="Test",
            source_url="https://example.com",
            category=Category.AI_ML,
            relevance_score=0.5,
        )
        assert item.entities == []
        assert item.tags == []
        assert item.related_items == []

    def test_fetched_at_default_is_timezone_aware(self):
        from shared.models import Category, NewsItem

        item = NewsItem(
            id="test",
            title="Test",
            summary="Test",
            url="https://example.com",
            source="Test",
            source_url="https://example.com",
            category=Category.AI_ML,
            relevance_score=0.5,
        )
        assert item.fetched_at is not None
        assert item.fetched_at.tzinfo is not None

    def test_model_dump_serialization(self, sample_news_item):
        data = sample_news_item.model_dump()

        assert isinstance(data, dict)
        assert data["id"] == "abc123def456"
        assert data["category"] == "ai-ml"
        assert data["urgency"] == "normal"


class TestCategoryData:
    """Tests for CategoryData model."""

    def test_create_category_data(self, sample_category_data):
        from shared.models import Category

        assert sample_category_data.category == Category.AI_ML
        assert len(sample_category_data.items) == 1
        assert sample_category_data.agent_notes == "Test agent notes"

    def test_last_updated_default_is_timezone_aware(self):
        from shared.models import Category, CategoryData

        data = CategoryData(category=Category.AI_ML, items=[])
        assert data.last_updated is not None
        assert data.last_updated.tzinfo is not None

    def test_empty_items_list(self):
        from shared.models import Category, CategoryData

        data = CategoryData(category=Category.GEOPOLITICAL, items=[])
        assert data.items == []


class TestNarrativePattern:
    """Tests for NarrativePattern model."""

    def test_create_narrative_pattern(self):
        from shared.models import NarrativePattern

        now = datetime.now(UTC)
        pattern = NarrativePattern(
            id="pattern1",
            title="Test Pattern",
            description="A test narrative pattern",
            sources=["source1", "source2"],
            item_ids=["item1"],
            strength=0.85,
            first_seen=now,
            last_seen=now,
        )

        assert pattern.id == "pattern1"
        assert pattern.strength == 0.85
        assert len(pattern.sources) == 2

    def test_strength_validation(self):
        from shared.models import NarrativePattern

        now = datetime.now(UTC)

        with pytest.raises(ValidationError):
            NarrativePattern(
                id="test",
                title="Test",
                description="Test",
                sources=[],
                item_ids=[],
                strength=1.5,  # Invalid
                first_seen=now,
                last_seen=now,
            )


class TestDashboardState:
    """Tests for DashboardState model."""

    def test_create_dashboard_state(self, sample_category_data):
        from shared.models import DashboardState

        now = datetime.now(UTC)
        state = DashboardState(
            categories={"ai-ml": sample_category_data},
            narratives=[],
            last_updated=now,
        )

        assert "ai-ml" in state.categories
        assert state.system_status == "operational"
        assert state.narratives == []
