# SIGINT Dashboard Refinement Plan

> **Purpose**: Phased implementation plan for age-based article filtering, prediction market integration, and high-signal feed expansion.

## Executive Summary

This plan addresses three core issues:
1. **Stale content**: No date filtering exists—old articles appear alongside fresh ones
2. **Limited prediction market integration**: Polymarket data exists but isn't contextualized to displayed articles
3. **Insufficient sources**: Need more high-signal RSS feeds per category

## Phase Overview

| Phase | Focus | Complexity | LLM Cost Impact |
|-------|-------|------------|-----------------|
| **Phase 1** | Age Slider + Date Filtering | Medium | Reduces cost (fewer items to LLM) |
| **Phase 2** | Contextual Prediction Markets | High | Moderate increase (new prompts) |
| **Phase 3** | High-Signal Feed Expansion | Low | Neutral (pre-LLM filtering offsets) |
| **Phase 4** | Archive Enhancement | Medium | None |

---

## Phase 1: Age Slider + Date Filtering

### 1.1 Backend: Pre-LLM Age Filtering

**Goal**: Filter out articles older than a configurable threshold BEFORE sending to LLM (cost savings).

**Files to modify**:
- `lambdas/shared/feed_fetcher.py` — Add `filter_by_age()` method
- `lambdas/reporters/handler.py` — Apply filter before LLM call
- `config/feeds.json` — Add `default_age_hours: 24` to global_settings

**Implementation**:
```python
# In feed_fetcher.py
def filter_by_age(self, items: list[NewsItem], max_age_hours: int = 24) -> list[NewsItem]:
    """Filter items to only include those within max_age_hours"""
    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
    return [
        item for item in items 
        if item.published_at is None or item.published_at > cutoff
    ]
```

### 1.2 Backend: Archive Range Query API

**Goal**: Enable frontend to query archive data across a date range (for slider functionality).

**Files to modify**:
- `lambdas/shared/s3_store.py` — Add `get_archive_range()` and `list_archive_dates()` methods

**Implementation**:
```python
def list_archive_dates(self) -> list[str]:
    """List all available archive dates"""
    # Use S3 list_objects_v2 with prefix 'archive/'
    
def get_archive_range(self, category: Category, days: int = 7) -> list[NewsItem]:
    """Get archived items for last N days"""
    items = []
    for i in range(days):
        date = (datetime.now(UTC) - timedelta(days=i)).strftime("%Y-%m-%d")
        items.extend(self.get_archive(category, date))
    return items
```

### 1.3 Frontend: Age Slider Component

**Goal**: Interactive slider (24h default, max 30 days) that filters displayed content.

**Files to modify**:
- `frontend/index.html` — Add slider UI element
- `frontend/style.css` — Style the slider
- `frontend/app.js` — Implement slider logic and archive fetching

**UI Concept**:
```
[TIME RANGE] ━━━━━━●━━━━━━━━━━━━━━━━━ [30 DAYS]
              24h    7d    14d    30d
```

**Behavior**:
- Default: 24h (shows current data only)
- Sliding right: Fetches and merges archive data for selected range
- Client-side filtering prevents JSON bloat (fetch in chunks, display filtered)

---

## Phase 2: Contextual Prediction Markets

### 2.1 Architecture Decision: Reporter Enhancement vs New Agent

**Recommendation**: Enhance existing reporters to include prediction market context.

**Why NOT a separate Prediction Markets category**:
- Prediction markets gain meaning when contextualized (e.g., "Israel-Gaza" next to geopolitical article)
- A standalone category would duplicate headlines without adding signal
- Existing reporters already understand their domain

**Why reporter enhancement**:
- Each reporter already has domain expertise
- Can match prediction markets to current headlines
- Adds 1-2 prediction market items per category (minimal cost)

### 2.2 Prediction Market Data Sources

**Primary markets to integrate**:

| Market | API | Focus Areas |
|--------|-----|-------------|
| **Polymarket** | `gamma-api.polymarket.com/markets` | Politics, crypto, events |
| **Kalshi** | `trading-api.kalshi.com/v2/events` | US-regulated, economics, elections |
| **Metaculus** | `metaculus.com/api2/questions/` | Long-term forecasting, science |

