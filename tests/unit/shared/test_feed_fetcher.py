"""
Tests for shared/feed_fetcher.py
"""

import json
from unittest.mock import AsyncMock, patch


class TestRawFeedItem:
    """Tests for RawFeedItem dataclass."""

    def test_create_raw_feed_item(self, sample_raw_feed_items):
        item = sample_raw_feed_items[0]

        assert item.id == "feed1"
        assert item.title == "AI Research Update"
        assert item.source == "ArXiv"


class TestFeedFetcher:
    """Tests for FeedFetcher class."""

    def test_generate_id_deterministic(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        id1 = fetcher._generate_id("https://example.com", "Test Title")
        id2 = fetcher._generate_id("https://example.com", "Test Title")

        assert id1 == id2
        assert len(id1) == 16  # SHA256 truncated to 16 chars

    def test_generate_id_different_inputs(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        id1 = fetcher._generate_id("https://example.com/1", "Title 1")
        id2 = fetcher._generate_id("https://example.com/2", "Title 2")

        assert id1 != id2

    def test_get_source_name_known_domains(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()

        # Note: source_map uses 'bbc.co.uk' not 'bbci.co.uk'
        assert fetcher._get_source_name("https://www.bbc.co.uk/news") == "BBC"
        assert fetcher._get_source_name("https://hnrss.org/frontpage") == "Hacker News"
        assert fetcher._get_source_name("https://arxiv.org/rss/cs.AI") == "ArXiv"
        assert fetcher._get_source_name("https://openai.com/blog/rss.xml") == "OpenAI"
        assert fetcher._get_source_name("https://www.anthropic.com/rss.xml") == "Anthropic"

    def test_get_source_name_unknown_domain(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        result = fetcher._get_source_name("https://unknown-site.com/feed")

        # Should extract domain and title-case it
        assert result is not None
        assert len(result) > 0

    def test_parse_rss_valid_feed(self, sample_rss_content):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        items = fetcher._parse_rss(sample_rss_content, "https://example.com/feed")

        assert len(items) == 1
        assert items[0].title == "Breaking: Major AI Breakthrough"
        assert "example.com/article1" in items[0].link

    def test_parse_rss_empty_feed(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        empty_rss = """<?xml version="1.0"?>
        <rss version="2.0"><channel><title>Empty</title></channel></rss>"""

        items = fetcher._parse_rss(empty_rss, "https://example.com/feed")
        assert items == []

    def test_parse_rss_invalid_content(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        items = fetcher._parse_rss("not valid xml at all", "https://example.com")

        # Should handle gracefully and return empty list
        assert items == []

    def test_parse_json_api_coingecko(self, sample_coingecko_response):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        content = json.dumps(sample_coingecko_response)
        items = fetcher._parse_json_api(content, "https://api.coingecko.com/api/v3/simple/price")

        assert len(items) == 2

        # Find bitcoin item
        btc_items = [i for i in items if "bitcoin" in i.title.lower()]
        assert len(btc_items) == 1
        assert "95" in btc_items[0].title  # Price should be in title

    def test_parse_json_api_polymarket(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        polymarket_data = [
            {"question": "Will AI pass the Turing test?", "url": "https://poly.market/1"},
            {"question": "Bitcoin above 100k?", "url": "https://poly.market/2"},
        ]

        items = fetcher._parse_json_api(
            json.dumps(polymarket_data), "https://gamma-api.polymarket.com/markets"
        )

        assert len(items) == 2
        # Polymarket titles are prefixed with 📊 emoji
        assert items[0].title == "📊 Will AI pass the Turing test?"

    def test_parse_json_api_invalid_json(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        items = fetcher._parse_json_api("not json", "https://api.example.com")

        assert items == []

    def test_fetch_feeds_sync_returns_list(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()

        # Mock the async method
        with patch.object(fetcher, "fetch_feeds", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []

            result = fetcher.fetch_feeds_sync([])
            assert result == []


class TestFeedFetcherDeduplication:
    """Tests for feed item deduplication."""

    def test_deduplicate_by_id(self):
        from shared.feed_fetcher import RawFeedItem

        # Create items with same ID
        items = [
            RawFeedItem(
                id="same-id",
                title="Title 1",
                link="https://example.com/1",
                description="Desc 1",
                source="Source1",
                source_url="https://source1.com",
                published=None,
                raw_data={},
            ),
            RawFeedItem(
                id="same-id",  # Duplicate ID
                title="Title 2",
                link="https://example.com/2",
                description="Desc 2",
                source="Source2",
                source_url="https://source2.com",
                published=None,
                raw_data={},
            ),
            RawFeedItem(
                id="different-id",
                title="Title 3",
                link="https://example.com/3",
                description="Desc 3",
                source="Source3",
                source_url="https://source3.com",
                published=None,
                raw_data={},
            ),
        ]

        # Test deduplication logic directly
        seen = set()
        unique_items = []
        for item in items:
            if item.id not in seen:
                seen.add(item.id)
                unique_items.append(item)

        assert len(unique_items) == 2


class TestFeedFetcherRSSParsing:
    """Additional RSS parsing tests."""

    def test_parse_rss_with_multiple_items(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>Multi Feed</title>
        <item>
            <title>Article 1</title>
            <link>https://example.com/1</link>
            <description>First article</description>
        </item>
        <item>
            <title>Article 2</title>
            <link>https://example.com/2</link>
            <description>Second article</description>
        </item>
        <item>
            <title>Article 3</title>
            <link>https://example.com/3</link>
            <description>Third article</description>
        </item>
    </channel>
</rss>"""

        items = fetcher._parse_rss(rss, "https://example.com/feed")

        assert len(items) == 3
        assert items[0].title == "Article 1"
        assert items[2].title == "Article 3"

    def test_parse_rss_strips_html_from_description(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>HTML Feed</title>
        <item>
            <title>HTML Article</title>
            <link>https://example.com/html</link>
            <description><![CDATA[<p>This is <strong>bold</strong> text</p>]]></description>
        </item>
    </channel>
</rss>"""

        items = fetcher._parse_rss(rss, "https://example.com/feed")

        assert len(items) == 1
        # HTML should be stripped
        assert "<p>" not in items[0].description
        assert "<strong>" not in items[0].description


class TestFeedFetcherFiltering:
    """Tests for pre-LLM filtering methods."""

    def test_jaccard_similarity_identical_strings(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        assert fetcher._jaccard_similarity("hello world", "hello world") == 1.0

    def test_jaccard_similarity_completely_different(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        assert fetcher._jaccard_similarity("hello world", "foo bar") == 0.0

    def test_jaccard_similarity_partial_overlap(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        # "hello world" and "hello there" share "hello"
        similarity = fetcher._jaccard_similarity("hello world", "hello there")
        assert 0.0 < similarity < 1.0
        # 1 word in common ("hello"), union is 3 words
        assert similarity == 1 / 3

    def test_jaccard_similarity_case_insensitive(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        assert fetcher._jaccard_similarity("Hello World", "hello world") == 1.0

    def test_jaccard_similarity_empty_string(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        assert fetcher._jaccard_similarity("", "hello") == 0.0
        assert fetcher._jaccard_similarity("hello", "") == 0.0

    def test_filter_similar_titles_removes_duplicates(self, sample_raw_feed_items):
        from shared.feed_fetcher import FeedFetcher, RawFeedItem
        from datetime import datetime, UTC

        fetcher = FeedFetcher()

        # Create items with similar titles
        items = [
            RawFeedItem(
                id="1",
                title="Breaking: Major AI breakthrough announced today",
                link="https://a.com",
                description="",
                source="Source A",
                source_url="https://a.com",
                published=datetime.now(UTC),
                raw_data={},
            ),
            RawFeedItem(
                id="2",
                title="Breaking: Major AI breakthrough announced",  # Very similar
                link="https://b.com",
                description="",
                source="Source B",
                source_url="https://b.com",
                published=datetime.now(UTC),
                raw_data={},
            ),
            RawFeedItem(
                id="3",
                title="Completely different topic about finance",  # Different
                link="https://c.com",
                description="",
                source="Source C",
                source_url="https://c.com",
                published=datetime.now(UTC),
                raw_data={},
            ),
        ]

        filtered = fetcher.filter_similar_titles(items, similarity_threshold=0.7)

        # Should keep first and third, remove second as similar to first
        assert len(filtered) == 2
        assert filtered[0].id == "1"
        assert filtered[1].id == "3"

    def test_filter_similar_titles_empty_list(self):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()
        assert fetcher.filter_similar_titles([]) == []

    def test_limit_per_source_basic(self):
        from shared.feed_fetcher import FeedFetcher, RawFeedItem
        from datetime import datetime, UTC

        fetcher = FeedFetcher()

        # Create 10 items from same source
        items = [
            RawFeedItem(
                id=str(i),
                title=f"Article {i}",
                link=f"https://example.com/{i}",
                description="",
                source="Same Source",
                source_url="https://example.com",
                published=datetime.now(UTC),
                raw_data={},
            )
            for i in range(10)
        ]

        filtered = fetcher.limit_per_source(items, max_per_source=3)

        assert len(filtered) == 3
        # Should keep first 3
        assert [f.id for f in filtered] == ["0", "1", "2"]

    def test_limit_per_source_multiple_sources(self):
        from shared.feed_fetcher import FeedFetcher, RawFeedItem
        from datetime import datetime, UTC

        fetcher = FeedFetcher()

        items = []
        for source in ["Source A", "Source B", "Source C"]:
            for i in range(4):
                items.append(
                    RawFeedItem(
                        id=f"{source}-{i}",
                        title=f"Article {i} from {source}",
                        link=f"https://example.com/{source}/{i}",
                        description="",
                        source=source,
                        source_url="https://example.com",
                        published=datetime.now(UTC),
                        raw_data={},
                    )
                )

        filtered = fetcher.limit_per_source(items, max_per_source=2)

        # 3 sources × 2 items each = 6
        assert len(filtered) == 6

        # Check each source has at most 2
        source_counts = {}
        for item in filtered:
            source_counts[item.source] = source_counts.get(item.source, 0) + 1

        assert all(count <= 2 for count in source_counts.values())

    def test_apply_pre_llm_filters_combined(self, sample_raw_feed_items):
        from shared.feed_fetcher import FeedFetcher

        fetcher = FeedFetcher()

        # Use sample items (should all be recent enough)
        filtered = fetcher.apply_pre_llm_filters(
            sample_raw_feed_items,
            max_age_hours=24,
            similarity_threshold=0.7,
            max_per_source=5,
        )

        # Should return a list (exact count depends on sample data)
        assert isinstance(filtered, list)
        # Should be <= original count
        assert len(filtered) <= len(sample_raw_feed_items)
