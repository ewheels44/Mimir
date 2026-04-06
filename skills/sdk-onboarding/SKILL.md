---
name: sdk-onboarding
description: Guide for onboarding developers to any SDK or library. Combines live API docs, project-specific patterns, and evolved skills into a single onboarding flow. Use this when a developer asks "how do I use X in this project?"
---

# SDK Onboarding

Unified onboarding flow for any SDK or library. Combines three knowledge sources into one answer.

## When to use

- Developer asks "How do I use [library] in this project?"
- New team member needs to learn a project's SDK integration patterns
- Adding a new library to the project
- Debugging SDK integration issues

## When NOT to use

- Generic "what is this library?" questions (use docs directly)
- You already know the exact answer from memory
- The question is about project-internal code, not external SDKs

## Workflow

### Step 1: Check for existing project usage

Search the project knowledge base for how this SDK is already used:

```
mimir-knowledge_enrich_task(task="How is <library> used in this project?")
```

**If results found**: The project already uses this SDK. Show the existing patterns.
**If no results**: This is a new SDK integration. Proceed to Step 2.

### Step 2: Get current SDK documentation

Fetch live docs from the SDK cache (or Context7 API):

```
mimir-knowledge_sdk_cache_get(library="<library>", topic="<specific feature>")
```

**If docs found**: You have current API reference. Combine with project patterns.
**If docs not found**: Fall back to general knowledge, note that docs may be outdated.

### Step 3: Check for evolved skills

Search OpenSpace for any skills related to this SDK:

```
openspace_search_skills(query="<library> integration", source="local")
```

**If skill found**: Use the proven pattern from the skill.
**If no skill**: This is a new integration. Create a pattern from Steps 1+2.

### Step 4: Synthesize answer

Combine all sources into a clear, actionable answer:

```
## How to use <library> in this project

### Existing usage
[From Mimir: how the project already uses this SDK]

### API reference
[From SDK cache: current method signatures and parameters]

### Recommended pattern
[Synthesized: project conventions + SDK best practices]

### Example
[Code example matching project style]
```

### Step 5: After implementation

If the developer implements the integration:
1. OpenSpace will capture the pattern as a new skill automatically
2. The next developer asking the same question gets a faster, better answer

## Example

```
Q: "How do I add Stripe checkout to the billing page?"

Step 1: Mimir finds src/payments/stripe.ts with existing Stripe usage
Step 2: SDK cache returns Stripe checkout session API docs
Step 3: No evolved skill yet (first time)
Step 4: Synthesize:
  "This project uses Stripe v14 with the following pattern:
   [existing code from Mimir]
   To add checkout, use createCheckoutSession:
   [API reference from cache]
   Follow the project's error handling pattern:
   [error handling from Mimir]"
```

## Notes

- This skill is a starting point — it will be replaced by evolved skills as the system learns
- SDK cache TTL is 7 days — docs are always reasonably current
- Mimir index updates automatically via git hooks — project patterns are always fresh
