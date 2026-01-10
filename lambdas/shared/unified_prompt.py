"""
Unified Prompt Builder for SIGINT

Builds structured LLM prompts that combine all signal sources
(RSS, Twitter, Polymarket, Tickers) for cross-source analysis.

The prompt instructs the LLM to:
1. Select top items from RSS
2. Boost items that correlate with Twitter signals
3. Anchor predictions to market probabilities
4. Tag items with their contributing sources
"""

import logging
from datetime import datetime

from .models import (
    Category,
    NewsItem,
    PredictionMarket,
    SourceType,
    TwitterSignal,
)

logger = logging.getLogger(__name__)

# Category-specific analysis instructions
CATEGORY_INSTRUCTIONS = {
    Category.AI_ML: """Focus on:
- Major model releases (GPT, Claude, Gemini, Llama, Grok)
- Safety research and alignment
- Regulatory developments
- Company announcements (OpenAI, Anthropic, Google, Meta, xAI)
- Frontier capabilities and benchmarks""",

    Category.GEOPOLITICAL: """Focus on:
- Active conflicts and military operations
- Diplomatic developments and negotiations
- Sanctions and economic measures
- Elections and political transitions
- Intelligence and security matters""",

    Category.DEEP_TECH: """Focus on:
- Quantum computing breakthroughs
- Semiconductor and chip developments
- Space exploration and launches
- Biotech and medical advances
- Energy and climate technology""",

    Category.CRYPTO_FINANCE: """Focus on:
- Major price movements (>5% swings)
- Regulatory actions (SEC, CFTC)
- Protocol upgrades and launches
- Institutional adoption
- DeFi developments""",
}


def build_unified_prompt(
    rss_items: list[NewsItem],
    twitter_signals: list[TwitterSignal] | None = None,
    prediction_markets: list[PredictionMarket] | None = None,
    category: Category = Category.AI_ML,
    max_rss_items: int = 30,
    max_twitter_signals: int = 10,
    max_markets: int = 10,
) -> str:
    """
    Build a unified analysis prompt combining all signal sources.

    Args:
        rss_items: Raw RSS items to analyze
        twitter_signals: Aggregated Twitter signals (velocity, trending)
        prediction_markets: Prediction market data
        category: Category being analyzed
        max_rss_items: Maximum RSS items to include
        max_twitter_signals: Maximum Twitter signals to include
        max_markets: Maximum prediction markets to include

    Returns:
        Formatted prompt string for LLM
    """
    sections = []

    # Header
    sections.append(_build_header(category))

    # RSS Items (primary source)
    sections.append(_build_rss_section(rss_items[:max_rss_items]))

    # Twitter Signals (boost indicators)
    if twitter_signals:
        sections.append(_build_twitter_section(twitter_signals[:max_twitter_signals]))

    # Prediction Markets (probability anchors)
    if prediction_markets:
        sections.append(_build_markets_section(prediction_markets[:max_markets]))

    # Task instructions
    sections.append(_build_task_instructions(category, twitter_signals, prediction_markets))

    return "\n\n".join(sections)


def _build_header(category: Category) -> str:
    """Build the prompt header with role and context."""
    return f"""You are a senior intelligence analyst performing unified multi-source analysis for the **{category.value.upper()}** category.

Your task is to analyze items from multiple sources and select the most significant ones for an intelligence dashboard.

{CATEGORY_INSTRUCTIONS.get(category, "")}"""


def _build_rss_section(items: list[NewsItem]) -> str:
    """Build the RSS items section."""
    if not items:
        return "## PRIMARY: RSS FEED ITEMS\n\nNo RSS items available."

    lines = ["## PRIMARY: RSS FEED ITEMS", ""]

    for i, item in enumerate(items, 1):
        # Format published time if available
        pub_time = ""
        if item.published_at:
            age_hours = (datetime.now(item.published_at.tzinfo or None) - item.published_at).total_seconds() / 3600
            if age_hours < 1:
                pub_time = f" ({int(age_hours * 60)}m ago)"
            elif age_hours < 24:
                pub_time = f" ({int(age_hours)}h ago)"
            else:
                pub_time = f" ({int(age_hours / 24)}d ago)"

        lines.append(f"{i}. [{item.source}]{pub_time} {item.title}")

        # Include truncated summary
        summary = item.summary[:200] + "..." if len(item.summary) > 200 else item.summary
        lines.append(f"   Summary: {summary}")
        lines.append("")

    return "\n".join(lines)


