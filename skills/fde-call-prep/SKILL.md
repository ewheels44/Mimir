---
name: fde-call-prep
description: Prepare for a customer call on a specific topic. Uses Mimir's search (top_k=8) and query tools to generate a briefing with relevant code sections, known patterns, questions to ask, common pitfalls, proposed approach, and things to verify.
---

# FDE Call Preparation

Generate a focused briefing before customer calls to ensure productive conversations and demonstrate expertise.

## When to use

- **Before any customer call** — technical discussions, troubleshooting, planning
- **When the customer has a specific question or issue** — prepare informed responses
- **Architecture review meetings** — understand current state before proposing changes
- **Troubleshooting sessions** — research the problem space beforehand

## When NOT to use

- Non-technical calls (billing, administrative)
- You've already prepared for this exact topic with this customer
- The topic is completely outside the indexed codebase

## Tools

### search

Find specific code sections relevant to the call topic.

```
search(query="rate limiting implementation", top_k=8)
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `query` | yes | — | Natural language search query |
| `top_k` | no | `5` | Use `8` for call prep (broader coverage) |

### query

Get synthesized understanding of patterns and concepts.

```
query(question="How does the authentication flow work?")
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `question` | yes | — | Natural language question |

## Workflow

```
Call topic received
         │
         ▼
Identify key search queries
    ├── Main topic query
    ├── Related patterns
    └── Potential edge cases
         │
         ▼
Execute searches (top_k=8)
    ├── search("main topic")
    ├── search("related pattern 1")
    └── search("related pattern 2")
         │
         ▼
Query for synthesized understanding
    └── query("How does X work?")
         │
         ▼
Generate call briefing
    ├── Relevant code sections
    ├── Known patterns
    ├── Questions to ask
    ├── Common pitfalls
    ├── Proposed approach
    └── Things to verify
         │
         ▼
Review briefing before call
```

## Output Format

The call briefing should include:

### 1. Relevant Code Sections
- Key files and functions
- Important configuration
- Entry points for the topic

### 2. Known Patterns
- How things are currently done
- Established conventions
- Similar implementations

### 3. Questions to Ask
- Clarifications needed
- Requirements to confirm
- Constraints to understand

### 4. Common Pitfalls
- Known issues in this area
- Edge cases to watch for
- Dependencies that might break

### 5. Proposed Approach
- Initial recommendation
- Implementation outline
- Alternatives to consider

### 6. Things to Verify
- Assumptions to check
- Configurations to confirm
- Dependencies to validate

## Example

### Example: Preparing for rate limiting discussion

```
# Step 1: Identify queries
# Topic: "Add rate limiting to API endpoints"
# Related: authentication middleware, existing middleware stack, config

# Step 2: Execute searches
search(query="rate limiting", top_k=8)
# Result: No existing rate limiting found

search(query="middleware stack", top_k=8)
# Result: Starlette middleware in src/middleware/, auth middleware pattern

search(query="API configuration", top_k=8)
# Result: Settings in config.py, environment-based config

# Step 3: Query for understanding
query(question="How is middleware currently structured?")
# Result: Middleware added in main.py, follows Starlette pattern, auth middleware is good reference

# Step 4: Generate briefing
```

**Generated Briefing:**
```
## Topic: Add Rate Limiting to API Endpoints

## Relevant Code Sections
- src/main.py — Middleware registration (lines 45-60)
- src/middleware/auth.py — Auth middleware pattern (reference implementation)
- config.py — API settings and configuration

## Known Patterns
- Middleware follows Starlette pattern: class with __call__ method
- Auth middleware is good reference: handles request/response, adds user context
- Configuration via environment variables, validated in config.py

## Questions to Ask
1. What rate limits do you need? (requests per minute/hour)
2. Should limits be per-user, per-IP, or per-API-key?
3. Do you need different limits for different endpoints?
4. What should happen when limit is exceeded? (429, custom response?)
5. Do you need rate limit headers in responses? (X-RateLimit-*)

## Common Pitfalls
- Forgetting to handle the case when Redis is unavailable
- Not accounting for WebSocket connections (if applicable)
- Rate limiting authenticated vs unauthenticated requests differently
- Memory leaks in in-memory rate limiters under load

## Proposed Approach
1. Create RateLimitMiddleware following auth middleware pattern
2. Use Redis for distributed rate limiting (already in stack)
3. Configure limits via environment variables
4. Return 429 with Retry-After header on limit exceeded
5. Add X-RateLimit headers to responses

Alternatives:
- Use slowapi library (FastAPI/Starlette rate limiting)
- In-memory rate limiting for single-instance deployments

## Things to Verify
- Is Redis available and configured? (check config.py)
- Are there any existing rate limiting attempts in the codebase?
- What's the deployment model? (single instance vs distributed)
- Any existing API documentation to update?
```

## Notes

- Always use `top_k=8` for call prep to get comprehensive coverage
- Generate at least 5 questions — better to over-prepare
- Include "Things to Verify" section for live checking during the call
- Save the briefing in your notes for reference during the call
- If time permits, search for "edge cases" or "error handling" related to the topic
- Common pitfalls often come from searching for "error" or "exception" + topic
