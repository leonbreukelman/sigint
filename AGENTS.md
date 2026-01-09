# AGENTS.md: Guidance for AI Agents in sigint

This file provides actionable instructions for AI coding agents working in the **sigint** repository. User prompts override all contents. Nearest AGENTS.md takes precedence in subdirectories.

> **Core Directive:** All agents must reference governance principles via `uv run smactorio constitution list` (or read `.specify/memory/governance-catalog.yaml` directly) before planning or coding. The `constitution.md` file is a derived human-readable view—never parse it for data.

## 0. Agentic SDD Workflow (RECOMMENDED)

**This is the primary development path.** When implementing features, use the autonomous multi-agent workflow:

```bash
# Full specification-driven development workflow
uv run smactorio workflow run --feature "Your feature description here"

# With verbose output
uv run smactorio workflow run -f "Add user authentication" --verbose

# Use faster model tier for quick iterations
uv run smactorio workflow run -f "Add health endpoint" --model fast
```

**What it does (orchestrated pipeline):**
1. **AnalystAgent** — Extracts entities, relationships, requirements
2. **ClarificationAgent** — Identifies ambiguities (marks with [NEEDS CLARIFICATION]); runs **only if ambiguities are detected**
3. **ConstitutionAgent** — Validates against governance principles
4. **ArchitectAgent** — Generates architecture options; runs **only for complex features**
5. **TaskDecomposerAgent** — Breaks down into implementation tasks
6. **CodeGeneratorAgent** — Generates implementation code
7. **ValidatorAgent** — Generates test cases and validates

**Pipeline variants:**
- **Simple features:** Analyst → Clarification (if needed) → Constitution → TaskDecomposer → CodeGenerator → Validator
- **Complex features:** Analyst → Clarification (if needed) → Constitution → Architect → TaskDecomposer → CodeGenerator → Validator

**Output:** Creates `spec.md`, `plan.md`, and `tasks.md` in the output directory.

**Individual agents** (for targeted analysis):
```bash
uv run smactorio agent list                    # List available agents
uv run smactorio agent run analyst -f "..."   # Run single agent
```

> ⚠️ **Prefer `smactorio workflow run` over slash commands** for spec creation. Slash commands (like `/speckit.specify`) are fallback for IDE contexts only.

## 1. Tooling Constraints (Strict)

- **Dependency Management:** Use `uv` exclusively.
  - Install/sync: `uv sync`
  - Add package: `uv add <package>`
  - Remove package: `uv remove <package>`
  - Run script: `uv run <script.py>`
- **Prohibited:** Never use `pip`, `poetry`, or `conda` directly.

## 2. Testing & Quality Gates

- Runner: `uv run pytest`
- Coverage: `uv run pytest --cov`
- Linting: `uv run ruff check .`
- Formatting: `uv run ruff format .`
- Type checking: `uv run mypy .`
- **Pre-commit (REQUIRED):** Before ANY commit, run `uv run pre-commit run --all-files`
- **Mandate:** Changes are incomplete until:
  - All tests pass without regression.
  - Pre-commit hooks pass (ruff, mypy, formatting).
  - Coverage does not decrease.
  - Add/update tests proactively (TDD preferred: tests before implementation).

## 3. Reuse Supremacy

- **Priority:** Always search existing code, `.specify/`, and `.memory/` first.
- **Constraint:** Before creating new modules/files, log a "Novelty Justification" proving no existing asset is adaptable (<10 lines refactoring).
- **Order:** Composition > Inheritance > New implementation.

## 4. Boundaries & Security

- **Protected Paths:** Never modify `.github/workflows`, `.specify/memory/governance-catalog.yaml`, or infrastructure configs without explicit approval.
- **Secrets:** Do not output or hardcode credentials.

## 5. Suggested Multi-Agent Behaviors

For orchestrated workflows (e.g., CrewAI, OpenAI Agents):

- **Orchestrator:** Decompose tasks; generate preliminary specs in `.specify/` if missing; output structured plans (YAML/JSON).
- **Reuser (Scout):** Enforce reuse checks; validate novelty justifications.
- **Implementer (Builder):** Follow TDD; prefer async for I/O; strict `uv` compliance.
- **Validator (Auditor):** Run coverage/lint; reject reductions in quality.
- **Maintainer:** Optimize this file and CI.

## 6. Handoff Protocol (For Multi-Turn/Multi-Agent)

Use this YAML schema for state preservation:

```yaml
Current_State: "Concise summary of progress."
Next_Step: "Specific immediate task."
Constraints: "Key reminders (e.g., USE UV ONLY; REFERENCE CONSTITUTION)."
References:
  - "Path:line(s) to relevant spec/code"
```

## 7. Dev Tips

- Environment: `uv venv` for isolation.
- Run locally: `uv run <entrypoint>`

## 8. SIGINT-Specific Patterns

### Lambda Handler Pattern
```python
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    start_time = time.time()
    # ... logic ...
    duration_ms = int((time.time() - start_time) * 1000)
    return {"statusCode": 200, "body": json.dumps({..., "duration_ms": duration_ms})}
```

### Key Files for Common Tasks
| Task | Files to Modify |
|------|----------------|
| Add news category | `shared/models.py` (Category enum), `reporters/handler.py` (CATEGORY_FEEDS), `llm_client.py` (CATEGORY_PROMPTS), `infrastructure/app.py` (EventBridge), `config/feeds.json` |
| Add new feed source | `reporters/handler.py` (CATEGORY_FEEDS dict), `config/feeds.json` |
| Modify LLM behavior | `shared/llm_client.py` (CATEGORY_PROMPTS) |
| Add data model | `shared/models.py`, update `shared/__init__.py` exports |
| Change S3 structure | `shared/s3_store.py` (follow key naming convention) |
| Modify markets ticker | `reporters/handler.py` (CATEGORY_FEEDS[Category.MARKETS]), `llm_client.py` (CATEGORY_PROMPTS[Category.MARKETS]), `frontend/app.js` (renderTickerItem), `frontend/style.css` (.ticker-*) |

### Test Commands
```bash
# Run all tests
uv run pytest

# Test specific Lambda
uv run pytest tests/unit/lambdas/test_reporters_handler.py -v

# Test with coverage
uv run pytest --cov=lambdas --cov-report=term-missing
```

### Local Lambda Testing
```bash
cd lambdas
export DATA_BUCKET=your-test-bucket
export ANTHROPIC_API_KEY=your-key
python -c "from reporters.handler import handler; print(handler({'category': 'ai-ml'}, None))"
```

## 9. Governance Integration

- **Source of Truth:** `.specify/memory/governance-catalog.yaml` (OSCAL Catalog format)
- **Derived View:** `.specify/memory/constitution.md` (auto-generated Markdown, for humans only)
- **CLI Commands:**
  - `uv run smactorio constitution list` — View all principles
  - `uv run smactorio constitution add --group <g> --title <t> --statement <s>` — Add principle
  - `uv run smactorio constitution edit <id> --statement <s>` — Modify principle
  - `uv run smactorio constitution validate` — Validate catalog schema
  - `uv run smactorio constitution check <spec.md>` — Check spec against principles

**IMPORTANT:** Never parse `constitution.md` for data. Always use CLI commands or read the YAML catalog directly.