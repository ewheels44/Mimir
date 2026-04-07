---
name: fde-technical-writeup
description: Generate post-call technical writeups. Takes call notes, searches relevant code, and generates customer-facing documentation with summary, problem statement, approach, implementation details, tradeoffs, and next steps.
---

# FDE Technical Writeup

Generate professional technical documentation after customer calls to capture decisions, approaches, and action items.

## When to use

- **After any technical customer call** — document what was discussed and decided
- **When the customer needs a written summary** — formal documentation of proposed solutions
- **Before implementation** — get customer sign-off on the approach
- **For complex discussions** — ensure nothing is lost or misunderstood

## When NOT to use

- Non-technical calls (billing, scheduling)
- Simple Q&A sessions with no decisions made
- When the customer explicitly doesn't want documentation

## Tools

### search

Find code sections referenced in call notes.

```
search(query="authentication middleware", top_k=8)
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `query` | yes | — | Natural language search query |
| `top_k` | no | `5` | Use `8` for comprehensive coverage |

### query

Understand patterns and architecture mentioned in call.

```
query(question="How does the current caching layer work?")
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `question` | yes | — | Natural language question |

## Workflow

```
Call notes received
         │
         ▼
Extract key topics from notes
    ├── Problems discussed
    ├── Solutions proposed
    └── Decisions made
         │
         ▼
Search for relevant code
    ├── search("topic 1", top_k=8)
    ├── search("topic 2", top_k=8)
    └── query("architecture question")
         │
         ▼
Generate technical writeup
    ├── Summary
    ├── Problem statement
    ├── Approach
    ├── Implementation details
    ├── Tradeoffs
    └── Next steps
         │
         ▼
Review and deliver to customer
```

## Output Format

The technical writeup should include:

### 1. Summary
- 2-3 sentence overview of what was discussed
- Key outcome or decision

### 2. Problem Statement
- Clear description of the issue
- Business impact
- Constraints and requirements

### 3. Approach
- High-level solution design
- Why this approach was chosen
- Key components

### 4. Implementation Details
- Specific files/modules affected
- Code patterns to follow
- Configuration changes needed

### 5. Tradeoffs
- Alternatives considered
- Why they were rejected
- Risks and mitigations

### 6. Next Steps
- Action items with owners
- Dependencies
- Timeline estimates

## Example

### Example: Post-call writeup for caching implementation

**Call Notes (Input):**
```
Customer wants to add caching to reduce API response times.
Current avg response: 800ms, target: <200ms.
Discussed Redis caching for product catalog endpoints.
Customer has Redis available (used for sessions).
Decided on: Cache-aside pattern, 5-minute TTL, cache invalidation on product updates.
Next: FDE to implement POC, customer to provide test data.
```

**Generated Writeup:**
```
# Technical Writeup: Product Catalog Caching Implementation

**Date:** 2026-04-07
**Attendees:** [Customer Team], [FDE]
**Topic:** API Response Time Optimization via Caching

---

## Summary

Discussed implementing Redis caching for the product catalog API to reduce average response times from 800ms to under 200ms. Decided on a cache-aside pattern with 5-minute TTL and automatic invalidation on product updates.

## Problem Statement

The product catalog API endpoints (`/api/v1/products/*`) currently average 800ms response time, causing poor user experience in the frontend application. The target is sub-200ms response times for read-heavy operations.

**Business Impact:**
- Slow page loads affecting conversion rates
- Poor mobile user experience
- Increased infrastructure costs from redundant queries

**Constraints:**
- Must maintain data consistency
- Cannot exceed existing Redis instance capacity
- Must work with existing authentication/authorization

## Approach

Implement a **cache-aside pattern** using the existing Redis infrastructure:

1. Check cache before database query
2. On cache miss, query database and populate cache
3. Invalidate cache on product updates
4. Use 5-minute TTL as safety net

**Why cache-aside:**
- Customer already has Redis (used for sessions)
- Gives application full control over cache population
- Easy to implement incrementally per endpoint

**Key Components:**
- Cache service layer in `src/services/cache.py`
- Decorator pattern for caching endpoints
- Cache invalidation hooks in product update handlers

## Implementation Details

### Files to Modify/Create

| File | Changes |
|------|---------|
| `src/services/cache.py` | New file — Redis cache service |
| `src/api/v1/products.py` | Add caching decorators |
| `src/models/product.py` | Add cache invalidation hooks |
| `config.py` | Add cache TTL configuration |
| `docker-compose.yml` | Verify Redis configuration |

### Code Pattern

```python
# src/services/cache.py
class CacheService:
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
    
    async def get_or_set(self, key: str, factory: Callable, ttl: int = 300):
        cached = await self.redis.get(key)
        if cached:
            return json.loads(cached)
        
        value = await factory()
        await self.redis.setex(key, ttl, json.dumps(value))
        return value

# Usage in products.py
@router.get("/products/{product_id}")
@cache_response(ttl=300, key_prefix="product")
async def get_product(product_id: int):
    ...
```

### Configuration

```python
# config.py additions
CACHE_TTL_SECONDS: int = 300  # 5 minutes
CACHE_KEY_PREFIX: str = "catalog"
```

## Tradeoffs

### Alternatives Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Cache-aside (chosen)** | Full control, incremental rollout | Application complexity | ✅ Selected |
| Read-through cache | Simpler app code | Requires cache-aware DB layer | ❌ Too invasive |
| Write-through cache | Always fresh data | Higher write latency | ❌ Not needed |
| CDN caching | Zero app changes | Complex invalidation, not for dynamic data | ❌ Not applicable |

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Stale data | 5-min TTL + invalidation on updates |
| Cache stampede | Add mutex/locking for hot keys |
| Redis unavailable | Graceful degradation to DB |
| Memory pressure | Monitor Redis memory, set maxmemory policy |

## Next Steps

| Action | Owner | Target Date |
|--------|-------|--------------|
| Implement cache service | FDE | 2026-04-10 |
| Add caching to GET /products | FDE | 2026-04-10 |
| Add cache invalidation hooks | FDE | 2026-04-11 |
| Provide test product data | Customer | 2026-04-09 |
| Review POC in staging | Both | 2026-04-12 |
| Production deployment | Customer | TBD |

**Dependencies:**
- Customer to provide representative test data by 2026-04-09
- Redis connection details from customer

**Questions/Open Items:**
- Should we cache product search results?
- What's the expected cache hit ratio?
- Do we need cache warming on deployment?
```

## Notes

- Always search for actual code to reference in implementation details
- Include specific file paths and line numbers when possible
- Tradeoffs section shows the customer you've thought through alternatives
- Next steps should have clear owners and dates
- Keep the writeup customer-friendly — avoid internal jargon
- Save writeups for future reference and handoffs
- Consider adding a "Questions/Open Items" section for unresolved topics
