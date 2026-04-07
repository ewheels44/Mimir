---
name: fde-customer-onboarding
description: Fast onboarding to a customer's codebase. Uses Mimir's openspace_health, search, and query tools to generate a structured onboarding brief covering tech stack, architecture, key files, integration points, and questions for the customer.
---

# FDE Customer Onboarding

Quickly onboard to a customer's codebase by leveraging Mimir's knowledge base to generate a comprehensive onboarding brief.

## When to use

- **Starting a new FDE engagement** — first interaction with a customer's codebase
- **Taking over from another FDE** — need to understand the current state quickly
- **Before a kickoff call** — prepare informed questions and talking points
- **When the customer shares a new repo** — rapid context gathering

## When NOT to use

- You've already onboarded to this customer's codebase
- The customer has no indexed codebase (check `openspace_health` first)
- You only need to understand a single, specific file

## Tools

### openspace_health

Check if Mimir is available and has an index for this customer.

```
openspace_health()
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| — | — | — | No parameters |

**Response:**
```json
{
  "enabled": true,
  "circuit_open": false,
  "has_index": true,
  "index_timestamp": "2026-04-05T10:30:00"
}
```

### search

Semantic search across the customer's indexed codebase and docs.

```
search(query="authentication flow", top_k=10)
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `query` | yes | — | Natural language search query |
| `top_k` | no | `5` | Number of results to return |

### query

Ask a synthesized question about the codebase.

```
query(question="What is the overall architecture of this project?")
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `question` | yes | — | Natural language question |

## Workflow

```
Customer codebase received
         │
         ▼
Call openspace_health()
         │
         ├── no index → Request customer to index codebase
         │              or proceed with manual exploration
         │
         ▼
Broad discovery queries
    ├── query("What is the tech stack?")
    ├── query("What is the architecture?")
    └── search("main entry point", top_k=5)
         │
         ▼
Deep dive into key areas
    ├── search("authentication", top_k=8)
    ├── search("database models", top_k=8)
    ├── search("API endpoints", top_k=8)
    └── search("configuration", top_k=5)
         │
         ▼
Generate onboarding brief
    ├── Tech stack summary
    ├── Architecture overview
    ├── Key files list
    ├── Integration points
    └── Questions for customer
         │
         ▼
Present brief to FDE
```

## Output Format

The onboarding brief should include:

### 1. Tech Stack Summary
- Languages and frameworks
- Key dependencies
- Build tools and package managers

### 2. Architecture Overview
- High-level structure
- Key modules/components
- Data flow patterns

### 3. Key Files
- Entry points
- Configuration files
- Core business logic

### 4. Integration Points
- External APIs/services
- Database connections
- Authentication providers

### 5. Questions for Customer
- Clarifications needed
- Potential concerns
- Areas requiring documentation

## Example

### Example: Onboarding to a SaaS platform

```
# Step 1: Health check
openspace_health()
# Result: has_index: true, index_timestamp: 2026-04-05

# Step 2: Broad discovery
query(question="What is the tech stack?")
# Result: Python 3.11, FastAPI, PostgreSQL, Redis, Docker

query(question="What is the architecture?")
# Result: Monolithic FastAPI app with async workers, REST API + WebSocket

# Step 3: Deep dive
search(query="authentication", top_k=8)
# Result: JWT-based auth, OAuth2 integration, middleware in src/auth/

search(query="database models", top_k=8)
# Result: SQLAlchemy ORM, 15 models, migrations via Alembic

search(query="API endpoints", top_k=8)
# Result: 42 endpoints, versioned at /api/v1/, OpenAPI docs

# Step 4: Generate brief
```

**Generated Brief:**
```
## Tech Stack
- Python 3.11, FastAPI, SQLAlchemy, Alembic
- PostgreSQL (primary DB), Redis (caching/sessions)
- Docker, docker-compose for local dev

## Architecture
- Monolithic FastAPI application
- Async background workers for email/notifications
- REST API + WebSocket for real-time features
- JWT authentication with OAuth2 (Google, GitHub)

## Key Files
- src/main.py — Application entry point
- src/auth/middleware.py — Auth middleware
- src/models/ — SQLAlchemy models
- alembic/ — Database migrations
- docker-compose.yml — Local dev setup

## Integration Points
- PostgreSQL: Primary data store
- Redis: Session storage, caching
- OAuth2: Google, GitHub providers
- SMTP: Transactional emails

## Questions for Customer
1. What's the deployment target? (K8s, ECS, etc.)
2. Are there any undocumented integrations?
3. What's the current test coverage?
4. Any known technical debt or pain points?
```

## Notes

- Use `top_k=8-10` for discovery searches to get comprehensive coverage
- Combine `search` (find specific code) with `query` (understand concepts)
- If `openspace_health` shows `stale` index, note this in the brief
- Always generate questions — they show the customer you've done your homework
- Save the brief for future reference and handoffs
