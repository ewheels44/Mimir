---
name: fde-handoff
description: Generate handoff documentation for transferring FDE work to a permanent team. Uses Mimir's query and search tools to generate comprehensive handoff documentation. References the CLI: `python mimir-projects.py handoff`.
---

# FDE Handoff Documentation

Generate comprehensive handoff documentation when transferring FDE work to a permanent engineering team.

## When to use

- **Ending an FDE engagement** — formal handoff to permanent team
- **Transitioning between FDEs** — another FDE taking over
- **Project completion** — document what was built and why
- **Before going on leave** — ensure continuity

## When NOT to use

- Mid-engagement with no transition planned
- When the customer explicitly doesn't want documentation
- For internal FDE notes (use personal notes instead)

## Tools

### query

Get synthesized understanding of the overall project state.

```
query(question="What is the architecture of this project?")
query(question="What were the main changes made during this engagement?")
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `question` | yes | — | Natural language question |

### search

Find specific implementations, configurations, and patterns.

```
search(query="authentication", top_k=10)
search(query="configuration", top_k=10)
search(query="deployment", top_k=10)
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `query` | yes | — | Natural language search query |
| `top_k` | no | `5` | Use `10` for handoff (comprehensive) |

## CLI Reference

The handoff can also be generated via CLI:

```bash
python mimir-projects.py handoff <project-name>
```

This command:
- Searches the project's indexed knowledge base
- Generates a structured handoff document
- Outputs to stdout or specified file

## Workflow

```
Handoff requested
         │
         ▼
Gather project context
    ├── query("What is the architecture?")
    ├── query("What were the main changes?")
    └── query("What are the key integration points?")
         │
         ▼
Search for specific areas
    ├── search("authentication", top_k=10)
    ├── search("database", top_k=10)
    ├── search("API endpoints", top_k=10)
    ├── search("configuration", top_k=10)
    ├── search("deployment", top_k=10)
    └── search("testing", top_k=10)
         │
         ▼
Generate handoff document
    ├── Project overview
    ├── Architecture summary
    ├── Key files and modules
    ├── Recent changes
    ├── Open issues
    ├── Configuration guide
    ├── Deployment guide
    └── Contact information
         │
         ▼
Review and deliver
```

## Output Format

The handoff document should include:

### 1. Project Overview
- Business context
- Project goals
- Current status

### 2. Architecture Summary
- High-level design
- Key components
- Data flow

### 3. Key Files and Modules
- Entry points
- Core business logic
- Configuration files
- Test files

### 4. Recent Changes
- What was built/modified
- Why decisions were made
- Known limitations

### 5. Open Issues
- Known bugs
- Technical debt
- Future work

### 6. Configuration Guide
- Environment variables
- Required services
- Local setup steps

### 7. Deployment Guide
- Deployment process
- CI/CD pipeline
- Monitoring/alerting

### 8. Contact Information
- FDE contact
- Customer contacts
- Relevant Slack channels

## Example

### Example: Handoff for e-commerce platform

**Generated Handoff Document:**
```
# Handoff Document: E-Commerce Platform

**Project:** CustomerName E-Commerce Platform
**FDE:** [Your Name]
**Handoff Date:** 2026-04-07
**Receiving Team:** CustomerName Platform Team

---

## Project Overview

### Business Context
CustomerName is a B2B e-commerce platform serving wholesale buyers. The platform manages product catalogs, pricing tiers, and order processing for 500+ business customers.

### Project Goals
- Reduce API response times from 800ms to <200ms
- Implement proper authentication and authorization
- Add rate limiting for API protection
- Improve test coverage from 40% to 80%

### Current Status
- ✅ Caching implemented (avg response: 150ms)
- ✅ JWT authentication with OAuth2 providers
- ✅ Rate limiting deployed
- 🔄 Test coverage at 65% (in progress)
- ❌ CI/CD pipeline not yet configured

---

## Architecture Summary

### High-Level Design
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│  FastAPI    │────▶│ PostgreSQL  │
│   (React)   │     │   Backend   │     │   Primary   │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    │    Redis    │
                    │   (Cache)   │
                    └─────────────┘
```

### Key Components
- **FastAPI Backend** — Python 3.11, async REST API
- **PostgreSQL** — Primary data store, SQLAlchemy ORM
- **Redis** — Session storage, caching layer
- **OAuth2** — Google, GitHub authentication

### Data Flow
1. Request → Rate Limiter → Auth Middleware → Router
2. Router → Cache Check → Database (if miss) → Response
3. Cache invalidation on write operations

---

## Key Files and Modules