def _build_twitter_section(signals: list[TwitterSignal]) -> str:
    """Build the Twitter signals section."""
    if not signals:
        return ""

    lines = [
        "## SIGNAL BOOST: TWITTER/X ACTIVITY",
        "",
        "These topics are trending among domain experts on X/Twitter.",
        "Items related to these signals should be prioritized.",
        "",
    ]

    # Separate spikes from regular signals
    spikes = [s for s in signals if s.is_spike]
    regular = [s for s in signals if not s.is_spike][:5]

    if spikes:
        lines.append("### 🔥 VELOCITY SPIKES (2x+ normal activity)")
        for sig in spikes:
            top_accounts = ", ".join(sig.top_accounts[:3]) if sig.top_accounts else "various"
            lines.append(
                f"- **{sig.entity}**: {sig.velocity_ratio:.1f}x velocity "
                f"(from {top_accounts})"
            )
            if sig.sample_tweets:
                lines.append(f'  > "{sig.sample_tweets[0][:100]}..."')
        lines.append("")

    if regular:
        lines.append("### Active Topics")
        for sig in regular:
            lines.append(f"- {sig.entity}: {sig.velocity:.1f} tweets/hr")
        lines.append("")

    return "\n".join(lines)


def _build_markets_section(markets: list[PredictionMarket]) -> str:
    """Build the prediction markets section."""
    if not markets:
        return ""

    lines = [
        "## PROBABILITY ANCHORS: PREDICTION MARKETS",
        "",
        "Use these market probabilities to calibrate your confidence.",
        "If an RSS item relates to a market question, note the probability.",
        "",
    ]

    for i, market in enumerate(markets, 1):
        prob = f"{market.probability * 100:.0f}%" if market.probability else "N/A"
        lines.append(f"{i}. [{market.source}] {market.question}")
        lines.append(f"   Probability: {prob}")
        if market.volume:
            lines.append(f"   Volume: {market.volume}")
        lines.append("")

    return "\n".join(lines)


def _build_task_instructions(
    category: Category,
    twitter_signals: list[TwitterSignal] | None,
    prediction_markets: list[PredictionMarket] | None,
) -> str:
    """Build the task instructions section."""
    # Determine available sources
    sources = [SourceType.RSS.value]
    if twitter_signals:
        sources.append(SourceType.TWITTER.value)
    if prediction_markets:
        sources.append(SourceType.POLYMARKET.value)

    source_tags_example = " ".join(f"[{s.upper()}]" for s in sources)

    return f"""## TASK

Analyze the items above and select the **top 5 most significant** for the {category.value} intelligence dashboard.

### Selection Rules

1. **BOOST items that appear across sources**
   - RSS item + matching Twitter signal = HIGH priority
   - RSS item + prediction market correlation = HIGH confidence

2. **APPLY velocity boosting**
   - Items related to Twitter velocity spikes get +0.2 confidence boost
   - Maximum boost: +0.3 (capped)

3. **TAG each item with contributing sources**
   - Use tags like: {source_tags_example}
   - An item can have multiple tags if it appears in multiple sources

4. **SET confidence scores (0.0-1.0)**
   - Base: Relevance to {category.value} category
   - +0.1-0.2: Twitter correlation
   - +0.1: Prediction market anchor
   - Cap at 0.95

### Output Format

Return a JSON array with exactly this structure:

```json
{{
  "selected_items": [
    {{
      "item_number": 1,
      "title": "Original title from RSS",
      "summary": "Your 2-sentence analysis",
      "source_tags": ["RSS", "TWITTER"],
      "twitter_boost": 0.2,
      "market_probability": null,
      "market_question": null,
      "confidence": 0.85,
      "urgency": "high",
      "entities": ["OpenAI", "GPT-5"],
      "reasoning": "Why this item is significant"
    }}
  ],
  "twitter_correlations": [
    {{
      "rss_item_number": 1,
      "twitter_entity": "@OpenAI",
      "correlation_type": "velocity_spike"
    }}
  ],
  "market_correlations": [
    {{
      "rss_item_number": 2,
      "market_number": 1,
      "correlation_type": "direct_reference"
    }}
  ],
  "analysis_notes": "Brief summary of key themes and any notable patterns"
}}
```

Return ONLY valid JSON, no markdown code blocks or additional text."""


def estimate_token_count(prompt: str) -> int:
    """Rough estimate of token count (4 chars per token on average)."""
    return len(prompt) // 4
