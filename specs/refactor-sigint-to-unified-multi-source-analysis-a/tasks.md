# Implementation Tasks: Unified Multi-Source Analysis

Generated from spec and plan.md

---

## Phase 1: Data Layer Restructuring

### TASK-001: Create Raw Data S3 Layer
**Priority**: P0
**Effort**: 2h
**Dependencies**: None

Modify S3Store to support raw data storage with new key structure:
- `raw/{category}/rss.json` - RSS feed items
- `raw/{category}/twitter.json` - Twitter signals
- `raw/{category}/markets.json` - Polymarket data
- `raw/ticker.json` - Financial tickers

**Files to modify**:
- `lambdas/shared/s3_store.py`: Add `save_raw_data()` and `load_raw_data()` methods
- `lambdas/shared/models.py`: Add `RawSourceData` model

**Acceptance**:
- [ ] Raw data can be saved with source_type, category, timestamp
- [ ] Raw data can be loaded by category and source_type
- [ ] Existing current/ data structure unchanged

---

### TASK-002: Refactor Twitter Lambda to Raw Storage
**Priority**: P0
**Effort**: 1h
**Dependencies**: TASK-001

Modify Twitter Lambda to write to raw/ instead of current/:
- Output goes to `raw/{category}/twitter.json`
- Include velocity calculations in stored data
- Add `TwitterSignal` summary model

**Files to modify**:
- `lambdas/twitter/handler.py`: Change output path, add velocity summary
- `lambdas/shared/models.py`: Add `TwitterSignal` model

**Acceptance**:
- [ ] Twitter data written to `raw/ai-ml/twitter.json`
- [ ] Data includes velocity metrics per entity
- [ ] Sample tweets included for context

---

### TASK-003: Create RSS Ingestion Lambda
**Priority**: P0
**Effort**: 3h
**Dependencies**: TASK-001

Split reporter Lambda into ingestion + analysis:
- New `sigint-rss-ingest` Lambda for RSS fetching only
- Writes raw RSS items to `raw/{category}/rss.json`
- No LLM calls - just fetch, dedupe, age-filter

**Files to create**:
- `lambdas/rss_ingest/handler.py`: RSS fetching logic
- `lambdas/rss_ingest/__init__.py`

**Files to modify**:
- `infrastructure/app.py`: Add RSS Ingest Lambda, EventBridge schedules

**Acceptance**:
- [ ] RSS items fetched and stored to raw/
- [ ] Deduplication by URL/title
- [ ] Age filtering (72h default)
- [ ] No LLM calls in this Lambda

---

## Phase 2: Unified Analyzer

### TASK-004: Create Unified Prompt Builder
**Priority**: P0
**Effort**: 2h
**Dependencies**: TASK-001, TASK-002, TASK-003

Build structured prompts combining all sources:

```python
def build_unified_prompt(
    rss_items: list[NewsItem],
    twitter_signals: list[TwitterSignal],
    prediction_markets: list[PredictionMarket] | None,
    category: Category
) -> str:
```

**Files to create**:
- `lambdas/shared/unified_prompt.py`

**Acceptance**:
- [ ] Prompt includes numbered RSS items
- [ ] Twitter velocity signals highlighted
- [ ] Prediction markets included if available
- [ ] Clear instructions for cross-source boosting

---

### TASK-005: Add Unified Analysis to LLM Client
**Priority**: P0
**Effort**: 2h
**Dependencies**: TASK-004

Add new method for unified multi-source analysis:

```python
def analyze_unified(
    self,
    prompt: str,
    category: Category
) -> list[AnalyzedItem]:
```

Output includes:
- `source_tags: list[str]` - Contributing sources
- `twitter_boost: float | None` - Boost factor from Twitter
- `confidence: float` - Overall confidence

**Files to modify**:
- `lambdas/shared/llm_client.py`: Add `analyze_unified()` method
- `lambdas/shared/models.py`: Add `AnalyzedItem` model

**Acceptance**:
- [ ] LLM returns structured JSON with source attribution
- [ ] Items boosted when Twitter correlation detected
- [ ] Confidence scores reflect cross-source validation

---

### TASK-006: Create Analyzer Lambda
**Priority**: P0
**Effort**: 3h
**Dependencies**: TASK-004, TASK-005

New Lambda that orchestrates unified analysis:
1. Load raw data from all sources for category
2. Build unified prompt
3. Call LLM for analysis
4. Save results to `current/{category}.json`