**API integration pattern** (add to `CATEGORY_FEEDS` or separate config):
```python
PREDICTION_MARKET_APIS = {
    "polymarket": "https://gamma-api.polymarket.com/markets?closed=false&order=volume&ascending=false&limit=50",
    "kalshi": "https://trading-api.kalshi.com/v2/events?status=open&limit=50",
    "metaculus": "https://www.metaculus.com/api2/questions/?status=open&order_by=-activity&limit=50",
}
```

### 2.3 LLM Prompt Enhancement

**Modify `CATEGORY_PROMPTS` in `lambdas/shared/llm_client.py`**:

```python
# Add to each category prompt:
"""
PREDICTION MARKET CONTEXT:
You are also provided with current prediction market data. For each selected article,
if there is a directly relevant prediction market, include it as a related prediction
in the article's metadata.

Format prediction data as:
{
  "prediction_market": {
    "question": "Will X happen by Y date?",
    "probability": 0.65,
    "source": "Polymarket",
    "volume": "$2.5M"
  }
}
"""
```

### 2.4 Frontend: Prediction Market Display

**Files to modify**:
- `frontend/app.js` — Render prediction badges on articles
- `frontend/style.css` — Style prediction probability badges

**Display concept**:
```
┌─────────────────────────────────────────────────┐
│ [BBC] Putin announces new military offensive     │
│ Strategic analysis of the latest developments   │
│ ┌─────────────────────────────────────────────┐ │
│ │ 📊 Polymarket: "Russia controls Kyiv by 2026" │
│ │    12% probability • $1.2M volume             │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

---

## Phase 3: High-Signal Feed Expansion

### 3.1 Feed Additions by Category

**GEOPOLITICAL** (add 10 feeds):
```python
# Think tanks & analysis
"https://www.foreignaffairs.com/rss.xml",  # Foreign Affairs
"https://carnegieendowment.org/rss/solr/?fa=topStories",  # Carnegie
"https://www.rand.org/blog.xml",  # RAND Corporation
"https://rusi.org/rss.xml",  # RUSI (UK defense)

# Regional specialists
"https://www.aspistrategist.org.au/feed/",  # Australian Strategic Policy
"https://www.iiss.org/blogs/analysis/feed",  # IISS
"https://foreignpolicy.com/feed/",  # Foreign Policy

# Open-source intelligence
"https://www.oryxspioenkop.com/feeds/posts/default?alt=rss",  # Oryx (verified losses)
"https://liveuamap.com/rss",  # Live UA Map
```

**AI_ML** (add 8 feeds):
```python
"https://www.marktechpost.com/feed/",  # MarkTechPost
"https://www.aiweekly.co/feed.xml",  # AI Weekly
"https://jack-clark.net/feed/",  # Import AI (Jack Clark)
"https://thegradient.pub/rss/",  # The Gradient
"https://distill.pub/rss.xml",  # Distill (if active)
"https://newsletter.ruder.io/feed",  # Sebastian Ruder
"https://www.deeplearning.ai/the-batch/feed/",  # The Batch (Andrew Ng)
"https://bensbites.beehiiv.com/feed",  # Ben's Bites
```

**DEEP_TECH** (add 8 feeds):
```python
"https://spectrum.ieee.org/feeds/feed.rss",  # IEEE Spectrum
"https://semiengineering.com/feed/",  # Semiconductor Engineering
"https://www.nextplatform.com/feed/",  # The Next Platform
"https://www.anandtech.com/rss/",  # AnandTech
"https://www.tomshardware.com/feeds/all",  # Tom's Hardware
"https://hackaday.com/feed/",  # Hackaday
"https://www.quantamagazine.org/feed/",  # Quanta Magazine
"https://phys.org/rss-feed/",  # Phys.org
```

**CRYPTO_FINANCE** (add 8 feeds):
```python
"https://decrypt.co/feed",  # Decrypt
"https://www.coindesk.com/arc/outboundfeeds/rss/",  # CoinDesk
"https://thedefiant.io/feed",  # The Defiant (DeFi)
"https://www.theblock.co/rss.xml",  # The Block
"https://messari.io/rss",  # Messari
"https://newsletter.banklesshq.com/feed",  # Bankless
"https://www.dlnews.com/rss.xml",  # DL News
"https://a]16zcrypto.com/feed/",  # a16z Crypto
```

### 3.2 Cost Mitigation

**Pre-LLM filtering chain** (applied in order):
1. Age filter (Phase 1) — Remove articles > 24h
2. Deduplication — Remove already-seen IDs
3. Title similarity — Remove near-duplicate headlines (Jaccard similarity > 0.8)
4. Source diversity — Max 3 items per source before LLM

**Expected result**: 50+ feeds → ~30 unique recent items → LLM sees same volume as today.

---

## Phase 4: Archive Enhancement

### 4.1 Extended Archive Retention

**Current**: Archives stored per day, accessible via modal
**Enhanced**: 
- Store 30 days of archives
- Add date picker in archive modal
- Enable export to JSON/CSV

### 4.2 Archive Cleanup Lambda

**New Lambda**: `archive-cleanup`
- Runs daily
- Deletes archives older than 30 days
- Compresses older archives if storage becomes concern

### 4.3 Archive Index

**New S3 object**: `archive/index.json`
```json
{
  "available_dates": ["2026-01-09", "2026-01-08", ...],
  "total_items_by_category": {
    "geopolitical": 1250,
    "ai-ml": 890,
    ...
  }
}
```

---

## Implementation Order

```
Phase 1.1 (Backend filtering) ──┐
Phase 1.2 (Archive range API) ──┼── Week 1
Phase 1.3 (Frontend slider)  ───┘

