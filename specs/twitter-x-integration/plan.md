# Twitter/X Integration Plan

> **Strategy**: Hybrid (List-based baseline + Event-driven search)  
> **Depth**: Deep narrative correlation engine  
> **Pilot**: AI/ML category  
> **API Tier**: Free (1,500 reads/month constraint)

## Executive Summary

Integrate Twitter/X as a high-signal source for the SIGINT dashboard, using curated lists for baseline monitoring and event-driven search queries when narrative spikes are detected. The integration will correlate tweet velocity and engagement metrics with news headlines to surface emerging patterns with higher confidence.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Twitter/X Integration Architecture                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────────┐ │
│  │  Twitter Lambda  │────▶│   S3 Cache       │────▶│  Narrative Lambda    │ │
│  │  (Fetcher)       │     │   twitter/*.json │     │  (Correlator)        │ │
│  └────────┬─────────┘     └──────────────────┘     └──────────────────────┘ │
│           │                                                  │              │
│           ▼                                                  ▼              │
│  ┌──────────────────┐                              ┌──────────────────────┐ │
│  │  X API v2        │                              │  Correlation Engine  │ │
│  │  - Lists         │                              │  - Tweet velocity    │ │
│  │  - Search        │                              │  - Hashtag spikes    │ │
│  │  - Users         │                              │  - News ↔ Tweet      │ │
│  └──────────────────┘                              └──────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## API Budget Strategy

### Free Tier Constraints
- **Read limit**: ~1,500 tweets/month
- **Rate limit**: 1 request per 15 minutes per endpoint
- **Endpoints**: User timeline, List timeline, Search (limited)

### Budget Allocation (Monthly)

| Mode | Frequency | Calls/Day | Calls/Month | Tweets/Call | Total Tweets |
|------|-----------|-----------|-------------|-------------|--------------|
| **List Baseline** | Every 2 hours | 12 | 360 | 50 | ~400 effective* |
| **Event Search** | On spike detection | ~2 | ~60 | 10 | ~600 |
| **Reserve** | Emergency/manual | - | - | - | ~500 |

*Effective = unique tweets after deduplication across fetches

### Rate Limit Strategy

```python
# Aggressive caching + smart scheduling
TWITTER_CONFIG = {
    "list_fetch_interval_hours": 2,      # Baseline: 12 fetches/day
    "search_cooldown_minutes": 60,        # Min gap between searches
    "cache_ttl_hours": 4,                 # Serve from cache between fetches
    "spike_threshold": 3,                 # Entity mentions to trigger search
    "max_searches_per_day": 3,            # Hard cap on event searches
}
```

---

## Phase 1: Core Infrastructure

### 1.1 New Files

| File | Purpose |
|------|---------|
| `lambdas/twitter/handler.py` | Twitter fetcher Lambda |
| `lambdas/twitter/__init__.py` | Package init |
| `lambdas/shared/twitter_client.py` | X API v2 client with rate limiting |
| `lambdas/shared/correlation_engine.py` | Tweet ↔ News correlation logic |

### 1.2 Modified Files

| File | Changes |
|------|---------|
| `lambdas/shared/models.py` | Add `TweetItem`, `CorrelatedNarrative` models |
| `lambdas/shared/feed_fetcher.py` | Add `_parse_twitter_v2()` method |
| `lambdas/narrative/handler.py` | Integrate correlation engine |
| `infrastructure/app.py` | Add Twitter Lambda + SSM param |
| `config/feeds.json` | Add Twitter accounts/lists config |

### 1.3 SSM Parameters

```bash
aws ssm put-parameter \
  --name '/sigint/x-bearer-token' \
  --type 'SecureString' \
  --value 'AAAA...' \
  --region us-east-1
```

---

## Phase 2: AI/ML Pilot Configuration

### Curated Twitter List: AI/ML Signal

| Account | Rationale | Signal Type |
|---------|-----------|-------------|
| @AnthropicAI | Official announcements | Product launches |
| @OpenAI | Official announcements | Product launches |
| @GoogleDeepMind | Research releases | Papers, breakthroughs |
| @ylecun | Meta AI Chief, commentary | Industry insights |
| @kaboroe | Andrej Karpathy, deep technical | Trends, tutorials |
| @sama | OpenAI CEO | Strategy, policy |
| @EMostaque | Stability AI CEO | Open source AI |
| @ClementDelworthy | Hugging Face CEO | OSS ecosystem |
| @ai_explained_ | High-quality summaries | Paper breakdowns |
| @_akhaliq | Paper aggregator | Research velocity |

### Event Search Triggers

When narrative detector sees spike in these entities, trigger search:
- Model names: `GPT-5`, `Claude 4`, `Gemini 2`, `Llama 4`
- Companies: `OpenAI`, `Anthropic`, `Google AI`, `Meta AI`
- Concepts: `AGI`, `AI safety`, `AI regulation`, `open weights`

---

## Phase 3: Deep Narrative Correlation

### Correlation Engine Logic

```python
class CorrelationEngine:
    """Correlates tweet signals with news headlines for pattern detection."""
    
    def detect_correlations(
        self,
        tweets: list[TweetItem],
        news_items: list[NewsItem],
        window_hours: int = 6
    ) -> list[CorrelatedNarrative]:
        """
        Find patterns where:
        1. Tweet velocity spikes precede news (leading indicator)
        2. News breaks, tweets amplify (confirmation signal)
        3. Hashtag clusters match news entities (correlation)
        """
        pass
    
    def calculate_velocity(self, tweets: list[TweetItem]) -> dict[str, float]:
        """
        Calculate tweet velocity per entity.
        Returns: {"GPT-5": 4.2, "Anthropic": 2.1, ...}
        """
        pass
    
    def extract_twitter_entities(self, tweets: list[TweetItem]) -> list[str]:
        """
        Extract entities from tweets:
        - Native hashtags (#AI, #GPT5)
        - Cashtags ($NVDA, $MSFT)
        - Mentions (@OpenAI)
        - LLM-extracted entities
        """
        pass
```

### Correlation Output Model

```python
@dataclass
class CorrelatedNarrative:
    """A narrative with cross-source evidence."""
    
    title: str                          # "GPT-5 Release Imminent"
    confidence: float                   # 0.0 - 1.0
    evidence: list[Evidence]            # News + Tweet sources
    velocity_score: float               # Tweet activity intensity
    lead_time_hours: float | None       # If tweets preceded news
    questions: list[str]                # LLM-generated questions
    
    # Correlation metadata
    news_sources: list[str]
    twitter_sources: list[str]
    hashtags: list[str]
    entity_matches: list[str]           # Entities appearing in both
```

---

## Phase 4: LLM Integration

### Twitter-Aware Prompt Enhancement

Add to `llm_client.py`:

```python
TWITTER_CORRELATION_PROMPT = """
You are analyzing correlated signals between news headlines and Twitter activity.

NEWS ITEMS:
{news_items}

TWITTER SIGNALS:
{twitter_items}

VELOCITY DATA:
{velocity_data}

Identify:
1. LEADING INDICATORS: Twitter discussion that precedes news coverage
2. AMPLIFICATION: News stories gaining significant Twitter traction
3. DIVERGENCE: High Twitter activity with no corresponding news (potential breaking)
4. QUESTIONS: What should we be asking about these patterns?

Output JSON with:
- narratives: [{title, confidence, evidence_summary, questions}]
- leading_signals: [{entity, tweet_velocity, news_lag_hours}]
- divergent_signals: [{topic, twitter_intensity, news_coverage: "none"|"minimal"}]
"""
```

---

## Implementation Tasks

### Sprint 1: Infrastructure (Days 1-3)

- [ ] Create `lambdas/shared/twitter_client.py` with X API v2 client
- [ ] Add `TweetItem` model to `models.py`
- [ ] Store X bearer token in SSM
- [ ] Create `lambdas/twitter/handler.py` skeleton

### Sprint 2: Fetching (Days 4-6)

- [ ] Implement list timeline fetching
- [ ] Implement S3 caching layer
- [ ] Add rate limit tracking (avoid overages)
- [ ] Add `_parse_twitter_v2()` to feed_fetcher.py

### Sprint 3: Correlation (Days 7-10)

- [ ] Create `correlation_engine.py`
- [ ] Implement velocity calculation
- [ ] Implement entity matching (tweet ↔ news)
- [ ] Integrate with narrative Lambda

### Sprint 4: LLM & Polish (Days 11-14)

- [ ] Add Twitter correlation prompts
- [ ] Implement event-driven search triggers
- [ ] Frontend: Display correlation confidence
- [ ] Testing & documentation

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| API budget utilization | <90% | Monthly tweet reads |
| Correlation hit rate | >60% | Tweets matching news entities |
| Leading indicator detection | >3/week | Tweets preceding news by >1hr |
| Narrative confidence lift | +15% | Correlated vs single-source |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| API overages | Hard daily caps, aggressive caching |
| Rate limit errors | Exponential backoff, request queuing |
| Low-quality tweets | Engagement thresholds, verified accounts priority |
| Account suspension | Store bearer token in SSM, easy rotation |

---

## Next Steps

1. **Run agentic SDD workflow** to generate detailed spec and tasks:
   ```bash
   uv run smactorio workflow run -f "Integrate Twitter/X feeds with hybrid list-based and event-driven search approach, deep narrative correlation, piloting with AI/ML category" --verbose
   ```

2. **Review generated artifacts** in `specs/` directory

3. **Begin Sprint 1** implementation

---

## Notes on "Intent-Driven Development"

The user raised the idea of renaming "Specification-Driven Development" to "Intent-Driven Development" (IDD). This better captures the workflow:

- **Intent**: User describes what they want (natural language)
- **Specification**: System derives formal spec from intent
- **Implementation**: Agents execute against spec

Consider renaming `smactorio` commands from `speckit` to `intentkit` or similar in a future iteration.