**Files to create**:
- `lambdas/analyzer/handler.py`
- `lambdas/analyzer/__init__.py`

**Files to modify**:
- `infrastructure/app.py`: Add Analyzer Lambda, EventBridge schedule

**Acceptance**:
- [ ] Loads RSS, Twitter, Markets data from raw/
- [ ] Single LLM call per category
- [ ] Output includes source_tags on each item
- [ ] Graceful fallback if sources missing

---

## Phase 3: Narrative Enhancement

### TASK-007: Enhance Narrative Writer
**Priority**: P1
**Effort**: 2h
**Dependencies**: TASK-006

Upgrade narrative Lambda to generate explanatory paragraphs:
- Load analyzed data with source tags
- Generate 2-4 sentence explanations
- Include implications ("This suggests...", "Watch for...")
- Reference cross-source correlations

**Files to modify**:
- `lambdas/narrative/handler.py`: Enhance pattern descriptions
- `lambdas/shared/llm_client.py`: Add `generate_narrative_paragraph()` method

**Acceptance**:
- [ ] Narratives are full paragraphs, not just titles
- [ ] Implications included in output
- [ ] Source references cited

---

## Phase 4: Frontend Integration

### TASK-008: Display Source Tags in Frontend
**Priority**: P1
**Effort**: 2h
**Dependencies**: TASK-006

Add source tag indicators to dashboard items:
- [RSS] - Blue tag
- [🐦] - Twitter logo/icon
- [📊] - Polymarket indicator
- [💰] - Ticker indicator

**Files to modify**:
- `frontend/app.js`: Add source tag rendering
- `frontend/style.css`: Source tag styles

**Acceptance**:
- [ ] Tags visible on each item
- [ ] Hover shows source details
- [ ] Tags visually distinct

---

### TASK-009: Display Narrative Paragraphs
**Priority**: P1
**Effort**: 1h
**Dependencies**: TASK-007

Update narrative tracker to show full paragraphs:
- Expandable pattern cards
- Implications highlighted
- Source citations linked

**Files to modify**:
- `frontend/app.js`: Narrative section rendering
- `frontend/style.css`: Narrative card styles

**Acceptance**:
- [ ] Full paragraphs displayed
- [ ] Implications visually distinct
- [ ] Readable and scannable

---

## Phase 5: Infrastructure & Orchestration

### TASK-010: Update CDK for New Lambdas
**Priority**: P0
**Effort**: 2h
**Dependencies**: TASK-003, TASK-006

Add new Lambdas to CDK stack:
- `sigint-rss-ingest` with per-category schedules
- `sigint-analyzer` triggered after ingestion

**Files to modify**:
- `infrastructure/app.py`: Add Lambda definitions, schedules

**Acceptance**:
- [ ] Both Lambdas deploy successfully
- [ ] EventBridge schedules configured
- [ ] IAM permissions correct

---

### TASK-011: Deprecate Reporter LLM Analysis
**Priority**: P2
**Effort**: 1h
**Dependencies**: TASK-006, TASK-010 (after validation)

Remove LLM analysis from reporter once analyzer is stable:
- Reporter becomes pure ingestion
- Or merge with rss-ingest Lambda

**Files to modify**:
- `lambdas/reporters/handler.py`: Remove LLM calls (or deprecate entirely)

**Acceptance**:
- [ ] No duplicate LLM calls
- [ ] Clean separation of concerns

---

## Summary

| Phase | Tasks | Est. Effort |
|-------|-------|-------------|
| 1. Data Layer | TASK-001, 002, 003 | 6h |
| 2. Unified Analyzer | TASK-004, 005, 006 | 7h |
| 3. Narrative | TASK-007 | 2h |
| 4. Frontend | TASK-008, 009 | 3h |
| 5. Infrastructure | TASK-010, 011 | 3h |
| **Total** | **11 tasks** | **~21h** |

## Execution Order

1. TASK-001 (S3 layer) - Foundation
2. TASK-002 (Twitter to raw) - Quick win
3. TASK-003 (RSS ingest) - Parallel with 004
4. TASK-004 (Prompt builder) - Parallel with 003
5. TASK-005 (LLM method) - After 004
6. TASK-006 (Analyzer Lambda) - After 005
7. TASK-010 (CDK) - After 003, 006
8. TASK-007 (Narrative) - After 006
9. TASK-008, 009 (Frontend) - After 006, 007
10. TASK-011 (Deprecate) - Last, after validation
