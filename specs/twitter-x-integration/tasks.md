# Twitter/X Integration - Implementation Tasks

> **Feature**: Hybrid Twitter/X integration with deep narrative correlation  
> **Pilot Category**: AI/ML  
> **Generated**: 2026-01-09

---

## Sprint 1: Infrastructure Foundation (Days 1-3)

### TASK-001: Store X API Bearer Token in SSM
**Priority**: P0 | **Story Points**: 1 | **Status**: Not Started

**Description**: Store the X/Twitter API bearer token securely in AWS SSM Parameter Store.

**Acceptance Criteria**:
- [ ] SSM parameter `/sigint/x-bearer-token` created as SecureString
- [ ] Parameter accessible from Lambda execution role
- [ ] Test retrieval works from local environment

**Implementation**:
```bash
aws ssm put-parameter \
  --name '/sigint/x-bearer-token' \
  --type 'SecureString' \
  --value 'YOUR_BEARER_TOKEN' \
  --region us-east-1
```

**Files**: None (AWS CLI operation)

---

### TASK-002: Create TweetItem and CorrelatedNarrative Models
**Priority**: P0 | **Story Points**: 2 | **Status**: Not Started

**Description**: Add Pydantic models for Twitter data and correlated narratives to the shared models module.

**Acceptance Criteria**:
- [ ] `TweetItem` dataclass with: tweet_id, author_handle, author_id, content, created_at, hashtags, mentions, retweet_count, like_count, reply_count, fetched_at
- [ ] `CorrelatedNarrative` dataclass with: correlation_id, tweet_ids, news_article_ids, keywords, hashtags, tweet_spike_time, news_publish_time, lead_lag_hours, confidence_score, amplification_factor
- [ ] Models serialize/deserialize correctly to JSON
- [ ] Unit tests pass

**Files**:
- `lambdas/shared/models.py` (modify)
- `tests/unit/shared/test_models.py` (modify)

---

### TASK-003: Create twitter_client.py Module
**Priority**: P0 | **Story Points**: 5 | **Status**: Not Started

**Description**: Create a Twitter/X API v2 client with rate limiting, caching, and error handling.

**Acceptance Criteria**:
- [ ] `TwitterClient` class with async methods:
  - `fetch_list_timeline(list_id: str) -> list[TweetItem]`
  - `search_tweets(query: str, max_results: int) -> list[TweetItem]`
  - `get_user_timeline(user_id: str) -> list[TweetItem]`
- [ ] Rate limit tracking (reads remaining, reset time)
- [ ] S3 cache integration for all responses
- [ ] Exponential backoff on rate limit errors
- [ ] Bearer token loaded from SSM
- [ ] Unit tests with mocked API responses

**Files**:
- `lambdas/shared/twitter_client.py` (create)
- `tests/unit/shared/test_twitter_client.py` (create)

**Dependencies**: TASK-001, TASK-002

---

### TASK-004: Add Twitter Lambda to Infrastructure
**Priority**: P0 | **Story Points**: 3 | **Status**: Not Started

**Description**: Add the Twitter Lambda function to CDK infrastructure with EventBridge schedule.

**Acceptance Criteria**:
- [ ] Lambda function `sigint-twitter` created
- [ ] SSM parameter reference for X bearer token
- [ ] EventBridge schedule: every 2 hours for list baseline
- [ ] Lambda can invoke on narrative spike event (SNS/EventBridge)
- [ ] CloudWatch log group created
- [ ] IAM role with S3, SSM read permissions

**Files**:
- `infrastructure/app.py` (modify)
- `lambdas/twitter/__init__.py` (create)
- `lambdas/twitter/handler.py` (create skeleton)

**Dependencies**: TASK-001

---

## Sprint 2: Data Collection (Days 4-6)

### TASK-005: Implement List Timeline Fetching
**Priority**: P0 | **Story Points**: 3 | **Status**: Not Started

**Description**: Implement the core list timeline fetching logic in TwitterClient.

**Acceptance Criteria**:
- [ ] Fetch tweets from Twitter List by list ID
- [ ] Parse X API v2 response into `TweetItem` models
- [ ] Extract: text, author, metrics, hashtags, mentions, cashtags
- [ ] Handle pagination (up to 100 tweets per request)
- [ ] Cache response to S3 with TTL metadata

**Files**:
- `lambdas/shared/twitter_client.py` (implement)
- `tests/unit/shared/test_twitter_client.py` (add tests)

**API Reference**: GET /2/lists/:id/tweets

---

### TASK-006: Implement S3 Caching Layer
**Priority**: P0 | **Story Points**: 3 | **Status**: Not Started

**Description**: Add caching layer for Twitter API responses to minimize API calls.

