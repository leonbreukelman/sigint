"""
Tests for shared/llm_client.py
"""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestLLMClientInit:
    """Tests for LLMClient initialization."""

    def test_init_with_api_key(self):
        with patch("anthropic.Anthropic"):
            from shared.llm_client import LLMClient

            client = LLMClient(api_key="test-key")
            assert client.api_key == "test-key"

    def test_init_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")

        with patch("anthropic.Anthropic"):
            from shared.llm_client import LLMClient

            client = LLMClient()
            assert client.api_key == "env-key"

    def test_init_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        from shared.llm_client import LLMClient

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not set"):
            LLMClient(api_key=None)

    def test_default_model(self):
        with patch("anthropic.Anthropic"):
            from shared.llm_client import LLMClient

            client = LLMClient(api_key="test-key")
            assert "claude" in client.model.lower()


class TestLLMClientPromptBuilding:
    """Tests for prompt building methods."""

    def test_build_analysis_prompt_includes_items(self, sample_raw_feed_items):
        with patch("anthropic.Anthropic"):
            from shared.llm_client import LLMClient
            from shared.models import Category

            client = LLMClient(api_key="test-key")
            prompt = client._build_analysis_prompt(Category.AI_ML, sample_raw_feed_items)

            assert "AI Research Update" in prompt
            assert "ArXiv" in prompt
            assert "TOP 5" in prompt

    def test_build_analysis_prompt_category_specific(self, sample_raw_feed_items):
        with patch("anthropic.Anthropic"):
            from shared.llm_client import LLMClient
            from shared.models import Category

            client = LLMClient(api_key="test-key")

            ai_prompt = client._build_analysis_prompt(Category.AI_ML, sample_raw_feed_items)
            geo_prompt = client._build_analysis_prompt(Category.GEOPOLITICAL, sample_raw_feed_items)

            # Different categories should have different system prompts
            assert "AI/ML" in ai_prompt or "artificial intelligence" in ai_prompt.lower()
            assert "geopolitical" in geo_prompt.lower() or "international" in geo_prompt.lower()

    def test_build_narrative_prompt(self, sample_news_item):
        with patch("anthropic.Anthropic"):
            from shared.llm_client import LLMClient

            client = LLMClient(api_key="test-key")

            items_by_category = {
                "ai-ml": [sample_news_item],
                "geopolitical": [],
            }

            prompt = client._build_narrative_prompt(items_by_category)

            assert "pattern" in prompt.lower()
            assert "AI-ML" in prompt or "ai-ml" in prompt.lower()


class TestLLMClientAnalyze:
    """Tests for analyze_items method."""

    def test_analyze_items_empty_list(self):
        with patch("anthropic.Anthropic"):
            from shared.llm_client import LLMClient
            from shared.models import Category

            client = LLMClient(api_key="test-key")
            selected, notes = client.analyze_items(Category.AI_ML, [])

            assert selected == []
            assert notes == ""

    def test_analyze_items_success(self, sample_raw_feed_items, mock_llm_analysis_response):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps(mock_llm_analysis_response))]
            mock_client.messages.create.return_value = mock_response

            from shared.llm_client import LLMClient
            from shared.models import Category

            client = LLMClient(api_key="test-key")
            selected, notes = client.analyze_items(Category.AI_ML, sample_raw_feed_items)

            assert len(selected) == 1
            assert selected[0]["relevance_score"] == 0.85
            assert notes == "Testing the analysis pipeline"

    def test_analyze_items_api_error(self, sample_raw_feed_items):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client
            mock_client.messages.create.side_effect = Exception("API Error")

            from shared.llm_client import LLMClient
            from shared.models import Category

            client = LLMClient(api_key="test-key")
            selected, notes = client.analyze_items(Category.AI_ML, sample_raw_feed_items)

            # Should handle error gracefully
            assert selected == []
            assert notes == ""

    def test_analyze_items_invalid_json_response(self, sample_raw_feed_items):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="This is not valid JSON")]
            mock_client.messages.create.return_value = mock_response

            from shared.llm_client import LLMClient
            from shared.models import Category

            client = LLMClient(api_key="test-key")
            selected, notes = client.analyze_items(Category.AI_ML, sample_raw_feed_items)

            # Should handle gracefully
            assert selected == []
            assert notes == ""


class TestLLMClientNarratives:
    """Tests for detect_narratives method."""

    def test_detect_narratives_empty(self):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='{"patterns": []}')]
            mock_client.messages.create.return_value = mock_response

            from shared.llm_client import LLMClient

            client = LLMClient(api_key="test-key")
            patterns = client.detect_narratives({})

            assert patterns == []

    def test_detect_narratives_with_patterns(self, sample_news_item):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            response_data = {
                "patterns": [
                    {
                        "title": "AI Regulation Wave",
                        "description": "Multiple sources discussing new AI regulations",
                        "sources": ["geopolitical", "ai-ml"],
                        "strength": 0.75,
                    }
                ]
            }
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps(response_data))]
            mock_client.messages.create.return_value = mock_response

            from shared.llm_client import LLMClient

            client = LLMClient(api_key="test-key")
            patterns = client.detect_narratives({"ai-ml": [sample_news_item]})

            assert len(patterns) == 1
            assert patterns[0].title == "AI Regulation Wave"
            assert patterns[0].strength == 0.75

    def test_detect_narratives_api_error(self, sample_news_item):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client
            mock_client.messages.create.side_effect = Exception("API Error")

            from shared.llm_client import LLMClient

            client = LLMClient(api_key="test-key")
            patterns = client.detect_narratives({"ai-ml": [sample_news_item]})

            # Should return empty list on error
            assert patterns == []


class TestLLMClientBreaking:
    """Tests for evaluate_breaking method."""

    def test_evaluate_breaking_yes(self, sample_news_item):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="YES")]
            mock_client.messages.create.return_value = mock_response

            from shared.llm_client import LLMClient

            client = LLMClient(api_key="test-key")
            result = client.evaluate_breaking(sample_news_item)

            assert result is True

    def test_evaluate_breaking_no(self, sample_news_item):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="NO")]
            mock_client.messages.create.return_value = mock_response

            from shared.llm_client import LLMClient

            client = LLMClient(api_key="test-key")
            result = client.evaluate_breaking(sample_news_item)

            assert result is False

    def test_evaluate_breaking_error(self, sample_news_item):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client
            mock_client.messages.create.side_effect = Exception("API Error")

            from shared.llm_client import LLMClient

            client = LLMClient(api_key="test-key")
            result = client.evaluate_breaking(sample_news_item)

            # Should return False on error
            assert result is False

    def test_evaluate_breaking_case_insensitive(self, sample_news_item):
        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="yes")]  # lowercase
            mock_client.messages.create.return_value = mock_response

            from shared.llm_client import LLMClient

            client = LLMClient(api_key="test-key")
            result = client.evaluate_breaking(sample_news_item)

            assert result is True
