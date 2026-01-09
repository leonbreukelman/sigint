# sigint Development Guidelines

> **Purpose**: Instructions for GitHub Copilot and AI coding assistants working in the sigint repository.

## Agentic SDD Workflow (PRIMARY PATH)

**When building new features, use the autonomous multi-agent workflow:**

```bash
# Full specification-driven development (RECOMMENDED)
uv run smactorio workflow run --feature "Your feature description"

# Verbose output for debugging
uv run smactorio workflow run -f "Add user authentication" --verbose

# Fast mode for quick iterations
uv run smactorio workflow run -f "Add health endpoint" --model fast
```

The workflow automatically:
1. Performs a complexity assessment to determine routing
2. Analyst – analyzes requirements and extracts entities
3. Clarification – identifies ambiguities (conditional, only if needed)
4. Constitution – validates against governance principles
5. Architect – generates architecture (conditional, only for complex features)
6. TaskDecomposer – creates implementation tasks
7. CodeGenerator – generates code
8. Validator – generates test cases and validates

**Output:** `spec.md`, `plan.md`, `tasks.md` in `specs/` directory.

> ⚠️ **Prefer `smactorio workflow run` over slash commands** (like `/speckit.specify`) for spec creation. Slash commands are fallback for IDE-only contexts.

## Governance Integration (CRITICAL)

### Source of Truth

| File | Role |
|------|------|
| `.specify/memory/governance-catalog.yaml` | **Authoritative** — OSCAL catalog, machine-readable |
| `.specify/memory/constitution.md` | **Derived** — Auto-generated Markdown for humans |

**NEVER parse `constitution.md` for data.** Always use CLI commands or read the YAML directly.

### CLI Commands

```bash
# View all principles
uv run smactorio constitution list

# Add a principle
uv run smactorio constitution add \
  --group <core|development|architecture|quality> \
  --title "Principle Title" \
  --statement "The normative rule text" \
  --severity <NON-NEGOTIABLE|RECOMMENDED|OPTIONAL>

# Edit a principle
uv run smactorio constitution edit --control-id <id> --statement "New text"

# Remove a principle (BREAKING CHANGE)
uv run smactorio constitution remove --control-id <id> --force

# Validate catalog
uv run smactorio constitution validate

# Check spec compliance
uv run smactorio constitution check <path/to/spec.md>
```

## Tooling Constraints

- **Use `uv` exclusively** for all Python operations:
  - `uv sync` — Install/sync dependencies
  - `uv add <package>` — Add package
  - `uv run <script>` — Run scripts
- **Never use** `pip`, `poetry`, or `conda` directly

## Quality Gates

Before any commit:

```bash
uv run pre-commit run --all-files  # REQUIRED
uv run pytest                       # Tests must pass
uv run pytest --cov                 # Coverage must not decrease
uv run ruff check .                 # Linting
uv run mypy .                       # Type checking
```

## Project Structure

```
src/                     # Main package
.specify/memory/         # Governance data
  governance-catalog.yaml   # OSCAL catalog (source of truth)
  constitution.md           # Rendered Markdown (derived)
  backups/                  # Timestamped catalog backups
specs/                   # Feature specifications
tests/                   # Test suites (unit, integration, contract)
```

## Development Principles

1. **Spec-Driven**: All features start with a specification in `specs/`
2. **Test-First**: Write tests before implementation (TDD)
3. **Library-First**: Core logic as importable library, CLI wraps it
4. **Reuse Supremacy**: Search existing code before creating new

## References

- [AGENTS.md](../AGENTS.md) — Universal agent instructions
- [README.md](../README.md) — Project overview