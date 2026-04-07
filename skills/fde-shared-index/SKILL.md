---
name: fde-shared-index
description: Set up shared indices for cross-codebase search. Explains indexing shared SDKs once globally, configuring projects to reference them, and using scope parameter in search (all/local/shared:name). References CLI commands for shared index management.
---

# FDE Shared Index

Set up and use shared indices for efficient cross-codebase search across multiple customer projects.

## When to use

- **Onboarding to a new customer** — check if shared SDKs are already indexed
- **Working with common frameworks** — avoid re-indexing the same SDK repeatedly
- **Setting up a new project** — configure shared index references
- **Cross-project research** — search patterns across multiple codebases

## When NOT to use

- Single isolated project with no shared dependencies
- When all dependencies are already indexed in the project
- Quick one-off searches that don't justify setup time

## Concepts

### What are Shared Indices?

Shared indices allow you to index common SDKs, frameworks, and libraries **once** and reference them from multiple projects. This:

- **Saves time** — No re-indexing the same SDK for each customer
- **Saves storage** — One copy of the index instead of duplicates
- **Enables cross-project search** — Find patterns across all customers using a framework

### Scope Parameter

The `scope` parameter controls where Mimir searches:

| Scope | Description | Use Case |
|-------|-------------|----------|
| `all` | Project + all shared indices (default) | Comprehensive search |
| `local` | Project index only | Customer-specific code |
| `shared:<name>` | Specific shared index only | SDK/framework patterns |

## CLI Commands

### List Shared Indices

```bash
python mimir-projects.py shared list
```

Output:
```
Shared Indices:
  - stripe-sdk (indexed 2026-04-01, 2.3M vectors)
  - nextjs-docs (indexed 2026-03-28, 5.1M vectors)
  - fastapi (indexed 2026-04-05, 1.8M vectors)
```

### Create Shared Index

```bash
python mimir-projects.py shared create <name> <source-path>
```

Example:
```bash
# Index Stripe SDK from local clone
python mimir-projects.py shared create stripe-sdk ~/sdk/stripe-python

# Index from GitHub URL
python mimir-projects.py shared create nextjs-docs https://github.com/vercel/next.js/tree/main/docs
```

### Update Shared Index

```bash
python mimir-projects.py shared update <name>
```

Example:
```bash
python mimir-projects.py shared update stripe-sdk
```

### Delete Shared Index

```bash
python mimir-projects.py shared delete <name>
```

### Configure Project to Use Shared Index

```bash
python mimir-projects.py shared link <project-name> <shared-index-name>
```

Example:
```bash
python mimir-projects.py shared link customer-a stripe-sdk
```

## Tools

### search with scope

Search across project and shared indices.

```
search(query="subscription handling", scope="all", top_k=10)
search(query="subscription handling", scope="local", top_k=10)
search(query="subscription handling", scope="shared:stripe-sdk", top_k=10)
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `query` | yes | — | Natural language search query |
| `scope` | no | `all` | `all`, `local`, or `shared:<name>` |
| `top_k` | no | `5` | Number of results |

## Workflow

```
New project received
         │
         ▼
Check existing shared indices
    └── python mimir-projects.py shared list
         │
         ├── SDK already indexed → Link to project
         │   └── python mimir-projects.py shared link <project> <shared>
         │
         └── SDK not indexed → Create shared index
             └── python mimir-projects.py shared create <name> <path>
                 └── python mimir-projects.py shared link <project> <name>
         │
         ▼
Search with appropriate scope
    ├── scope="all" — Comprehensive search
    ├── scope="local" — Customer code only
    └── scope="shared:<name>" — SDK patterns only
         │
         ▼
Periodic maintenance
    └── python mimir-projects.py shared update <name>
```

## Output Format

### Search Results by Scope

**scope="all" (default):**
```
Results from project + shared indices:
  [project] src/billing/subscription.py (score=0.92)
  [shared:stripe-sdk] stripe/subscription.py (score=0.88)
  [project] src/models/plan.py (score=0.75)
  [shared:stripe-sdk] stripe/api_resources/subscription.py (score=0.71)
```

**scope="local":**
```
Results from project only:
  src/billing/subscription.py (score=0.92)
  src/models/plan.py (score=0.75)
  src/api/v1/subscriptions.py (score=0.68)
```

**scope="shared:stripe-sdk":**
```
Results from stripe-sdk:
  stripe/subscription.py (score=0.88)
  stripe/api_resources/subscription.py (score=0.71)
  stripe/checkout/session.py (score=0.65)
```

## Example

### Example: Setting up shared Stripe SDK index

```
# Step 1: Check existing shared indices
python mimir-projects.py shared list
# Output: No shared indices found

# Step 2: Create shared index for Stripe SDK
python mimir-projects.py shared create stripe-sdk ~/sdk/stripe-python
# Output: Created shared index 'stripe-sdk' with 2.3M vectors

# Step 3: Link to customer project
python mimir-projects.py shared link customer-a stripe-sdk
# Output: Linked 'stripe-sdk' to project 'customer-a'

# Step 4: Search with scope
search(query="subscription cancellation", scope="all", top_k=10)
# Returns results from both customer-a code and stripe-sdk

# Step 5: Search SDK only for patterns
search(query="subscription cancellation", scope="shared:stripe-sdk", top_k=10)
# Returns only Stripe SDK patterns for reference
```

### Example: Cross-project pattern discovery

```
# Find how multiple customers implement Stripe webhooks
# (Assuming stripe-sdk is linked to multiple projects)

# Project A
search(query="webhook handler", scope="local", top_k=5)
# Returns customer-a's webhook implementation

# Project B
search(query="webhook handler", scope="local", top_k=5)
# Returns customer-b's webhook implementation

# Compare with SDK patterns
search(query="webhook handler", scope="shared:stripe-sdk", top_k=5)
# Returns Stripe's recommended webhook patterns
```

## Configuration

### Project Configuration File

`.mimir/config.json`:
```json
{
  "docs_dir": "docs",
  "code_dirs": ["src", "tests"],
  "shared_indices": ["stripe-sdk", "fastapi"]
}
```

### Shared Index Storage

Shared indices are stored in:
```
~/.mimir/shared/
  ├── stripe-sdk/
  │   ├── index.faiss
  │   └── metadata.json
  ├── fastapi/
  │   ├── index.faiss
  │   └── metadata.json
  └── ...
```

## Notes

- Shared indices are stored globally in `~/.mimir/shared/`
- Update shared indices when SDKs release new versions
- Use `scope="local"` when you only want customer-specific code
- Use `scope="shared:<name>"` when learning SDK patterns
- Shared indices are read-only — they don't include project-specific code
- Consider creating shared indices for: Stripe, Twilio, Auth0, AWS SDK, etc.
- CLI reference: `python mimir-projects.py shared --help`
- Shared indices are automatically included in `scope="all"` searches
- Use descriptive names: `<framework>-<version>` or `<sdk>-docs`
