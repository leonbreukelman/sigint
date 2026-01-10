"""
Tests for analyzer/handler.py (Unified Analyzer Lambda)
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


class TestAnalyzerHandlerValidation:
    """Tests for handler input validation."""

    def test_invalid_category_returns_400(self):
        with patch.dict(
            "os.environ", {"DATA_BUCKET": "test-bucket", "ANTHROPIC_API_KEY": "test-key"}
        ):
            from analyzer.handler import handler

            result = handler({"category": "invalid-cat"}, None)

            assert result["statusCode"] == 400
            body = json.loads(result["body"])
            assert "Invalid category" in body["error"]

    def test_non_unified_category_returns_400(self):
        with patch.dict(
            "os.environ", {"DATA_BUCKET": "test-bucket", "ANTHROPIC_API_KEY": "test-key"}
        ):
            from analyzer.handler import handler

            # MARKETS is not in UNIFIED_CATEGORIES
            result = handler({"category": "markets"}, None)

            assert result["statusCode"] == 400
            body = json.loads(result["body"])
            assert "not eligible for unified analysis" in body["error"]


class TestAnalyzerHandlerNoData:
    """Tests for handler when no RSS data is available."""

    @patch("analyzer.handler.S3Store")
    @patch("analyzer.handler.LLMClient")
    def test_no_rss_items_returns_success_with_message(self, mock_llm_class, mock_store_class):
        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.load_raw_data.return_value = None  # No raw data

        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm
        mock_llm.model = "claude-test"

        with patch.dict(
            "os.environ", {"DATA_BUCKET": "test-bucket", "ANTHROPIC_API_KEY": "test-key"}
        ):
            from analyzer.handler import handler

            result = handler({"category": "ai-ml"}, None)

            assert result["statusCode"] == 200
            body = json.loads(result["body"])
            assert "No RSS items to analyze" in body["message"]


class TestAnalyzerHandlerSuccess:
    """Tests for successful unified analysis."""

    @patch("analyzer.handler.S3Store")
    @patch("analyzer.handler.LLMClient")
    def test_successful_analysis(self, mock_llm_class, mock_store_class):
        from shared.models import (
            AnalyzedItem,
            Category,
            NewsItem,
            RawSourceData,
            SourceType,
            TwitterSignal,
            UnifiedAnalysisResult,
            Urgency,
        )

        # Mock store with RSS data
        mock_store = MagicMock()
        mock_store_class.return_value = mock_store

        rss_data = RawSourceData(
            source_type=SourceType.RSS,
            category=Category.AI_ML,
            rss_items=[
                NewsItem(
                    id="test-1",
                    title="Test AI Article",
                    summary="Test summary",
                    url="https://example.com/test",
                    source="Test Source",
                    source_url="https://example.com/feed.xml",
                    category=Category.AI_ML,
                    relevance_score=0.8,
                )
            ],
        )

        twitter_data = RawSourceData(
            source_type=SourceType.TWITTER,
            category=Category.AI_ML,
            twitter_signals=[
                TwitterSignal(
                    entity="@OpenAI",
                    velocity=5.0,
                    velocity_ratio=2.5,
                    is_spike=True,
                )
            ],
        )

        def mock_load_raw_data(category, source_type):
            if source_type == SourceType.RSS:
                return rss_data
            elif source_type == SourceType.TWITTER:
                return twitter_data
            return None

        mock_store.load_raw_data.side_effect = mock_load_raw_data

        # Mock LLM client
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm
        mock_llm.model = "claude-test"

        mock_result = UnifiedAnalysisResult(
            category=Category.AI_ML,
            items=[
                AnalyzedItem(
                    id="test-1",
                    title="Test AI Article",
                    summary="LLM enhanced summary",
                    url="https://example.com/test",
                    source="Test Source",
                    source_url="https://example.com/feed.xml",
                    category=Category.AI_ML,
                    urgency=Urgency.NORMAL,
                    relevance_score=0.8,
                    source_tags=[SourceType.RSS, SourceType.TWITTER],
                    twitter_boost=0.2,
                    confidence=0.9,
                )
            ],
            sources_used=[SourceType.RSS, SourceType.TWITTER],
            sources_missing=[SourceType.POLYMARKET],
            items_boosted=1,
            llm_tokens=200,
            agent_notes="Analysis complete",
        )
        mock_llm.analyze_unified.return_value = mock_result

        with patch.dict(
            "os.environ", {"DATA_BUCKET": "test-bucket", "ANTHROPIC_API_KEY": "test-key"}
        ):
            from analyzer.handler import handler

            result = handler({"category": "ai-ml"}, None)

            assert result["statusCode"] == 200
            body = json.loads(result["body"])
            assert body["category"] == "ai-ml"
            assert body["items_analyzed"] == 1
            assert body["items_boosted"] == 1
            assert body["llm_tokens"] == 200
            assert "rss" in body["sources"]
            assert "twitter" in body["sources"]

    @patch("analyzer.handler.S3Store")
    @patch("analyzer.handler.LLMClient")
    def test_default_category_is_ai_ml(self, mock_llm_class, mock_store_class):
        mock_store = MagicMock()
        mock_store_class.return_value = mock_store
        mock_store.load_raw_data.return_value = None

        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm
        mock_llm.model = "claude-test"

        with patch.dict(
            "os.environ", {"DATA_BUCKET": "test-bucket", "ANTHROPIC_API_KEY": "test-key"}
        ):
            from analyzer.handler import handler

            # No category specified
            result = handler({}, None)

            assert result["statusCode"] == 200
            body = json.loads(result["body"])
            assert body["category"] == "ai-ml"


class TestLoadRawSources:
    """Tests for _load_raw_sources helper function."""

    @patch("analyzer.handler.S3Store")
    def test_load_all_sources(self, mock_store_class):
        from analyzer.handler import _load_raw_sources
        from shared.models import (
            Category,
            NewsItem,
            PredictionMarket,
            RawSourceData,
            SourceType,
            TwitterSignal,
        )

        mock_store = MagicMock()

        rss_data = RawSourceData(
            source_type=SourceType.RSS,
            category=Category.AI_ML,
            rss_items=[
                NewsItem(
                    id="rss-1",
                    title="RSS Article",
                    summary="Summary",
                    url="https://example.com",
                    source="RSS Source",
                    source_url="https://example.com/feed.xml",
                    category=Category.AI_ML,
                    relevance_score=0.7,
                )
            ],
        )

        twitter_data = RawSourceData(
            source_type=SourceType.TWITTER,
            category=Category.AI_ML,
            twitter_signals=[
                TwitterSignal(entity="#AI", velocity=3.0, velocity_ratio=1.5)
            ],
        )

        polymarket_data = RawSourceData(
            source_type=SourceType.POLYMARKET,
            category=Category.AI_ML,
            prediction_markets=[
                PredictionMarket(
                    question="Will GPT-5 launch?",
                    probability=0.65,
                    source="Polymarket",
                    url="https://polymarket.com/test",
                )
            ],
        )

        def mock_load(category, source_type):
            if source_type == SourceType.RSS:
                return rss_data
            elif source_type == SourceType.TWITTER:
                return twitter_data
            elif source_type == SourceType.POLYMARKET:
                return polymarket_data
            return None

        mock_store.load_raw_data.side_effect = mock_load

        metrics = {
            "rss_items_loaded": 0,
            "twitter_signals_loaded": 0,
            "polymarket_loaded": 0,
        }

        rss_items, twitter_signals, prediction_markets = _load_raw_sources(
            mock_store, Category.AI_ML, metrics
        )

        assert len(rss_items) == 1
        assert len(twitter_signals) == 1
        assert len(prediction_markets) == 1
        assert metrics["rss_items_loaded"] == 1
        assert metrics["twitter_signals_loaded"] == 1
        assert metrics["polymarket_loaded"] == 1

    @patch("analyzer.handler.S3Store")
    def test_handles_missing_sources_gracefully(self, mock_store_class):
        from analyzer.handler import _load_raw_sources
        from shared.models import Category, SourceType

        mock_store = MagicMock()
        mock_store.load_raw_data.return_value = None  # No data for any source

        metrics = {
            "rss_items_loaded": 0,
            "twitter_signals_loaded": 0,
            "polymarket_loaded": 0,
        }

        rss_items, twitter_signals, prediction_markets = _load_raw_sources(
            mock_store, Category.AI_ML, metrics
        )

        assert rss_items == []
        assert twitter_signals is None
        assert prediction_markets is None
        assert metrics["rss_items_loaded"] == 0


class TestSaveAnalyzedResults:
    """Tests for _save_analyzed_results helper function."""

    @patch("analyzer.handler.S3Store")
    def test_saves_category_data_and_unified_result(self, mock_store_class):
        from analyzer.handler import _save_analyzed_results
        from shared.models import (
            AnalyzedItem,
            Category,
            SourceType,
            UnifiedAnalysisResult,
            Urgency,
        )

        mock_store = MagicMock()

        result = UnifiedAnalysisResult(
            category=Category.AI_ML,
            items=[
                AnalyzedItem(
                    id="test-1",
                    title="Test Article",
                    summary="Summary",
                    url="https://example.com",
                    source="Source",
                    source_url="https://example.com/feed.xml",
                    category=Category.AI_ML,
                    urgency=Urgency.HIGH,
                    relevance_score=0.9,
                    source_tags=[SourceType.RSS],
                    confidence=0.85,
                )
            ],
            sources_used=[SourceType.RSS],
            agent_notes="Test notes",
        )

        _save_analyzed_results(mock_store, Category.AI_ML, result)

        # Should save both CategoryData and UnifiedAnalysisResult
        mock_store.save_category_data.assert_called_once()
        mock_store.save_unified_analysis.assert_called_once_with(result)