### Entry Points
| File | Purpose |
|------|---------|
| `src/main.py` | Application entry, middleware registration |
| `src/api/v1/__init__.py` | API router registration |

### Core Business Logic
| File | Purpose |
|------|---------|
| `src/services/product.py` | Product catalog service |
| `src/services/order.py` | Order processing service |
| `src/services/cache.py` | Redis caching layer |
| `src/auth/middleware.py` | JWT authentication |
| `src/auth/oauth.py` | OAuth2 provider integration |

### Configuration
| File | Purpose |
|------|---------|
| `config.py` | Environment-based configuration |
| `alembic.ini` | Database migration config |
| `docker-compose.yml` | Local development setup |

### Tests
| File | Purpose |
|------|---------|
| `tests/unit/` | Unit tests (65% coverage) |
| `tests/integration/` | Integration tests |
| `tests/conftest.py` | Test fixtures and setup |

---

## Recent Changes

### Caching Implementation (2026-04-01 to 2026-04-05)
- Added `src/services/cache.py` with cache-aside pattern
- Implemented caching for product catalog endpoints
- Added cache invalidation on product updates
- **Decision**: Cache-aside chosen for incremental rollout
- **Limitation**: Search results not yet cached

### Authentication Overhaul (2026-03-15 to 2026-03-25)
- Replaced basic auth with JWT tokens
- Added OAuth2 integration (Google, GitHub)
- Implemented role-based access control
- **Decision**: JWT chosen for stateless auth
- **Limitation**: Token revocation not implemented

### Rate Limiting (2026-03-28 to 2026-04-02)
- Added `src/middleware/rate_limit.py`
- Configured per-user and per-IP limits
- Added X-RateLimit headers to responses
- **Decision**: Redis-backed for distributed support

---

## Open Issues

### Known Bugs
1. **[P1]** WebSocket connections not rate-limited
2. **[P2]** Cache stampede on cold starts
3. **[P3]** Intermittent OAuth2 state validation errors

### Technical Debt
1. Missing integration tests for order flow
2. No API versioning strategy
3. Hardcoded rate limit values (should be configurable)

### Future Work
1. Implement token revocation for auth
2. Add caching for search results
3. Set up CI/CD pipeline
4. Increase test coverage to 80%

---

## Configuration Guide

### Required Environment Variables
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Redis
REDIS_URL=redis://localhost:6379/0

# Auth
JWT_SECRET=your-secret-key
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx
GITHUB_CLIENT_ID=xxx
GITHUB_CLIENT_SECRET=xxx

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=60
```

### Local Setup
```bash
# 1. Clone and install dependencies
git clone <repo>
cd <project>
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Start services
docker-compose up -d

# 3. Run migrations
alembic upgrade head

# 4. Start server
uvicorn src.main:app --reload
```

---

## Deployment Guide

### Current Deployment
- Deployed to AWS ECS
- Single container, auto-scaling enabled
- PostgreSQL on RDS, Redis on ElastiCache

### Deployment Process
```bash
# 1. Build and push image
docker build -t customername-api:latest .
docker push <ecr-repo>/customername-api:latest

# 2. Update ECS task definition
aws ecs update-service --cluster prod --service api --force-new-deployment
```

### Monitoring
- CloudWatch for logs and metrics
- PagerDuty for alerts
- No APM currently configured (recommend DataDog)

---

## Contact Information

### FDE Contact
- **Name:** [Your Name]
- **Email:** [your-email@company.com]
- **Slack:** #fde-customername

### Customer Contacts
- **Engineering Lead:** [Name] - [email]
- **Product Owner:** [Name] - [email]
- **DevOps:** [Name] - [email]

### Relevant Channels
- #customername-eng (internal)
- #customername-support (customer Slack)

---

## Appendix

### Key Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-15 | JWT over sessions | Stateless, scalable |
| 2026-03-28 | Redis rate limiting | Distributed support |
| 2026-04-01 | Cache-aside pattern | Incremental rollout |

### Related Documents
- [Technical Writeup: Caching Implementation](link)
- [Technical Writeup: Authentication](link)
- [Call Notes: 2026-03-20 Architecture Review](link)
```

## Notes

- Use `top_k=10` for handoff searches to be comprehensive
- Include specific file paths and line numbers where possible
- Document decisions and rationale — this is often more valuable than code
- Be honest about open issues and technical debt
- Include contact information for follow-up questions
- Save handoff documents in a shared location accessible to the receiving team
- Consider scheduling a handoff call to walk through the document
- CLI command: `python mimir-projects.py handoff <project-name>` for automated generation