Phase 2.1 (PM architecture) ────┐
Phase 2.2 (API integration) ────┼── Week 2
Phase 2.3 (Prompt enhancement) ─┘

Phase 2.4 (PM display) ─────────┐
Phase 3.1 (Feed expansion) ─────┼── Week 3
Phase 3.2 (Cost mitigation) ────┘

Phase 4 (Archive enhancement) ──── Week 4
```

---

## Agentic SDD Execution Commands

Run each phase through the workflow:

```bash
# Phase 1: Age Filtering & Slider
uv run smactorio workflow run --feature "Add age-based article filtering with a frontend time range slider. Default 24 hours, max 30 days. Filter articles BEFORE LLM calls in feed_fetcher.py. Add get_archive_range() to s3_store.py. Slider fetches archive data and merges with current."

# Phase 2: Contextual Prediction Markets  
uv run smactorio workflow run --feature "Integrate Polymarket, Kalshi, and Metaculus prediction market APIs into existing category reporters. Each reporter should find 1-2 prediction markets relevant to its top headlines. Display probability badges on articles in frontend."

# Phase 3: Feed Expansion
uv run smactorio workflow run --feature "Expand RSS feeds for all categories with high-signal sources. Add pre-LLM filtering: age filter, dedup, title similarity, source diversity limits. Ensure LLM input volume stays constant despite more feeds."

# Phase 4: Archive Enhancement
uv run smactorio workflow run --feature "Add 30-day archive retention with cleanup Lambda. Create archive index.json listing available dates. Add date picker to archive modal. Enable JSON export."
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Archive JSON bloat | Client-side pagination, lazy loading |
| Prediction market API rate limits | Cache responses for 5 min, fallback to stale |
| LLM cost increase from new feeds | Aggressive pre-LLM filtering maintains volume |
| Slider performance on mobile | Debounce slider, progressive loading |

---

## Success Metrics

- [ ] No articles older than slider setting displayed
- [ ] Each category shows 0-2 relevant prediction markets
- [ ] Feed count per category: 15+ sources
- [ ] LLM API costs remain within 10% of current
- [ ] Slider response time < 500ms

---

## Files Modified Per Phase

| Phase | Files |
|-------|-------|
| 1 | `feed_fetcher.py`, `handler.py`, `s3_store.py`, `feeds.json`, `app.js`, `style.css`, `index.html` |
| 2 | `llm_client.py`, `models.py`, `handler.py`, `app.js`, `style.css` |
| 3 | `handler.py`, `feeds.json`, `feed_fetcher.py` |
| 4 | `s3_store.py`, `app.py` (infrastructure), `app.js` |
