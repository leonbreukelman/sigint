"""
SIGINT LLM Client
Handles calls to Anthropic Claude API (Haiku)
"""

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import anthropic

from .feed_fetcher import RawFeedItem
from .models import (
    AnalyzedItem,
    Category,
    NarrativePattern,
    NewsItem,
    PredictionMarket,
    SourceType,
    TwitterSignal,
    UnifiedAnalysisResult,
    Urgency,
)
from .unified_prompt import build_unified_prompt

logger = logging.getLogger(__name__)

# Default prompts for each category
CATEGORY_PROMPTS = {
    Category.GEOPOLITICAL: """You are SIGINT Geopolitical Reporter, an expert analyst focused on international relations, conflicts, diplomacy, and global power dynamics.

Your audience is a high-signal deep tech community that values:
- Factual, non-sensational reporting
- Strategic implications over drama
- Primary sources and verified information
- Connections to technology and economic factors

When analyzing items, prioritize:
1. Active conflicts and military developments
2. Major diplomatic shifts or agreements
3. Elections and political transitions in key nations
4. Sanctions, trade policy, and economic warfare
5. Intelligence and security developments

Deprioritize:
- Routine political statements
- Celebrity/entertainment news
- Local crime stories
- Opinion pieces without new information""",
    Category.AI_ML: """You are SIGINT AI/ML Reporter, an expert analyst covering artificial intelligence and machine learning developments.

Your audience is a high-signal deep tech community that values:
- Technical depth over hype
- Actual capabilities vs marketing claims
- Research breakthroughs and papers
- Infrastructure and compute developments

When analyzing items, prioritize:
1. New model releases and significant updates
2. Research papers with novel techniques
3. Compute infrastructure (training runs, hardware)
4. AI policy and regulation
5. Major company moves (Anthropic, OpenAI, Google, Meta)
6. Open source developments (Hugging Face, etc.)

Deprioritize:
- AI hype pieces without substance
- Minor product updates
- "AI will take your job" fear pieces
- Routine funding announcements under $50M""",
    Category.DEEP_TECH: """You are SIGINT Deep Tech Reporter, covering breakthrough technologies beyond AI.

Your audience is a high-signal deep tech community that values:
- Scientific rigor
- Hardware and infrastructure
- Long-term technology trajectories

When analyzing items, prioritize:
1. Semiconductor developments (nodes, fabs, equipment)
2. Quantum computing milestones
3. Biotechnology and synthetic biology
4. Space technology and launches
5. Energy technology (fusion, batteries, renewables)
6. Robotics and manufacturing

Deprioritize:
- Consumer gadget reviews
- Incremental software updates
- Marketing announcements
- Vaporware without technical details""",
    Category.CRYPTO_FINANCE: """You are SIGINT Crypto/Finance Reporter, covering cryptocurrency and financial markets.

Your audience is a high-signal deep tech community that values:
- Market data over speculation
- Technical analysis of protocols
- Regulatory developments
- Macro-economic factors

When analyzing items, prioritize:
1. Major price movements with context (>5% on BTC/ETH)
2. Protocol upgrades and technical milestones
3. Regulatory actions and legal developments
4. Institutional adoption signals
5. DeFi exploits and security issues
6. Fed policy and macro indicators

Deprioritize:
- Shitcoin promotions
- Price predictions without analysis
- Celebrity crypto endorsements
- Minor altcoin news""",
    Category.NARRATIVE: """You are SIGINT Narrative Analyst, detecting emerging patterns across sources.

Your role is to identify:
1. Stories appearing across multiple unrelated sources
2. Narrative shifts (sentiment changes on topics)
3. Emerging themes before they go mainstream
4. Coordinated messaging patterns
5. Contradictions between sources

Look for:
- Same event reported with different framing
- Topics gaining velocity across feeds
- Unusual silence on expected topics
- Early signals of larger trends""",
    Category.BREAKING: """You are SIGINT Breaking News Editor, identifying the most urgent developments.

A story qualifies as BREAKING if:
1. It happened in the last 2 hours
2. It has significant immediate implications
3. It affects multiple stakeholder groups
4. Action may be required based on this information

Be very selective. Most news is NOT breaking.
Only elevate items that truly require immediate attention.""",
    Category.MARKETS: """You are SIGINT Market Reporter, curating notable cryptocurrency and market movements for a live ticker display.

Your role is to identify the MOST INTERESTING price movements to feature prominently.

PRIORITIZE (these deserve highlighting):
1. Major movers: >5% price change in 24h (up OR down)
2. New all-time highs or significant lows
3. Unusual volume spikes indicating market interest
4. Correlated moves (multiple assets moving together)
5. Divergences (one asset moving opposite to market)

TICKER DISPLAY FORMAT:
- Keep summaries ultra-short (ticker style)
- Format: "SYMBOL: $PRICE (±X.XX%)"
- For notable movers, add brief context: "BTC breaks $100k resistance"

DEPRIORITIZE:
- Stable prices (< ±2% movement)
- Obscure altcoins without significant volume
- Redundant data (don't repeat same coin multiple times)

Your audience wants quick market intelligence - what moved, why it matters, in minimal words.""",
}


