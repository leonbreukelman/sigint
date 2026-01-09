"""
SIGINT Feed Fetcher
Handles fetching and parsing RSS feeds and API endpoints
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import aiohttp
import feedparser

logger = logging.getLogger(__name__)


@dataclass
class RawFeedItem:
    """Raw item from a feed before AI processing"""

    id: str
    title: str
    link: str
    description: str
    source: str
    source_url: str
    published: datetime | None
    raw_data: dict[str, Any]


class FeedFetcher:
    """Async feed fetcher with caching and rate limiting"""

    def __init__(self, timeout: int = 30, max_concurrent: int = 10):
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)

    def _generate_id(self, url: str, title: str) -> str:
        """Generate unique ID from URL and title"""
        content = f"{url}:{title}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _parse_date(self, entry: dict) -> datetime | None:
        """Parse date from feed entry"""
        for field in ["published_parsed", "updated_parsed", "created_parsed"]:
            if field in entry and entry[field]:
                try:
                    import time

                    return datetime.fromtimestamp(time.mktime(entry[field]), tz=UTC)
                except (TypeError, ValueError, OverflowError):
                    pass
        return None

    def _get_source_name(self, url: str) -> str:
        """Extract readable source name from URL"""
        source_map = {
            "bbc.co.uk": "BBC",
            "npr.org": "NPR",
            "theguardian.com": "The Guardian",
            "reuters": "Reuters",
            "hnrss.org": "Hacker News",
            "arstechnica.com": "Ars Technica",
            "theverge.com": "The Verge",
            "technologyreview.com": "MIT Tech Review",
            "arxiv.org": "ArXiv",
            "openai.com": "OpenAI",
            "anthropic.com": "Anthropic",
            "blog.google": "Google AI",
            "deepmind": "DeepMind",
            "ai.meta.com": "Meta AI",
            "huggingface.co": "Hugging Face",
            "cnbc.com": "CNBC",
            "marketwatch.com": "MarketWatch",
            "yahoo.com": "Yahoo Finance",
            "ft.com": "Financial Times",
            "whitehouse.gov": "White House",
            "federalreserve.gov": "Federal Reserve",
            "sec.gov": "SEC",
            "treasury.gov": "Treasury",
            "state.gov": "State Dept",
            "csis.org": "CSIS",
            "brookings.edu": "Brookings",
            "cfr.org": "CFR",
            "defenseone.com": "Defense One",
            "warontherocks.com": "War on the Rocks",
            "breakingdefense.com": "Breaking Defense",
            "thedrive.com": "The War Zone",
            "thediplomat.com": "The Diplomat",
            "al-monitor.com": "Al-Monitor",
            "bellingcat.com": "Bellingcat",
            "defense.gov": "DoD",
            "cisa.gov": "CISA",
            "krebsonsecurity.com": "Krebs on Security",
            "coingecko.com": "CoinGecko",
            "polymarket.com": "Polymarket",
        }

        url_lower = url.lower()
        for domain, name in source_map.items():
            if domain in url_lower:
                return name

        # Fallback: extract domain
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            return parsed.netloc.replace("www.", "").split(".")[0].title()
        except Exception:
            return "Unknown"

    async def _fetch_url(self, session: aiohttp.ClientSession, url: str) -> str | None:
        """Fetch a single URL with semaphore limiting"""
        async with self.semaphore:
            try:
                # Strip CORS proxy prefixes for direct fetching
                clean_url = url
                for proxy in ["https://corsproxy.io/?", "https://api.allorigins.win/raw?url="]:
                    if url.startswith(proxy):
                        clean_url = url[len(proxy) :]
                        break

                async with session.get(
                    clean_url, timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        logger.warning(f"HTTP {response.status} for {clean_url}")
                        return None
            except TimeoutError:
                logger.warning(f"Timeout fetching {url}")
                return None
            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")
                return None

    def _parse_rss(self, content: str, source_url: str) -> list[RawFeedItem]:
        """Parse RSS/Atom feed content"""
        items = []
        try:
            feed = feedparser.parse(content)
            source_name = self._get_source_name(source_url)

            for entry in feed.entries[:50]:  # Limit to 50 items per feed
                title = entry.get("title", "").strip()
                link = entry.get("link", "")

                if not title or not link:
                    continue

                description = ""
                if "summary" in entry:
                    description = entry.summary
                elif "description" in entry:
                    description = entry.description
                elif "content" in entry and entry.content:
                    description = entry.content[0].get("value", "")

                # Strip HTML tags from description
                import re

                description = re.sub(r"<[^>]+>", "", description)[:500]

                item = RawFeedItem(
                    id=self._generate_id(link, title),
                    title=title,
                    link=link,
                    description=description,
                    source=source_name,
                    source_url=source_url,
                    published=self._parse_date(entry),
                    raw_data=dict(entry),
                )
                items.append(item)
        except Exception as e:
            logger.error(f"Error parsing RSS from {source_url}: {e}")

        return items

    def _parse_json_api(self, content: str, source_url: str) -> list[RawFeedItem]:
        """Parse JSON API responses (Yahoo Finance, CoinGecko, etc.)"""
        items = []
        try:
            data = json.loads(content)
            source_name = self._get_source_name(source_url)

            # Handle different API formats
            if "chart" in data and "result" in data["chart"]:
                # Yahoo Finance chart data
                result = data["chart"]["result"][0]
                meta = result.get("meta", {})
                symbol = meta.get("symbol", "Unknown")
                price = meta.get("regularMarketPrice", 0)
                change = meta.get("regularMarketChangePercent", 0)

                item = RawFeedItem(
                    id=self._generate_id(source_url, symbol),
                    title=f"{symbol}: ${price:.2f} ({change:+.2f}%)",
                    link=f"https://finance.yahoo.com/quote/{symbol}",
                    description=f"Market price for {symbol}",
                    source=source_name,
                    source_url=source_url,
                    published=datetime.now(UTC),
                    raw_data={"symbol": symbol, "price": price, "change": change},
                )
                items.append(item)

            elif "bitcoin" in data or "ethereum" in data:
                # CoinGecko format
                for coin, info in data.items():
                    if isinstance(info, dict) and "usd" in info:
                        price = info.get("usd", 0)
                        change = info.get("usd_24h_change", 0)

                        item = RawFeedItem(
                            id=self._generate_id(source_url, coin),
                            title=f"{coin.title()}: ${price:,.2f} ({change:+.2f}%)",
                            link=f"https://coingecko.com/en/coins/{coin}",
                            description=f"24h price for {coin}",
                            source="CoinGecko",
                            source_url=source_url,
                            published=datetime.now(UTC),
                            raw_data={"coin": coin, "price": price, "change": change},
                        )
                        items.append(item)

            elif isinstance(data, list) and len(data) > 0:
                # Check if it's CoinGecko markets API format
                first_item = data[0]
                if isinstance(first_item, dict) and "current_price" in first_item:
                    # CoinGecko /coins/markets format
                    for coin_data in data[:20]:
                        name = coin_data.get("name", "Unknown")
                        symbol = coin_data.get("symbol", "???").upper()
                        price = coin_data.get("current_price", 0)
                        change = coin_data.get("price_change_percentage_24h", 0) or 0
                        
                        item = RawFeedItem(
                            id=self._generate_id(source_url, symbol),
                            title=f"{name}: ${price:,.2f} ({change:+.2f}%)",
                            link=f"https://coingecko.com/en/coins/{coin_data.get('id', '')}",
                            description=f"24h price for {name} ({symbol})",
                            source="CoinGecko",
                            source_url=source_url,
                            published=datetime.now(UTC),
                            raw_data={"symbol": symbol, "price": price, "change": change},
                        )
                        items.append(item)
                else:
                    # Polymarket or generic list format
                    for item_data in data[:25]:
                        if isinstance(item_data, dict):
                            title = (
                                item_data.get("question")
                                or item_data.get("title")
                                or item_data.get("name", "")
                            )
                            link = item_data.get("url") or item_data.get("link", source_url)
                            desc = item_data.get("description", "")[:500]

                            if title:
                                item = RawFeedItem(
                                    id=self._generate_id(link, title),
                                    title=title,
                                    link=link,
                                    description=desc,
                                    source=source_name,
                                    source_url=source_url,
                                    published=datetime.now(UTC),
                                    raw_data=item_data,
                                )
                                items.append(item)

        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from {source_url}")
        except Exception as e:
            logger.error(f"Error parsing JSON from {source_url}: {e}")

        return items

    async def fetch_feeds(self, feed_urls: list[str]) -> list[RawFeedItem]:
        """Fetch multiple feeds concurrently"""
        all_items = []

        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch_url(session, url) for url in feed_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for url, result in zip(feed_urls, results):
                if isinstance(result, Exception):
                    logger.error(f"Exception fetching {url}: {result}")
                    continue

                if result is None:
                    continue

                # Determine if RSS or JSON
                content = result.strip()
                if (
                    content.startswith("<?xml")
                    or content.startswith("<rss")
                    or content.startswith("<feed")
                ):
                    items = self._parse_rss(content, url)
                elif content.startswith("{") or content.startswith("["):
                    items = self._parse_json_api(content, url)
                else:
                    # Try RSS parser as fallback
                    items = self._parse_rss(content, url)

                all_items.extend(items)

        # Deduplicate by ID
        seen = set()
        unique_items = []
        for item in all_items:
            if item.id not in seen:
                seen.add(item.id)
                unique_items.append(item)

        return unique_items

    def fetch_feeds_sync(self, feed_urls: list[str]) -> list[RawFeedItem]:
        """Synchronous wrapper for Lambda"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            return asyncio.run(self.fetch_feeds(feed_urls))
        else:
            # Event loop already running (e.g., in Lambda), use nest_asyncio pattern
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.fetch_feeds(feed_urls))
                return future.result()
