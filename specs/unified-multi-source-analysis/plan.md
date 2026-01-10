# Unified Multi-Source Analysis Architecture

## Overview

Refactor SIGINT to use a structured hybrid approach where all signal sources (RSS, X/Twitter, Polymarket, Tickers) are ingested separately but analyzed together in a unified LLM pass per category.

## Current State

```
RSS ──────▶ Reporter Lambda ──▶ LLM ──▶ S3: ai-ml.json
Twitter ──▶ Twitter Lambda ───▶ S3: twitter-ai-ml.json (unused by reporter)
Markets ──▶ Reporter Lambda ──▶ (matched to items)
Tickers ──▶ Reporter Lambda ──▶ S3: markets.json
```

**Problem**: Twitter signals don't influence which RSS items get selected. Cross-source correlation happens only in narrative (after the fact).

## Proposed Architecture

### Stage 1: Ingest (Per Source, No LLM)

Each source has its own ingestion pipeline storing raw data:

```
RSS Fetcher ────▶ S3: raw/{category}/rss.json
Twitter Fetcher ─▶ S3: raw/{category}/twitter.json  
Polymarket ─────▶ S3: raw/{category}/markets.json
Tickers ────────▶ S3: raw/ticker.json
```

### Stage 2: Unified Analyzer (Per Category, Single LLM)

A new `analyzer` Lambda loads all raw sources for a category and runs unified analysis:

```python
# Load all sources
rss_items = load_raw("ai-ml", "rss")
twitter_signals = load_raw("ai-ml", "twitter") 
prediction_markets = load_raw("ai-ml", "markets")

# Build unified prompt
prompt = build_unified_prompt(rss_items, twitter_signals, prediction_markets)

# Single LLM call with cross-source context
selected = llm.analyze_unified(prompt)

# Save with source attribution
save_category_data("ai-ml", selected)
```

### Stage 3: Narrative Writer (Cross-Category)

Narrative Lambda reads all `current/*.json` files and:
1. Detects cross-category patterns
2. Writes explanatory paragraphs (not just pattern names)
3. Highlights implications and connections

## Implementation Tasks

### TASK-001: Create Raw Data Layer
- Add `raw/` prefix to S3 structure
- Modify Twitter Lambda to write to `raw/{category}/twitter.json`
- Create RSS ingestion Lambda (split from reporter)
- Markets data stays in reporter for now (simpler)

### TASK-002: Build Unified Prompt Builder
- Create `lambdas/shared/unified_prompt.py`
- Function: `build_unified_prompt(rss, twitter, markets, tickers)`
- Output structured prompt with all sources
- Include velocity indicators for Twitter
- Include probability anchors for markets

### TASK-003: Create Analyzer Lambda
- New Lambda: `sigint-analyzer`
- Loads all raw sources for a category
- Calls LLM with unified prompt
- Saves to `current/{category}.json` with source tags
- Runs after ingestion Lambdas complete

### TASK-004: Refactor Reporter to Ingestion-Only
- Remove LLM analysis from reporter
- Reporter becomes "RSS Ingester"
- Writes to `raw/{category}/rss.json`
- Keep feed fetching, deduplication, age filtering

### TASK-005: Update LLM Client for Unified Analysis
- Add `analyze_unified()` method to LLMClient
- Prompt instructs: "Boost items appearing across sources"
- Output includes `source_tags: ["RSS", "Twitter", "Polymarket"]`
- Confidence scoring based on cross-source validation

### TASK-006: Enhance Narrative Writer
- Load Twitter data alongside news
- Generate explanatory paragraphs (not just titles)
- Include implications: "This suggests...", "Watch for..."
- Cross-reference prediction market probabilities

### TASK-007: Update Frontend for Source Tags
- Display source indicators on items: [RSS] [🐦] [📊]
- Show "Twitter Boost" indicator for correlated items
- Narrative section shows full paragraphs

### TASK-008: Update CDK Infrastructure
- Add `sigint-analyzer` Lambda
- Configure EventBridge: Ingestion → Analyzer chain
- Or use Step Functions for orchestration

## Data Models

### Raw Twitter Signal
```python
class TwitterSignal(BaseModel):
    entity: str                    # "Constitutional Classifiers"
    velocity: float                # tweets/hour
    velocity_ratio: float          # vs baseline (2.0 = 2x normal)
    sample_tweets: list[str]       # Top 3 tweet texts
    top_accounts: list[str]        # ["@AnthropicAI", "@sama"]
    first_seen: datetime
```

### Unified Analysis Output
```python
class AnalyzedItem(BaseModel):
    id: str
    title: str
    summary: str
    source_url: str
    published_at: datetime
    source_tags: list[str]         # ["RSS", "Twitter"]
    twitter_boost: float | None    # 0.0-1.0 boost from Twitter signal
    market_probability: float | None  # Polymarket probability
    confidence: float              # Overall confidence (0.0-1.0)
    entities: list[str]
```

## Prompt Template

```
You are analyzing multiple signal sources for the {category} intelligence category.

## PRIMARY: RSS FEED ITEMS
{rss_items_numbered}

## SIGNAL BOOST: TWITTER ACTIVITY
These topics are trending on X/Twitter among domain experts:
{twitter_signals}

## PROBABILITY ANCHORS: PREDICTION MARKETS
Current market probabilities for relevant outcomes:
{prediction_markets}

## TASK
Select the top 5 most significant items. Apply these rules:
1. BOOST items that appear across multiple sources (RSS + Twitter = high signal)
2. ANCHOR predictions to market probabilities where relevant
3. TAG each item with its sources: [RSS] [🐦 Twitter] [📊 Market]
4. PRIORITIZE items where Twitter velocity is elevated (>2x normal)

Output JSON with selected items, source_tags, and confidence scores.
```

## EventBridge Schedule (Proposed)

| Lambda | Schedule | Trigger |
|--------|----------|---------|
| sigint-rss-ingest | 5-15 min | EventBridge |
| sigint-twitter | 2 hours | EventBridge |
| sigint-analyzer | After ingestion | Step Functions or EventBridge |
| sigint-narrative | 30 min | EventBridge |

## Success Criteria

1. Items with Twitter correlation appear higher in category feeds
2. Source tags visible in dashboard: [RSS] [🐦] [📊]
3. Narrative explanations are full paragraphs with implications
4. Single LLM call per category (cost efficient)
5. Modular ingestion (one source failure doesn't break others)

## Migration Path

1. Deploy new Lambdas alongside existing
2. Run in parallel with shadow mode (compare outputs)
3. Switch frontend to new data structure
4. Deprecate old reporter Lambda

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Unified prompt too large | Summarize Twitter signals (top 5 entities only) |
| LLM fails on complex prompt | Fallback to RSS-only analysis |
| Step Functions complexity | Start with simple EventBridge delays |
| Twitter API limits | Aggressive caching (2h TTL), usage tracking |
