````chatagent
---
description: Manage governance principles using the smactorio CLI. Add, edit, remove, or list principles in the OSCAL catalog.
handoffs:
  - label: Build Specification
    agent: speckit.specify
    prompt: Implement the feature specification based on the updated constitution. I want to build...
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## CRITICAL: Data Source Rule (FR-015)

**YAML is the ONLY source of truth for principles.**

- **ALWAYS** use `uv run smactorio constitution list` to read current principles
- **NEVER** parse the Markdown `.specify/memory/constitution.md` for data
- The Markdown file is for **human preview only** — it is auto-generated from the YAML catalog

## Available Commands

### List Principles
```bash
uv run smactorio constitution list
uv run smactorio constitution list --format json  # For structured output
```

### Add a Principle
```bash
uv run smactorio constitution add \
  --group <core|development|architecture|quality> \
  --title "Principle Title" \
  --statement "The normative rule text" \
  --rationale "Optional explanation" \
  --severity <NON-NEGOTIABLE|RECOMMENDED|OPTIONAL>
```

### Edit a Principle
```bash
uv run smactorio constitution edit \
  --control-id <control-id> \
  --title "New title" \
  --statement "New statement" \
  --rationale "New rationale" \
  --severity <NON-NEGOTIABLE|RECOMMENDED|OPTIONAL>
```

### Remove a Principle
```bash
uv run smactorio constitution remove \
  --control-id <control-id> \
  --force  # Skip confirmation
```

**Warning**: Removal is a BREAKING CHANGE! It increments the MAJOR version.

### Validate Catalog
```bash
uv run smactorio constitution validate
```

### Check Spec Compliance
```bash
uv run smactorio constitution check <path/to/spec.md>
```

## Workflow

1. **Read current state**: Run `uv run smactorio constitution list` to see existing principles
2. **Discuss with user**: Understand what principle change they want
3. **Validate content**: Ensure title, statement, and group are appropriate
4. **Execute command**: Run the appropriate `smactorio constitution` subcommand
5. **Confirm result**: Report success or error, including version change

## Version Semantics (Automatic)

Version changes are automatic based on operation:
- **ADD**: Increments MINOR version (e.g., 1.0.0 → 1.1.0)
- **EDIT**: Increments PATCH version (e.g., 1.1.0 → 1.1.1)
- **REMOVE**: Increments MAJOR version (e.g., 1.1.1 → 2.0.0)

## Placeholder Support

The following placeholders are automatically resolved in statements/rationale:
- `[PROJECT_NAME]` → Project name
- `[DATE]` → Current date in ISO 8601 format
- `[VERSION]` → Current catalog version

## Example Session

User: "Add a principle about documentation"

Agent:
1. First, check current principles:
   ```bash
   uv run smactorio constitution list
   ```

2. Add the new principle:
   ```bash
   uv run smactorio constitution add \
     --group development \
     --title "Documentation First" \
     --statement "All public APIs must have documentation before implementation." \
     --severity RECOMMENDED
   ```

3. Report: "Added 'Documentation First' (development-001). Version: 1.0.0 → 1.1.0"

---

User: "Make the documentation principle non-negotiable"

Agent:
1. List principles to get the control ID:
   ```bash
   uv run smactorio constitution list
   ```

2. Edit the severity:
   ```bash
   uv run smactorio constitution edit \
     --control-id development-001 \
     --severity NON-NEGOTIABLE
   ```

3. Report: "Updated development-001 to NON-NEGOTIABLE. Version: 1.1.0 → 1.1.1"

````