**Acceptance Criteria**:
- [ ] S3 key pattern: `twitter/cache/{endpoint_type}/{id}/{timestamp}.json`
- [ ] Cache TTL: 2 hours for list timelines, 1 hour for searches
- [ ] Check cache before API call, return cached if fresh
- [ ] Log cache hit/miss metrics
- [ ] Monthly API usage counter in S3 (`twitter/usage/{year}-{month}.json`)
- [ ] Alert when usage exceeds 80% of 1500 limit

**Files**:
- `lambdas/shared/twitter_client.py` (add caching)
- `lambdas/shared/s3_store.py` (add twitter cache methods if needed)

---

### TASK-007: Add Twitter Parser to feed_fetcher.py
**Priority**: P1 | **Story Points**: 2 | **Status**: Not Started

**Description**: Add `_parse_twitter_v2()` method to FeedFetcher for consistency with existing parsers.

**Acceptance Criteria**:
- [ ] Method signature: `_parse_twitter_v2(data: dict, source_url: str, source_name: str) -> list[RawFeedItem]`
- [ ] Converts TweetItem to RawFeedItem for unified processing
- [ ] Preserves Twitter-specific metadata (metrics, hashtags)
- [ ] Integrates with existing dedup/filter pipeline

**Files**:
- `lambdas/shared/feed_fetcher.py` (modify)
- `tests/unit/shared/test_feed_fetcher.py` (add tests)

**Dependencies**: TASK-002

---

### TASK-008: Create Twitter Lambda Handler
**Priority**: P0 | **Story Points**: 3 | **Status**: Not Started

**Description**: Implement the Twitter Lambda handler with scheduled and event-driven modes.

**Acceptance Criteria**:
- [ ] Handler processes scheduled events (fetch AI/ML list)
- [ ] Handler processes spike events (targeted search)
- [ ] Stores raw tweets to S3: `current/twitter-ai-ml.json`
- [ ] Returns execution metrics (tweets fetched, cache hits, API calls)
- [ ] Proper error handling and logging

**Files**:
- `lambdas/twitter/handler.py` (implement)
- `tests/unit/lambdas/test_twitter_handler.py` (create)

**Dependencies**: TASK-003, TASK-004, TASK-006

---

## Sprint 3: Correlation Engine (Days 7-10)

### TASK-009: Create correlation_engine.py Module
**Priority**: P0 | **Story Points**: 5 | **Status**: Not Started

**Description**: Build the correlation engine that matches tweet signals with news headlines.

**Acceptance Criteria**:
- [ ] `CorrelationEngine` class with methods:
  - `detect_correlations(tweets: list[TweetItem], news: list[NewsItem]) -> list[CorrelatedNarrative]`
  - `calculate_velocity(tweets: list[TweetItem], window_hours: float) -> dict[str, float]`
  - `extract_entities(tweets: list[TweetItem]) -> list[str]`
  - `match_entities(tweet_entities: list[str], news_entities: list[str]) -> float`
- [ ] Velocity calculation: tweets per hour per entity
- [ ] Entity matching: Jaccard similarity + LLM enrichment
- [ ] Lead/lag time calculation
- [ ] Confidence scoring formula documented

**Files**:
- `lambdas/shared/correlation_engine.py` (create)
- `tests/unit/shared/test_correlation_engine.py` (create)

**Dependencies**: TASK-002

---

### TASK-010: Implement Velocity Spike Detection
**Priority**: P0 | **Story Points**: 3 | **Status**: Not Started

**Description**: Detect when tweet velocity exceeds baseline thresholds.

**Acceptance Criteria**:
- [ ] Calculate rolling baseline (24h average)
- [ ] Spike threshold: 2x baseline or 3+ mentions in 1 hour
- [ ] Return spike events with: entity, magnitude, timestamp, sample_tweets
- [ ] Trigger search when spike detected

**Files**:
- `lambdas/shared/correlation_engine.py` (add methods)
- `tests/unit/shared/test_correlation_engine.py` (add tests)

---

### TASK-011: Integrate Correlation Engine with Narrative Lambda
**Priority**: P0 | **Story Points**: 4 | **Status**: Not Started

**Description**: Enhance the existing narrative Lambda to use correlation engine for Twitter data.

**Acceptance Criteria**:
- [ ] Narrative handler loads Twitter data from S3
- [ ] Correlation engine runs on combined news + Twitter data
- [ ] CorrelatedNarrative objects included in narrative output
- [ ] Leading indicators highlighted in output
- [ ] No breaking changes to existing narrative output format

**Files**:
- `lambdas/narrative/handler.py` (modify)
- `tests/unit/lambdas/test_narrative_handler.py` (update)

**Dependencies**: TASK-008, TASK-009

---

## Sprint 4: LLM Integration & Polish (Days 11-14)

### TASK-012: Add Twitter Correlation LLM Prompts
**Priority**: P0 | **Story Points**: 3 | **Status**: Not Started

**Description**: Create LLM prompts for Twitter-enhanced narrative analysis.

