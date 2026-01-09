<!--
  ⚠️ AUTO-GENERATED FILE - DO NOT EDIT DIRECTLY

  This file is rendered from the authoritative YAML catalog:
    .specify/memory/governance-catalog.yaml

  To modify governance principles, use the smactorio CLI:
    uv run smactorio constitution list          # View principles
    uv run smactorio constitution add ...       # Add principle
    uv run smactorio constitution edit ...      # Edit principle
    uv run smactorio constitution remove ...    # Remove principle

  Changes made directly to this file WILL BE OVERWRITTEN.
-->

> [!WARNING]
> **This file is auto-generated from governance-catalog.yaml.**
> Do not edit directly. Use `uv run smactorio constitution` CLI commands.

# Smactorio Constitution

## Core Principles

### core-001. Documentation Required
All features in sigint MUST be documented before release.

**Rationale**: Documentation ensures knowledge transfer and reduces onboarding time for new team members.

### II. Category Enum Exhaustiveness (NON-NEGOTIABLE)
When adding new news categories to sigint, you MUST: 1) Add to Category enum in shared/models.py, 2) Add feed configuration in CATEGORY_FEEDS, 3) Add LLM prompt in CATEGORY_PROMPTS, 4) Add EventBridge schedule in infrastructure/app.py, 5) Update config/feeds.json.

## Development Workflow

### dev-001. Version Control
All code changes in sigint MUST be committed to version control with meaningful commit messages.

**Rationale**: Version control provides audit trail, enables collaboration, and supports rollback capabilities.

### II. Pydantic Models Required (NON-NEGOTIABLE)
All data structures exchanged between components in sigint MUST use Pydantic models defined in shared/models.py. Never use raw dicts for domain objects (NewsItem, CategoryData, NarrativePattern, etc.).

### III. Feed Configuration Source
Feed URLs for categories SHOULD be defined in config/feeds.json as the canonical source. The CATEGORY_FEEDS dict in handler.py is the runtime source; any new feeds should be added to both. Prefer external config over hardcoded values.

### IV. LLM Prompt Versioning
LLM prompts in CATEGORY_PROMPTS (llm_client.py) SHOULD be treated as critical business logic. Changes to prompts require: 1) documenting the intent, 2) testing with sample inputs, 3) considering cost implications (token usage).

## Architecture

### arch-001. Infrastructure as Code
Infrastructure for sigint SHOULD be defined as code and version controlled.

**Rationale**: IaC ensures reproducible deployments, enables disaster recovery, and documents infrastructure decisions.

### II. Lambda Handler Contract (NON-NEGOTIABLE)
All Lambda handlers in sigint MUST follow the established pattern: accept (event: dict, context: Any) -> dict with statusCode and body keys. Handlers MUST use structured logging and include duration_ms in success responses.

### III. Shared Module Usage (NON-NEGOTIABLE)
All Lambda functions MUST import shared modules via the Lambda layer pattern (from shared.X import Y). Never use relative imports or hardcode paths. The shared layer provides: models, feed_fetcher, llm_client, s3_store.

### IV. Secrets via SSM Only (NON-NEGOTIABLE)
All secrets in sigint (API keys, credentials) MUST be stored in AWS SSM Parameter Store with SecureString type. Lambda functions MUST fetch secrets at runtime via the ANTHROPIC_API_KEY_SSM_PARAM pattern. Never hardcode or commit secrets.

### V. S3 Key Naming Convention (NON-NEGOTIABLE)
S3 keys in sigint MUST follow the pattern: current/{category}.json for live data, archive/{YYYY-MM-DD}/{category}.json for historical data, current/dashboard.json for frontend state, current/narratives.json for patterns.

## Quality & Testing

### qual-001. Automated Testing
All features in sigint MUST have automated tests before deployment.

**Rationale**: Automated testing catches regressions early and enables confident refactoring.

### II. LLM Error Handling (NON-NEGOTIABLE)
All LLM calls in sigint MUST have explicit error handling with: 1) timeout handling, 2) graceful degradation on API errors, 3) structured logging of failures, 4) fallback behavior that allows the system to continue operating.

### III. Mock AWS in Tests (NON-NEGOTIABLE)
All unit tests for Lambda handlers and S3Store MUST use moto (@mock_aws) to mock AWS services. Tests MUST NOT make real AWS API calls. Integration tests requiring real AWS should be marked with @pytest.mark.integration.

### IV. Relevance Score Bounds (NON-NEGOTIABLE)
All relevance_score and strength values in sigint MUST be floats between 0.0 and 1.0 inclusive. Pydantic Field constraints (ge=0, le=1) enforce this. Never use unbounded numeric scores.

---

**Version**: 1.15.0 | **Last Modified**: 2026-01-09