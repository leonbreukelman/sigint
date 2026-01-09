"""
SIGINT Feed Fetcher
Handles fetching and parsing RSS feeds and API endpoints
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
            # Major news outlets
            "bbc.co.uk": "BBC",
            "npr.org": "NPR",
            "theguardian.com": "The Guardian",
            "reuters": "Reuters",
            "nytimes.com": "NYT",
            "washingtonpost.com": "WaPo",
            "aljazeera.com": "Al Jazeera",
            "wsj.com": "WSJ",
            "bloomberg.com": "Bloomberg",
            # Tech news
            "hnrss.org": "Hacker News",
            "arstechnica.com": "Ars Technica",
            "theverge.com": "The Verge",
            "technologyreview.com": "MIT Tech Review",
            "wired.com": "Wired",
            "venturebeat.com": "VentureBeat",
            "spectrum.ieee.org": "IEEE Spectrum",
            "quantamagazine.org": "Quanta",
            "anandtech.com": "AnandTech",
            "tomshardware.com": "Tom's Hardware",
            "semiengineering.com": "SemiEngineering",
            "nextplatform.com": "Next Platform",
            "semianalysis.com": "SemiAnalysis",
            "phys.org": "Phys.org",
            # Research
            "arxiv.org": "ArXiv",
            "thegradient.pub": "The Gradient",
            "marktechpost.com": "MarkTechPost",
            "lastweekin.ai": "Last Week in AI",
            "jack-clark.net": "Import AI",
            # AI companies
            "openai.com": "OpenAI",
            "anthropic.com": "Anthropic",
            "blog.google": "Google AI",
            "deepmind": "DeepMind",
            "ai.meta.com": "Meta AI",
            "huggingface.co": "Hugging Face",
            "blogs.microsoft.com": "Microsoft AI",
            "aws.amazon.com": "AWS ML",
            # Finance
            "cnbc.com": "CNBC",
            "marketwatch.com": "MarketWatch",
            "yahoo.com": "Yahoo Finance",
            "ft.com": "Financial Times",
            "ecb.europa.eu": "ECB",
            # Crypto
            "decrypt.co": "Decrypt",
            "coindesk.com": "CoinDesk",
            "thedefiant.io": "The Defiant",
            "theblock.co": "The Block",
            "dlnews.com": "DL News",
            "cointelegraph.com": "Cointelegraph",
            "banklesshq.com": "Bankless",
            "messari.io": "Messari",
            "coingecko.com": "CoinGecko",
            "polymarket.com": "Polymarket",
            "metaculus.com": "Metaculus",
            # Government & regulators
            "whitehouse.gov": "White House",
            "federalreserve.gov": "Federal Reserve",
            "sec.gov": "SEC",
            "treasury.gov": "Treasury",
            "state.gov": "State Dept",
            "cisa.gov": "CISA",
            "defense.gov": "DoD",
            # Think tanks & analysis
            "csis.org": "CSIS",
            "brookings.edu": "Brookings",
            "cfr.org": "CFR",
            "carnegieendowment.org": "Carnegie",
            "rand.org": "RAND",
            "rusi.org": "RUSI",
            "iiss.org": "IISS",
            "aspistrategist.org.au": "ASPI",
            # Defense
            "defenseone.com": "Defense One",
            "warontherocks.com": "War on the Rocks",
            "breakingdefense.com": "Breaking Defense",
            "thedrive.com": "The War Zone",
            "defensenews.com": "Defense News",
            # Regional
            "thediplomat.com": "The Diplomat",
            "al-monitor.com": "Al-Monitor",
            "foreignpolicy.com": "Foreign Policy",
            "euractiv.com": "Euractiv",
            # OSINT
            "bellingcat.com": "Bellingcat",
            "krebsonsecurity.com": "Krebs on Security",
            # Life sciences & space
            "statnews.com": "STAT News",
            "fiercebiotech.com": "FierceBiotech",
            "spacenews.com": "SpaceNews",
            "canarymedia.com": "Canary Media",
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

            # Handle Metaculus dict format with "results" key
            elif isinstance(data, dict) and "metaculus" in source_url.lower():
                items.extend(self._parse_metaculus(data, source_url, source_name))

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
                    # Check for Polymarket format
                    if "polymarket" in source_url.lower() and isinstance(data, list):
                        items.extend(self._parse_polymarket(data, source_url, source_name))
                    # Check for Metaculus format (list format)
                    elif "metaculus" in source_url.lower():
                        items.extend(self._parse_metaculus(data, source_url, source_name))
                    else:
                        # Generic list format
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

    def _parse_polymarket(
        self, data: list, source_url: str, source_name: str
    ) -> list[RawFeedItem]:
        """Parse Polymarket API response with probability data."""
        # Skip sports, esports, and trivial questions
        SKIP_PATTERNS = [
            "win on 2026", "win on 2025", "win the 202",  # Sports matches
            "NCAA", "NFL", "NBA", "MLB", "Premier League", "Champions League",
            "Serie A", "La Liga", "Bundesliga", "MLS",
            "Team Liquid", "Kill Handicap", "FDV above",  # Esports/crypto trivial
            "say \"Peanut\"", "say Peanut",  # Trivial Trump quotes
        ]
        
        items = []
        for market in data[:50]:  # Check more, filter more
            if not isinstance(market, dict):
                continue
            
            question = market.get("question", "")
            if not question:
                continue
            
            # Skip irrelevant questions
            if any(pattern.lower() in question.lower() for pattern in SKIP_PATTERNS):
                continue
            
            # Extract probability from outcomePrices (JSON string like '["0.65","0.35"]')
            probability = None
            outcome_prices = market.get("outcomePrices")
            if outcome_prices:
                try:
                    if isinstance(outcome_prices, str):
                        prices = json.loads(outcome_prices)
                    else:
                        prices = outcome_prices
                    if prices and len(prices) > 0:
                        probability = float(prices[0])  # First outcome (usually "Yes")
                except (json.JSONDecodeError, ValueError, IndexError):
                    pass
            
            # Format volume
            volume_raw = market.get("volume") or market.get("volumeNum") or 0
            try:
                volume_num = float(volume_raw)
                if volume_num >= 1_000_000:
                    volume = f"${volume_num / 1_000_000:.1f}M"
                elif volume_num >= 1_000:
                    volume = f"${volume_num / 1_000:.1f}K"
                else:
                    volume = f"${volume_num:.0f}"
            except (ValueError, TypeError):
                volume = None
            
            # Build description with probability
            prob_str = f"{probability * 100:.0f}%" if probability else "N/A"
            desc = f"Probability: {prob_str}"
            if volume:
                desc += f" | Volume: {volume}"
            if market.get("endDate"):
                desc += f" | Ends: {market.get('endDate', '')[:10]}"
            
            # Store market data in raw_data for LLM matching
            market_data = {
                **market,
                "_parsed_probability": probability,
                "_parsed_volume": volume,
                "_market_type": "prediction",
                "_source": "Polymarket",
            }
            
            item = RawFeedItem(
                id=self._generate_id(source_url, question),
                title=f"📊 {question}",
                link=market.get("url") or f"https://polymarket.com",
                description=desc,
                source="Polymarket",
                source_url=source_url,
                published=datetime.now(UTC),
                raw_data=market_data,
            )
            items.append(item)
        
        logger.info(f"Parsed {len(items)} Polymarket markets")
        return items

    def _parse_metaculus(
        self, data: dict | list, source_url: str, source_name: str
    ) -> list[RawFeedItem]:
        """Parse Metaculus API response with probability data."""
        items = []
        
        # Metaculus returns {"results": [...]} or just a list
        questions = data.get("results", data) if isinstance(data, dict) else data
        if not isinstance(questions, list):
            return items
        
        for question in questions[:30]:
            if not isinstance(question, dict):
                continue
            
            title = question.get("title", "")
            if not title:
                continue
            
            # Extract probability from community prediction
            probability = None
            prediction = question.get("community_prediction", {})
            if isinstance(prediction, dict):
                probability = prediction.get("full", {}).get("q2")  # Median
                if probability is None:
                    probability = prediction.get("y")  # Alternative field
            
            # Get question URL
            question_id = question.get("id")
            url = f"https://www.metaculus.com/questions/{question_id}/" if question_id else source_url
            
            # Build description
            prob_str = f"{probability * 100:.0f}%" if probability else "N/A"
            desc = f"Community prediction: {prob_str}"
            if question.get("resolution_criteria"):
                desc += f" | {question.get('resolution_criteria', '')[:100]}"
            
            # Store market data
            market_data = {
                **question,
                "_parsed_probability": probability,
                "_market_type": "prediction",
                "_source": "Metaculus",
            }
            
            item = RawFeedItem(
                id=self._generate_id(url, title),
                title=f"🔮 {title}",
                link=url,
                description=desc,
                source="Metaculus",
                source_url=source_url,
                published=datetime.now(UTC),
                raw_data=market_data,
            )
            items.append(item)
        
        logger.info(f"Parsed {len(items)} Metaculus questions")
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

    def filter_by_age(
        self, items: list[RawFeedItem], max_age_hours: int = 24
    ) -> list[RawFeedItem]:
        """Filter items to only include those within max_age_hours.
        
        Args:
            items: List of raw feed items to filter
            max_age_hours: Maximum age in hours (default 24, max 720 for 30 days)
        
        Returns:
            Filtered list containing only items within the age threshold.
            Items with no published date are included (benefit of doubt).
        """
        # Clamp max_age_hours to valid range
        max_age_hours = max(1, min(max_age_hours, 720))
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        
        filtered = []
        for item in items:
            # Include items with no published date (benefit of doubt)
            if item.published is None:
                filtered.append(item)
            elif item.published > cutoff:
                filtered.append(item)
        
        logger.info(
            f"Age filter: {len(items)} items -> {len(filtered)} items "
            f"(cutoff: {max_age_hours}h)"
        )
        return filtered

    def _jaccard_similarity(self, str1: str, str2: str) -> float:
        """Calculate Jaccard similarity between two strings."""
        # Normalize: lowercase, split on non-alphanumeric
        import re
        words1 = set(re.findall(r'\w+', str1.lower()))
        words2 = set(re.findall(r'\w+', str2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)

    def filter_similar_titles(
        self, items: list[RawFeedItem], similarity_threshold: float = 0.7
    ) -> list[RawFeedItem]:
        """Remove items with highly similar titles to reduce redundancy.
        
        Uses Jaccard similarity on word sets. Keeps the first occurrence
        (typically from higher-priority sources).
        
        Args:
            items: List of raw feed items to filter
            similarity_threshold: Jaccard threshold above which items are considered duplicates
        
        Returns:
            Filtered list with similar titles removed.
        """
        if not items:
            return items
        
        filtered = []
        for item in items:
            is_similar = False
            for kept_item in filtered:
                similarity = self._jaccard_similarity(item.title, kept_item.title)
                if similarity >= similarity_threshold:
                    is_similar = True
                    break
            
            if not is_similar:
                filtered.append(item)
        
        removed = len(items) - len(filtered)
        if removed > 0:
            logger.info(
                f"Title similarity filter: {len(items)} -> {len(filtered)} items "
                f"(removed {removed} similar titles)"
            )
        return filtered

    def limit_per_source(
        self, items: list[RawFeedItem], max_per_source: int = 5
    ) -> list[RawFeedItem]:
        """Limit items per source for diversity.
        
        Args:
            items: List of raw feed items to filter
            max_per_source: Maximum items to keep from each source
        
        Returns:
            Filtered list with source limits applied.
        """
        source_counts: dict[str, int] = {}
        filtered = []
        
        for item in items:
            count = source_counts.get(item.source, 0)
            if count < max_per_source:
                filtered.append(item)
                source_counts[item.source] = count + 1
        
        removed = len(items) - len(filtered)
        if removed > 0:
            logger.info(
                f"Source diversity filter: {len(items)} -> {len(filtered)} items "
                f"(max {max_per_source}/source)"
            )
        return filtered

    def apply_pre_llm_filters(
        self,
        items: list[RawFeedItem],
        max_age_hours: int = 24,
        similarity_threshold: float = 0.7,
        max_per_source: int = 5,
    ) -> list[RawFeedItem]:
        """Apply all pre-LLM filters in optimal order.
        
        Order: age filter -> dedup (already done) -> title similarity -> source diversity
        
        Args:
            items: List of raw feed items to filter
            max_age_hours: Maximum age in hours
            similarity_threshold: Jaccard threshold for title similarity
            max_per_source: Maximum items per source
        
        Returns:
            Filtered list ready for LLM processing.
        """
        original_count = len(items)
        
        # 1. Age filter
        items = self.filter_by_age(items, max_age_hours)
        
        # 2. Title similarity (removes near-duplicates across sources)
        items = self.filter_similar_titles(items, similarity_threshold)
        
        # 3. Source diversity (prevents any one source from dominating)
        items = self.limit_per_source(items, max_per_source)
        
        logger.info(
            f"Pre-LLM filtering complete: {original_count} -> {len(items)} items"
        )
        return items
