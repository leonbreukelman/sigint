# SIGINT // Signals Intelligence Dashboard

An AI-powered news intelligence platform that autonomously scans, curates, and presents high-signal information across multiple categories.

```
┌─────────────────────────────────────────────────────────────────┐
│  [SIGINT] // signals intelligence                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │ GEOPOLITICAL│ │   AI / ML   │ │  DEEP TECH  │ │  CRYPTO   │ │
│  │             │ │             │ │             │ │  FINANCE  │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
│  ══════════════════════════════════════════════════════════════ │
│  ◀ BTC $90,269 ▲+0.5%  ETH $3,421 ▼-1.2%  SOL $138 ▲+2.9% ...  │
│  ══════════════════════════════════════════════════════════════ │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              NARRATIVE TRACKER                            │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Features

- **Autonomous AI Reporters**: Each category has its own AI agent that scans relevant RSS feeds and APIs
- **Markets Ticker**: Bloomberg-style scrolling ticker with live crypto prices. An AI agent monitors price movements and highlights notable movers (>5% swings) for display
- **Narrative Detection**: Cross-source pattern recognition identifies emerging trends
- **Breaking News**: Editor agent elevates urgent items automatically
- **24H Archive**: Full history of all curated items
- **Real-time Updates**: Tiered refresh rates (5-30 min depending on category)
- **Zero Database**: S3-only architecture for simplicity and cost

## Architecture

```
CloudFront CDN
      │
      ├── /          → S3 Frontend (static HTML/CSS/JS)
      │
      └── /data/*    → S3 Data (JSON files)
                           ▲
                           │ writes
                           │
              ┌────────────┴────────────┐
              │     Lambda Functions     │
              │  ┌─────────────────────┐ │
              │  │ Reporter (per cat)  │ │
              │  │ Editor              │ │
              │  │ Narrative Tracker   │ │
              │  └─────────────────────┘ │
              └────────────────────────┬─┘
                                       │
                            EventBridge Scheduler
```

## Categories & Update Frequency

| Category | Frequency | Focus |
|----------|-----------|-------|
| **Crypto/Finance** | 5 min | Markets, crypto, Fed, regulatory |
| **AI/ML** | 10 min | Models, research, AI companies |
| **Geopolitical** | 15 min | Conflicts, diplomacy, policy |
| **Deep Tech** | 15 min | Semiconductors, quantum, biotech |
| **Markets** | 5 min | Crypto prices via CoinGecko, LLM highlights movers |
| **Narrative** | 30 min | Cross-source pattern detection |
| **Editor** | 5 min | Breaking news synthesis |

## Deployment

### Prerequisites

- AWS CLI configured with appropriate credentials
- AWS CDK (`npm install -g aws-cdk`)
- Python 3.11+
- Anthropic API key

### Step 1: Store your Anthropic API Key

```bash
aws ssm put-parameter \
  --name '/sigint/anthropic-api-key' \
  --type 'SecureString' \
  --value 'sk-ant-YOUR-KEY-HERE' \
  --region us-east-1
```

### Step 2: Deploy

```bash
chmod +x deploy.sh
./deploy.sh
```

The script will:
1. Bootstrap CDK
2. Deploy all infrastructure
3. Upload frontend
4. Initialize data structures
5. Output the dashboard URL

### Step 3: Wait

The agents run on schedules. First data should appear within ~15 minutes.

## Cost Estimate

| Service | Monthly Est. |
|---------|-------------|
| Lambda | $5-10 |
| S3 | ~$1 |
| CloudFront | $8-10 |
| EventBridge | ~$0.15 |
| Claude Haiku | $15-25 |
| CoinGecko API | Free (no key) |
| **Total** | **~$30-50** |

## Local Development

### Test a Reporter Locally

```bash
cd lambdas
export ANTHROPIC_API_KEY=your-key
export DATA_BUCKET=your-bucket
python -c "from reporters.handler import handler; print(handler({'category': 'ai-ml'}, None))"
```

### Test Markets Ticker Locally

```bash
cd lambdas
export ANTHROPIC_API_KEY=your-key
export DATA_BUCKET=your-bucket
python -c "from reporters.handler import handler; print(handler({'category': 'markets'}, None))"
```

### View Frontend Locally

```bash
cd frontend
python -m http.server 8000
# Open http://localhost:8000
```

## Configuration

### Adding/Removing Feeds

Edit `lambdas/reporters/handler.py` and modify `CATEGORY_FEEDS`:

```python
CATEGORY_FEEDS = {
    Category.AI_ML: [
        "https://new-feed-url.com/rss",
        # ...
    ],
}
```

Redeploy with `cdk deploy`.

### Adjusting Update Frequency

Edit `infrastructure/app.py` and modify the EventBridge schedules:

```python
events.Rule(
    self, "AiMlSchedule",
    schedule=events.Schedule.rate(Duration.minutes(5)),  # Changed from 10
    # ...
)
```

### Customizing Agent Prompts

Edit `lambdas/shared/llm_client.py` and modify `CATEGORY_PROMPTS`.

For the Markets ticker, adjust the selection threshold (default >5% price change) in `CATEGORY_PROMPTS[Category.MARKETS]`:

```python
Category.MARKETS: """You are a market analyst. Prioritize coins with >5% 24h price movement..."""
```

## Data Structure

```
s3://sigint-data-{account}/
├── current/
│   ├── geopolitical.json
│   ├── ai-ml.json
│   ├── deep-tech.json
│   ├── crypto-finance.json
│   ├── markets.json          # Ticker data
│   ├── narrative.json
│   ├── breaking.json
│   ├── narratives.json
│   └── dashboard.json
├── archive/
│   └── 2024-01-08/
│       ├── geopolitical.json
│       └── ...
└── config/
    └── feeds.json
```

## Troubleshooting

### No Data Appearing

1. Check Lambda logs in CloudWatch
2. Verify Anthropic API key is valid
3. Check S3 bucket permissions

### High LLM Costs

1. Reduce feed count per category
2. Increase update intervals
3. Add more aggressive pre-LLM filtering

### Frontend Not Loading

1. Check CloudFront invalidation completed
2. Verify S3 bucket policy allows CloudFront access
3. Check browser console for CORS errors

### Markets Ticker Not Showing

1. Hard refresh browser (Ctrl+Shift+R / Cmd+Shift+R)
2. Wait 2-5 min for CloudFront cache propagation
3. Verify `markets.json` has properly formatted titles: `"Bitcoin: $90,000.00 (+5.5%)"`
4. Check that at least one item matches the expected format (items with malformed titles are filtered)

## License

MIT

## Credits

Inspired by [Situation Monitor](https://hipcityreg.github.io/situation-monitor/)