def _get_api_key_from_ssm() -> str | None:
    """Fetch API key from SSM Parameter Store"""
    ssm_param = os.environ.get("ANTHROPIC_API_KEY_SSM_PARAM")
    if not ssm_param:
        return None
    try:
        import boto3
        ssm = boto3.client("ssm")
        response = ssm.get_parameter(Name=ssm_param, WithDecryption=True)
        return response["Parameter"]["Value"]
    except Exception as e:
        logger.warning(f"Failed to fetch API key from SSM: {e}")
        return None


class LLMClient:
    """Client for Anthropic Claude API"""

    def __init__(self, api_key: str | None = None, model: str = "claude-3-5-haiku-20241022"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or _get_api_key_from_ssm()
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set and not found in SSM")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model

    def _build_analysis_prompt(
        self,
        category: Category,
        items: list[RawFeedItem],
        prediction_markets: list[RawFeedItem] | None = None,
    ) -> str:
        """Build the analysis prompt for a category"""
        items_text = "\n\n".join(
            [
                f"[{i + 1}] {item.source}\nTitle: {item.title}\nURL: {item.link}\nDescription: {item.description[:300]}..."
                for i, item in enumerate(items[:30])  # Limit to 30 items to control token usage
            ]
        )

        # Build prediction markets section if provided
        pm_section = ""
        if prediction_markets:
            pm_text = "\n".join(
                [
                    f"[PM-{i + 1}] {item.source}: {item.title}\n   {item.description}"
                    for i, item in enumerate(prediction_markets[:30])  # Show more markets
                ]
            )
            pm_section = f"""

=== PREDICTION MARKETS (ACTIVELY MATCH THESE) ===
{pm_text}

PREDICTION MARKET MATCHING - IMPORTANT:
For EACH selected news item, ACTIVELY LOOK for a related prediction market.
Matches should be included when there's ANY meaningful connection:
- DIRECT: Same event/entity (OpenAI news → OpenAI IPO market)
- THEMATIC: Same domain (AI safety research → AI legislation market)
- CONTEXTUAL: Related implications (Meta nuclear plans → energy/tech infrastructure markets)

Aim to match at least 2-3 items with prediction markets. Add value for readers by linking news to probabilistic forecasts.
"""

        return f"""Analyze these news items and select the TOP 5 most relevant for your category.

{CATEGORY_PROMPTS[category]}

=== ITEMS TO ANALYZE ===
{items_text}
{pm_section}
=== YOUR TASK ===
Select exactly 5 items (or fewer if less than 5 are relevant).
For each selected item, provide:
1. The item number [N]
2. A 1-2 sentence summary (your own words, not copied)
3. Urgency: breaking, high, normal, or low
4. Relevance score: 0.0 to 1.0
5. Key entities mentioned (people, companies, countries)
6. Tags (2-4 topic tags)
7. prediction_market: Include if ANY prediction market relates to this item's topic/entity

Respond in this exact JSON format:
{{
  "selected_items": [
    {{
      "item_number": 1,
      "summary": "Your summary here",
      "urgency": "normal",
      "relevance_score": 0.85,
      "entities": ["Entity1", "Entity2"],
      "tags": ["tag1", "tag2"],
      "prediction_market": {{"pm_number": 1}}
    }}
  ],
  "agent_notes": "Brief note about the current state of this category (1 sentence)"
}}

IMPORTANT: Actively match prediction markets to news items. If a news item mentions OpenAI, check for OpenAI markets. If it mentions AI policy, check for AI legislation markets. Include the match to add probabilistic context."""

    def _build_narrative_prompt(self, all_items: dict[str, list[NewsItem]]) -> str:
        """Build prompt for narrative pattern detection with rich paragraphs"""
        items_by_category = []
        for cat, items in all_items.items():
            if items:
                items_text = "\n".join([f"- {item.title}" for item in items[:10]])
                items_by_category.append(f"=== {cat.upper()} ===\n{items_text}")

        all_items_text = "\n\n".join(items_by_category)

        return f"""Analyze these items across categories to detect narrative patterns and write explanatory paragraphs.

{CATEGORY_PROMPTS[Category.NARRATIVE]}

=== CURRENT ITEMS BY CATEGORY ===
{all_items_text}

=== YOUR TASK ===
Identify 1-3 narrative patterns (or none if nothing significant).

For each pattern, write:
1. A concise title (5-10 words)
2. A brief description (1 sentence)
3. An explanatory PARAGRAPH (3-5 sentences) that:
   - Explains WHAT is happening
   - Provides CONTEXT for why it matters
   - Identifies IMPLICATIONS for readers
4. Key implications as bullet points (2-4 points)
5. Related entities (companies, people, technologies)

A pattern must:
- Appear in at least 2 different categories or sources
- Represent a meaningful trend, not just coincidence
- Be specific and actionable

Respond in this exact JSON format:
{{
  "patterns": [
    {{
      "title": "Brief pattern title",
      "description": "One-sentence summary",
      "paragraph": "Longer explanatory paragraph with context and implications. This should read like a news analysis piece, connecting dots and explaining significance. Include what this means for the industry/world.",
      "implications": [
        "First key implication",
        "Second key implication"
      ],
      "related_entities": ["Entity1", "Entity2"],
      "sources": ["Category1", "Category2"],
      "strength": 0.75
    }}
  ]
}}

If no significant patterns, return: {{"patterns": []}}"""

    def analyze_items(
        self,
        category: Category,
        items: list[RawFeedItem],
        prediction_markets: list[RawFeedItem] | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        """Analyze items and return selected items with metadata and agent notes.
        
        Args:
            category: The news category being analyzed
            items: List of raw feed items to analyze
            prediction_markets: Optional list of prediction market items for matching
        
        Returns:
            Tuple of (selected items with metadata, agent notes string)
        """
        if not items:
            return [], ""

        prompt = self._build_analysis_prompt(category, items, prediction_markets)

        try:
            response = self.client.messages.create(
                model=self.model, max_tokens=2000, messages=[{"role": "user", "content": prompt}]
            )

            # Parse response
            content = response.content[0].text

            # Extract JSON from response
            import re

            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                result = json.loads(json_match.group())
                return result.get("selected_items", []), result.get("agent_notes", "")

            logger.warning(f"Could not parse LLM response for {category}")
            return [], ""

        except Exception as e:
            logger.error(f"LLM error for {category}: {e}")
            return [], ""

    def detect_narratives(self, all_items: dict[str, list[NewsItem]]) -> list[NarrativePattern]:
        """Detect narrative patterns across categories with rich paragraphs"""
        prompt = self._build_narrative_prompt(all_items)

        try:
            response = self.client.messages.create(
                model=self.model, max_tokens=2500, messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text

            import re
            from datetime import datetime

            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                result = json.loads(json_match.group())
                patterns = []
                for p in result.get("patterns", []):
                    import hashlib

                    pattern_id = hashlib.sha256(p["title"].encode()).hexdigest()[:12]
                    patterns.append(
                        NarrativePattern(
                            id=pattern_id,
                            title=p["title"],
                            description=p["description"],
                            sources=p.get("sources", []),
                            item_ids=[],  # Would need to match these
                            strength=p.get("strength", 0.5),
                            first_seen=datetime.now(UTC),
                            last_seen=datetime.now(UTC),
                            paragraph=p.get("paragraph"),
                            implications=p.get("implications", []),
                            related_entities=p.get("related_entities", []),
                        )
                    )
                return patterns

            return []

        except Exception as e:
            logger.error(f"LLM error for narrative detection: {e}")
            return []

    def evaluate_breaking(self, item: NewsItem) -> bool:
        """Quick check if an item should be elevated to breaking"""
        prompt = f"""Is this news item BREAKING (requires immediate attention)?

Title: {item.title}
Summary: {item.summary}
Source: {item.source}
Category: {item.category.value}

{CATEGORY_PROMPTS[Category.BREAKING]}

Respond with only: YES or NO"""

        try:
            response = self.client.messages.create(
                model=self.model, max_tokens=10, messages=[{"role": "user", "content": prompt}]
            )

            return "YES" in response.content[0].text.upper()

        except Exception as e:
            logger.error(f"LLM error for breaking check: {e}")
            return False

    def analyze_unified(
        self,
        category: Category,
        rss_items: list[NewsItem],
        twitter_signals: list[TwitterSignal] | None = None,
        prediction_markets: list[PredictionMarket] | None = None,
    ) -> UnifiedAnalysisResult:
        """Perform unified multi-source analysis.

        This is the Stage 2 analysis method that combines all signal sources
        and produces items with source attribution and cross-source boosting.

        Args:
            category: Category being analyzed
            rss_items: Raw RSS items from ingestion
            twitter_signals: Aggregated Twitter signals (velocity, trending)
            prediction_markets: Prediction market data

        Returns:
            UnifiedAnalysisResult with analyzed items and metadata
        """
        import re
        import time

        start_time = time.time()

        # Track sources used
        sources_used = [SourceType.RSS] if rss_items else []
        sources_missing = []

        if twitter_signals:
            sources_used.append(SourceType.TWITTER)
        else:
            sources_missing.append(SourceType.TWITTER)

        if prediction_markets:
            sources_used.append(SourceType.POLYMARKET)
        else:
            sources_missing.append(SourceType.POLYMARKET)

        if not rss_items:
            logger.warning(f"No RSS items for unified analysis of {category.value}")
            return UnifiedAnalysisResult(
                category=category,
                items=[],
                sources_used=sources_used,
                sources_missing=sources_missing,
                agent_notes="No RSS items available for analysis",
            )

        # Build unified prompt
        prompt = build_unified_prompt(
            rss_items=rss_items,
            twitter_signals=twitter_signals,
            prediction_markets=prediction_markets,
            category=category,
        )

        logger.info(
            f"Unified analysis for {category.value}: "
            f"{len(rss_items)} RSS, {len(twitter_signals or [])} Twitter signals, "
            f"{len(prediction_markets or [])} markets"
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens

            # Extract JSON from response
            json_match = re.search(r"\{[\s\S]*\}", content)
            if not json_match:
                logger.warning(f"Could not parse unified analysis response for {category.value}")
                return self._fallback_analysis(
                    category, rss_items, sources_used, sources_missing, start_time
                )

            result = json.loads(json_match.group())
            selected = result.get("selected_items", [])
            agent_notes = result.get("analysis_notes", "")
            twitter_correlations = result.get("twitter_correlations", [])
            market_correlations = result.get("market_correlations", [])

            # Convert to AnalyzedItem objects
            analyzed_items = []
            items_boosted = 0

            for sel in selected:
                item_num = sel.get("item_number", 1)
                if isinstance(item_num, list):
                    item_num = item_num[0] if item_num else 1
                item_idx = int(item_num) - 1

                if not (0 <= item_idx < len(rss_items)):
                    continue

                original = rss_items[item_idx]

                # Determine source tags
                source_tags = [SourceType.RSS]
                twitter_boost = sel.get("twitter_boost")

                # Check for Twitter correlation
                for tc in twitter_correlations:
                    if tc.get("rss_item_number") == item_num:
                        source_tags.append(SourceType.TWITTER)
                        if not twitter_boost:
                            twitter_boost = 0.1
                        break

                # Check for market correlation
                market_prob = sel.get("market_probability")
                market_q = sel.get("market_question")
                for mc in market_correlations:
                    if mc.get("rss_item_number") == item_num:
                        source_tags.append(SourceType.POLYMARKET)
                        # Get probability from markets list
                        mkt_num = mc.get("market_number", 0)
                        if prediction_markets and 0 < mkt_num <= len(prediction_markets):
                            mkt = prediction_markets[mkt_num - 1]
                            market_prob = mkt.probability
                            market_q = mkt.question
                        break

                # Track boosted items
                if twitter_boost and twitter_boost > 0:
                    items_boosted += 1

                # Parse urgency
                urgency_str = sel.get("urgency", "normal").lower()
                try:
                    urgency = Urgency(urgency_str)
                except ValueError:
                    urgency = Urgency.NORMAL

                # Build AnalyzedItem
                analyzed_item = AnalyzedItem(
                    id=original.id,
                    title=original.title,
                    summary=sel.get("summary", original.summary),
                    url=original.url,
                    source=original.source,
                    source_url=original.source_url,
                    category=category,
                    urgency=urgency,
                    relevance_score=original.relevance_score,
                    published_at=original.published_at,
                    analyzed_at=datetime.now(UTC),
                    entities=sel.get("entities", original.entities),
                    source_tags=list(set(source_tags)),  # Dedupe
                    twitter_boost=twitter_boost,
                    twitter_signals=[
                        tc.get("twitter_entity", "")
                        for tc in twitter_correlations
                        if tc.get("rss_item_number") == item_num
                    ],
                    market_probability=market_prob,
                    market_question=market_q,
                    confidence=sel.get("confidence", 0.5),
                    prediction_market=original.prediction_market,
                )
                analyzed_items.append(analyzed_item)

            duration_ms = int((time.time() - start_time) * 1000)

            return UnifiedAnalysisResult(
                category=category,
                items=analyzed_items,
                analyzed_at=datetime.now(UTC),
                sources_used=sources_used,
                sources_missing=sources_missing,
                rss_count=len(rss_items),
                twitter_signals_count=len(twitter_signals or []),
                markets_count=len(prediction_markets or []),
                items_boosted=items_boosted,
                llm_model=self.model,
                llm_tokens=tokens_used,
                analysis_duration_ms=duration_ms,
                agent_notes=agent_notes,
            )

        except Exception as e:
            logger.exception(f"Unified analysis error for {category.value}: {e}")
            return self._fallback_analysis(
                category, rss_items, sources_used, sources_missing, start_time
            )

    def _fallback_analysis(
        self,
        category: Category,
        rss_items: list[NewsItem],
        sources_used: list[SourceType],
        sources_missing: list[SourceType],
        start_time: float,
    ) -> UnifiedAnalysisResult:
        """Fallback when LLM analysis fails - return top RSS items by recency."""
        import time

        # Sort by published_at, take top 5
        sorted_items = sorted(
            rss_items,
            key=lambda x: x.published_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )[:5]

        analyzed = [
            AnalyzedItem(
                id=item.id,
                title=item.title,
                summary=item.summary,
                url=item.url,
                source=item.source,
                source_url=item.source_url,
                category=category,
                urgency=Urgency.NORMAL,
                relevance_score=0.5,
                published_at=item.published_at,
                entities=item.entities,
                source_tags=[SourceType.RSS],
                confidence=0.5,
            )
            for item in sorted_items
        ]

        duration_ms = int((time.time() - start_time) * 1000)

        return UnifiedAnalysisResult(
            category=category,
            items=analyzed,
            sources_used=sources_used,
            sources_missing=sources_missing,
            rss_count=len(rss_items),
            analysis_duration_ms=duration_ms,
            agent_notes="Fallback analysis - LLM unavailable",
        )
