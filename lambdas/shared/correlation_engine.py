"""
Correlation Engine for SIGINT

Matches tweet signals with news headlines to detect:
- Leading indicators (tweets precede news)
- Amplification patterns (news + tweet velocity)
- Divergent signals (high Twitter activity, no news coverage)
"""

import hashlib
import logging
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from .models import (
    Category,
    CorrelatedNarrative,
    NewsItem,
    TweetItem,
    VelocitySpike,
)

logger = logging.getLogger(__name__)

# Configuration
CORRELATION_CONFIG = {
    "velocity_window_minutes": 60,       # Window for velocity calculation
    "baseline_window_hours": 24,         # Baseline calculation window
    "spike_threshold": 2.0,              # Minimum magnitude to count as spike
    "entity_match_threshold": 0.3,       # Min Jaccard similarity for match
    "temporal_window_hours": 6,          # Max time gap for correlation
    "min_confidence": 0.4,               # Min confidence to report correlation
}


class CorrelationEngine:
    """
    Correlates tweet signals with news headlines for pattern detection.

    Key capabilities:
    - Calculate tweet velocity per entity (hashtags, mentions, keywords)
    - Detect velocity spikes against baseline
    - Match tweet entities with news article entities
    - Calculate lead/lag time between tweet spikes and news
    - Generate correlation confidence scores
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = {**CORRELATION_CONFIG, **(config or {})}

    def detect_correlations(
        self,
        tweets: list[TweetItem],
        news_items: list[NewsItem],
        category: Category | None = None,
    ) -> list[CorrelatedNarrative]:
        """
        Find correlations between tweet activity and news coverage.

        Returns narratives where:
        1. Tweet velocity spikes precede news (leading indicator)
        2. News breaks, tweets amplify (confirmation signal)
        3. Entity overlap between tweets and news (correlation)

        Args:
            tweets: Recent tweets from Twitter
            news_items: Recent news items
            category: Optional category filter

        Returns:
            List of CorrelatedNarrative objects
        """
        if not tweets or not news_items:
            return []

        # Extract entities from both sources
        tweet_entities = self._extract_tweet_entities(tweets)
        news_entities = self._extract_news_entities(news_items)

        # Calculate velocity spikes
        spikes = self.detect_velocity_spikes(tweets)

        # Find correlations
        correlations: list[CorrelatedNarrative] = []

        # 1. Entity-based correlations
        entity_correlations = self._correlate_by_entities(
            tweets, news_items, tweet_entities, news_entities
        )
        correlations.extend(entity_correlations)

        # 2. Spike-based correlations (leading indicators)
        spike_correlations = self._correlate_by_spikes(spikes, news_items)
        correlations.extend(spike_correlations)

        # Deduplicate by correlation_id
        seen_ids: set[str] = set()
        unique_correlations = []
        for corr in correlations:
            if corr.correlation_id not in seen_ids:
                seen_ids.add(corr.correlation_id)
                unique_correlations.append(corr)

        # Filter by minimum confidence
        min_confidence = self.config["min_confidence"]
        filtered = [c for c in unique_correlations if c.confidence_score >= min_confidence]

        # Sort by confidence
        filtered.sort(key=lambda c: c.confidence_score, reverse=True)

        logger.info(f"Found {len(filtered)} correlations from {len(tweets)} tweets and {len(news_items)} news items")
        return filtered

    def calculate_velocity(
        self,
        tweets: list[TweetItem],
        window_minutes: int | None = None,
    ) -> dict[str, float]:
        """
        Calculate tweet velocity per entity.

        Velocity = tweets per hour mentioning an entity.

        Args:
            tweets: Tweets to analyze
            window_minutes: Time window for calculation

        Returns:
            Dict of entity -> velocity (tweets/hour)
        """
        if not tweets:
            return {}

        window = window_minutes or self.config["velocity_window_minutes"]
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=window)

        # Filter to window
        recent_tweets = [t for t in tweets if t.created_at >= cutoff]
        if not recent_tweets:
            return {}

        # Count mentions per entity
        entity_counts: dict[str, int] = defaultdict(int)
        for tweet in recent_tweets:
            for entity in tweet.all_entities:
                entity_counts[entity.lower()] += 1

            # Also extract keywords from content
            for keyword in self._extract_keywords(tweet.content):
                entity_counts[keyword.lower()] += 1

        # Convert to velocity (per hour)
        hours = window / 60
        return {entity: count / hours for entity, count in entity_counts.items()}

    def detect_velocity_spikes(
        self,
        tweets: list[TweetItem],
        baseline_tweets: list[TweetItem] | None = None,
    ) -> list[VelocitySpike]:
        """
        Detect entities with velocity significantly above baseline.

        Args:
            tweets: Recent tweets (window for spike detection)
            baseline_tweets: Historical tweets for baseline (optional)

        Returns:
            List of VelocitySpike objects
        """
        if not tweets:
            return []

        # Calculate current velocity
        current_velocity = self.calculate_velocity(tweets)

        # Calculate baseline velocity (from older data or same data as approximation)
        if baseline_tweets:
            baseline_velocity = self.calculate_velocity(
                baseline_tweets,
                window_minutes=self.config["baseline_window_hours"] * 60,
            )
        else:
            # Approximate baseline from current data
            baseline_velocity = {
                entity: vel * 0.3  # Assume current is elevated
                for entity, vel in current_velocity.items()
            }

        # Find spikes
        spikes: list[VelocitySpike] = []
        threshold = self.config["spike_threshold"]
        now = datetime.now(UTC)

        for entity, velocity in current_velocity.items():
            baseline = baseline_velocity.get(entity, 0.1)  # Avoid division by zero
            magnitude = velocity / max(baseline, 0.1)

            if magnitude >= threshold:
                # Find sample tweets for this entity
                sample_ids = []
                for tweet in tweets:
                    if entity.lower() in [e.lower() for e in tweet.all_entities]:
                        sample_ids.append(tweet.tweet_id)
                    if len(sample_ids) >= 3:
                        break

                spike = VelocitySpike(
                    entity=entity,
                    velocity=velocity,
                    baseline_velocity=baseline,
                    magnitude=magnitude,
                    spike_start=now - timedelta(minutes=self.config["velocity_window_minutes"]),
                    spike_peak=now,
                    sample_tweet_ids=sample_ids,
                )
                spikes.append(spike)

        # Sort by magnitude
        spikes.sort(key=lambda s: s.magnitude, reverse=True)

        logger.debug(f"Detected {len(spikes)} velocity spikes")
        return spikes

    def _extract_tweet_entities(self, tweets: list[TweetItem]) -> dict[str, set[str]]:
        """
        Extract all entities from tweets, grouped by type.

        Returns:
            {
                "hashtags": set of hashtags,
                "mentions": set of mentions,
                "cashtags": set of cashtags,
                "keywords": set of extracted keywords,
            }
        """
        entities: dict[str, set[str]] = {
            "hashtags": set(),
            "mentions": set(),
            "cashtags": set(),
            "keywords": set(),
        }

        for tweet in tweets:
            entities["hashtags"].update(h.lower() for h in tweet.hashtags)
            entities["mentions"].update(m.lower() for m in tweet.mentions)
            entities["cashtags"].update(c.lower() for c in tweet.cashtags)
            entities["keywords"].update(self._extract_keywords(tweet.content))

        return entities

    def _extract_news_entities(self, news_items: list[NewsItem]) -> dict[str, set[str]]:
        """
        Extract entities from news items.

        Returns:
            {
                "entities": set of named entities,
                "keywords": set of extracted keywords,
            }
        """
        entities: dict[str, set[str]] = {
            "entities": set(),
            "keywords": set(),
        }

        for item in news_items:
            entities["entities"].update(e.lower() for e in item.entities)
            entities["keywords"].update(self._extract_keywords(item.title))
            entities["keywords"].update(self._extract_keywords(item.summary))

        return entities

    def _extract_keywords(self, text: str) -> set[str]:
        """
        Extract significant keywords from text.
        Focuses on capitalized words, product names, and tech terms.
        """
        if not text:
            return set()

        keywords: set[str] = set()

        # Extract capitalized phrases (likely names/products)
        caps_pattern = r'\b[A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*)*\b'
        for match in re.findall(caps_pattern, text):
            if len(match) > 2:  # Skip short words
                keywords.add(match.lower())

        # Extract quoted terms
        quoted_pattern = r'"([^"]+)"'
        for match in re.findall(quoted_pattern, text):
            keywords.add(match.lower())

        # Known AI/tech terms (case-insensitive)
        tech_terms = [
            "gpt", "claude", "gemini", "llama", "openai", "anthropic",
            "deepmind", "meta ai", "agi", "llm", "transformer",
            "neural", "machine learning", "deep learning",
        ]
        text_lower = text.lower()
        for term in tech_terms:
            if term in text_lower:
                keywords.add(term)

        return keywords

    def _correlate_by_entities(
        self,
        tweets: list[TweetItem],
        news_items: list[NewsItem],
        tweet_entities: dict[str, set[str]],
        news_entities: dict[str, set[str]],
    ) -> list[CorrelatedNarrative]:
        """
        Find correlations based on shared entities between tweets and news.
        """
        correlations: list[CorrelatedNarrative] = []

        # Combine all tweet entities
        all_tweet_entities = set()
        for entity_set in tweet_entities.values():
            all_tweet_entities.update(entity_set)

        # Combine all news entities
        all_news_entities = set()
        for entity_set in news_entities.values():
            all_news_entities.update(entity_set)

        # Find overlap
        shared_entities = all_tweet_entities & all_news_entities
        if not shared_entities:
            return []

        # Calculate Jaccard similarity
        jaccard = len(shared_entities) / len(all_tweet_entities | all_news_entities)

        if jaccard < self.config["entity_match_threshold"]:
            return []

        # Find tweets and news items that share entities
        matching_tweets = []
        for tweet in tweets:
            tweet_ents = set(e.lower() for e in tweet.all_entities)
            tweet_ents.update(self._extract_keywords(tweet.content))
            if tweet_ents & shared_entities:
                matching_tweets.append(tweet)

        matching_news = []
        for item in news_items:
            item_ents = set(e.lower() for e in item.entities)
            item_ents.update(self._extract_keywords(item.title))
            if item_ents & shared_entities:
                matching_news.append(item)

        if not matching_tweets or not matching_news:
            return []

        # Calculate temporal relationship
        earliest_tweet = min(t.created_at for t in matching_tweets)
        earliest_news = min(n.published_at for n in matching_news if n.published_at)

        if earliest_news:
            lead_lag_hours = (earliest_news - earliest_tweet).total_seconds() / 3600
        else:
            lead_lag_hours = None

        # Generate correlation
        correlation_id = hashlib.md5(
            ",".join(sorted(shared_entities)).encode()
        ).hexdigest()[:12]

        # Confidence based on jaccard + number of matches
        confidence = min(
            0.95,
            jaccard * 0.5 + (len(matching_tweets) / 10) * 0.25 + (len(matching_news) / 5) * 0.25
        )

        correlation = CorrelatedNarrative(
            correlation_id=f"entity_{correlation_id}",
            title=f"Correlation: {', '.join(list(shared_entities)[:3])}",
            tweet_ids=[t.tweet_id for t in matching_tweets[:10]],
            news_article_ids=[n.id for n in matching_news[:5]],
            keywords=list(shared_entities)[:10],
            hashtags=list(tweet_entities["hashtags"] & shared_entities),
            tweet_spike_time=earliest_tweet,
            news_publish_time=earliest_news,
            lead_lag_hours=lead_lag_hours,
            confidence_score=confidence,
            evidence_summary=f"Found {len(shared_entities)} shared entities across "
                           f"{len(matching_tweets)} tweets and {len(matching_news)} news items",
        )
        correlations.append(correlation)

        return correlations

    def _correlate_by_spikes(
        self,
        spikes: list[VelocitySpike],
        news_items: list[NewsItem],
    ) -> list[CorrelatedNarrative]:
        """
        Find correlations where tweet velocity spikes precede news.
        """
        correlations: list[CorrelatedNarrative] = []
        temporal_window = timedelta(hours=self.config["temporal_window_hours"])

        for spike in spikes[:5]:  # Top 5 spikes
            entity = spike.entity.lower()

            # Find news items mentioning this entity
            matching_news = []
            for item in news_items:
                item_text = f"{item.title} {item.summary}".lower()
                if entity in item_text or any(entity in e.lower() for e in item.entities):
                    if item.published_at:
                        # Check temporal proximity
                        time_diff = item.published_at - spike.spike_peak
                        if abs(time_diff) <= temporal_window:
                            matching_news.append(item)

            if not matching_news:
                continue

            earliest_news = min(n.published_at for n in matching_news if n.published_at)
            lead_lag_hours = (earliest_news - spike.spike_peak).total_seconds() / 3600

            # Higher confidence for leading indicators
            if lead_lag_hours > 0:  # Tweets preceded news
                confidence = min(0.9, 0.5 + spike.magnitude * 0.1 + len(matching_news) * 0.1)
            else:
                confidence = min(0.7, 0.3 + spike.magnitude * 0.1 + len(matching_news) * 0.1)

            correlation_id = hashlib.md5(f"{entity}_{spike.spike_peak}".encode()).hexdigest()[:12]

            correlation = CorrelatedNarrative(
                correlation_id=f"spike_{correlation_id}",
                title=f"Spike detected: {entity.upper()} ({spike.magnitude:.1f}x baseline)",
                tweet_ids=spike.sample_tweet_ids,
                news_article_ids=[n.id for n in matching_news[:5]],
                keywords=[entity],
                hashtags=[entity] if entity.startswith("#") else [],
                tweet_spike_time=spike.spike_peak,
                news_publish_time=earliest_news,
                lead_lag_hours=lead_lag_hours,
                confidence_score=confidence,
                amplification_factor=spike.magnitude,
                evidence_summary=f"Velocity spike of {spike.magnitude:.1f}x "
                               f"{'preceded' if lead_lag_hours > 0 else 'followed'} news by {abs(lead_lag_hours):.1f}h",
                questions=[
                    f"What triggered the {entity} spike?",
                    f"Is this part of a coordinated campaign?",
                ] if spike.magnitude > 3 else [],
            )
            correlations.append(correlation)

        return correlations

    def get_leading_indicators(
        self,
        correlations: list[CorrelatedNarrative],
    ) -> list[CorrelatedNarrative]:
        """
        Filter correlations to only leading indicators (tweets preceded news).
        """
        return [
            c for c in correlations
            if c.lead_lag_hours is not None and c.lead_lag_hours > 0
        ]

    def get_divergent_signals(
        self,
        tweets: list[TweetItem],
        news_items: list[NewsItem],
    ) -> list[VelocitySpike]:
        """
        Find velocity spikes with no corresponding news coverage.
        These may indicate breaking/emerging stories not yet in news.
        """
        spikes = self.detect_velocity_spikes(tweets)
        news_entities = self._extract_news_entities(news_items)
        all_news_entities = set()
        for entity_set in news_entities.values():
            all_news_entities.update(entity_set)

        divergent = []
        for spike in spikes:
            if spike.entity.lower() not in all_news_entities:
                divergent.append(spike)

        return divergent