**Acceptance Criteria**:
- [ ] `TWITTER_CORRELATION_PROMPT` in llm_client.py
- [ ] Prompt includes: news items, twitter items, velocity data
- [ ] Output schema: narratives, leading_signals, divergent_signals, questions
- [ ] Prompt tested with sample data
- [ ] Version tracked in prompt text

**Files**:
- `lambdas/shared/llm_client.py` (modify)
- `tests/unit/shared/test_llm_client.py` (add tests)

---

### TASK-013: Configure AI/ML Twitter List
**Priority**: P0 | **Story Points**: 1 | **Status**: Not Started

**Description**: Create the curated Twitter list configuration for AI/ML pilot.

**Acceptance Criteria**:
- [ ] Config in `config/feeds.json` or `config/twitter.json`:
  ```json
  {
    "twitter": {
      "ai-ml": {
        "list_id": "LIST_ID_HERE",
        "accounts": ["AnthropicAI", "OpenAI", "ylecun", "karpathy", "sama"],
        "search_keywords": ["GPT-5", "Claude 4", "AGI", "AI safety"],
        "fetch_interval_hours": 2
      }
    }
  }
  ```
- [ ] Create actual Twitter List with curated accounts
- [ ] Document account selection rationale

**Files**:
- `config/feeds.json` or `config/twitter.json` (modify/create)

---

### TASK-014: Implement Event-Driven Search Triggers
**Priority**: P1 | **Story Points**: 3 | **Status**: Not Started

**Description**: Trigger targeted Twitter searches when narrative spikes are detected.

**Acceptance Criteria**:
- [ ] Narrative Lambda can invoke Twitter Lambda with search query
- [ ] Search cooldown: minimum 60 minutes between searches
- [ ] Max 3 event searches per day (hard cap)
- [ ] Search results cached and added to narrative analysis

**Files**:
- `lambdas/narrative/handler.py` (modify)
- `lambdas/twitter/handler.py` (add search mode)

**Dependencies**: TASK-008, TASK-010

---

### TASK-015: Add Twitter Data to Frontend
**Priority**: P2 | **Story Points**: 3 | **Status**: Not Started

**Description**: Display Twitter correlation data in the SIGINT dashboard.

**Acceptance Criteria**:
- [ ] Narrative section shows correlation confidence
- [ ] Leading indicators highlighted with "📡 Twitter lead: Xh"
- [ ] Tweet count/velocity shown for correlated narratives
- [ ] No breaking changes to existing UI

**Files**:
- `frontend/app.js` (modify)
- `frontend/style.css` (modify)

**Dependencies**: TASK-011

---

### TASK-016: Documentation and Testing
**Priority**: P1 | **Story Points**: 2 | **Status**: Not Started

**Description**: Complete documentation and test coverage.

**Acceptance Criteria**:
- [ ] README updated with Twitter integration section
- [ ] AGENTS.md updated with Twitter-specific patterns
- [ ] All new code has >80% test coverage
- [ ] Integration test for full Twitter → Narrative flow
- [ ] API rate limit strategy documented

**Files**:
- `README.md` (modify)
- `AGENTS.md` (modify)
- `tests/integration/` (create tests)

---

## Task Dependency Graph

```
TASK-001 (SSM)
    │
    ├──► TASK-003 (twitter_client.py)
    │        │
    │        ├──► TASK-005 (list fetching)
    │        │
    │        └──► TASK-006 (S3 caching)
    │                  │
    │                  └──► TASK-008 (Lambda handler)
    │                            │
    │                            └──► TASK-011 (Narrative integration)
    │                                      │
    │                                      └──► TASK-015 (Frontend)
    │
    └──► TASK-004 (CDK infra)

TASK-002 (Models)
    │
    ├──► TASK-003 (twitter_client.py)
    │
    ├──► TASK-007 (feed_fetcher parser)
    │
    └──► TASK-009 (correlation_engine.py)
              │
              ├──► TASK-010 (velocity detection)
              │
              └──► TASK-011 (Narrative integration)

TASK-012 (LLM prompts) ──► TASK-011 (Narrative integration)

TASK-013 (Config) ──► TASK-008 (Lambda handler)

TASK-014 (Event search) ──► TASK-008 + TASK-010

TASK-016 (Docs) ──► All other tasks
```

---

## Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| API rate limit exceeded | High | Medium | Aggressive caching, usage alerts at 80% |
| X API changes/deprecation | High | Low | Abstract client, monitor API announcements |
| Low tweet quality | Medium | Medium | Engagement thresholds, verified accounts |
| Correlation false positives | Medium | High | Confidence thresholds, manual review flag |
| Lambda timeout on large datasets | Low | Medium | Pagination, async processing |

---

## Definition of Done

- [ ] All acceptance criteria met
- [ ] Unit tests pass with >80% coverage
- [ ] Pre-commit hooks pass (ruff, mypy)
- [ ] No governance violations
- [ ] Code reviewed
- [ ] Deployed to staging
- [ ] Manual verification in staging
- [ ] Documentation updated
