---
name: find-and-follow-pattern
description: When adding new code, find how the project already does it and follow the same pattern. This is the most common onboarding task — "how do I add a new X?" where X is an endpoint, component, test, etc.
---

# Find and Follow Pattern

The fastest way to write correct code: find how the project already does it, then copy the pattern.

## When to use

- "How do I add a new API endpoint?"
- "How do I add a new React component?"
- "How do I write a test for this?"
- "What's the pattern for database queries?"
- Any "how do I add a new X?" question

## Workflow

### Step 1: Identify what you're adding

Classify the task:
- **API endpoint** → search for existing route handlers
- **UI component** → search for existing components
- **Database query** → search for existing queries
- **Test** → search for existing tests
- **Configuration** → search for existing config files

### Step 2: Find existing examples

```
mimir-knowledge_search(query="<what you're adding> example pattern")
```

Look for 2-3 examples of the same type of code. More examples = more confidence in the pattern.

### Step 3: Identify the pattern

From the examples, extract:
- **File naming**: `kebab-case.ts`? `PascalCase.tsx`?
- **Directory structure**: Where do these files live?
- **Imports**: What libraries/utilities are used?
- **Structure**: What's the boilerplate?
- **Error handling**: How are errors handled?
- **Types**: What type patterns are used?

### Step 4: Apply the pattern

Write your new code following the exact same pattern. Don't improvise — consistency is more important than perfection.

### Step 5: Verify

Check that your code:
- Uses the same naming conventions
- Follows the same file structure
- Handles errors the same way
- Uses the same imports/utilities
- Matches the same type patterns

## Example

```
Q: "How do I add a new API endpoint for user preferences?"

Step 1: This is an API endpoint task
Step 2: Mimir finds:
  - src/routes/api/users.ts (GET /users)
  - src/routes/api/users/[id].ts (GET /users/:id)
  - src/routes/api/settings.ts (PUT /settings)

Step 3: Pattern identified:
  - Files: src/routes/api/<resource>.ts
  - Framework: Next.js API routes
  - Validation: Zod schemas
  - Error handling: try/catch with typed errors
  - Response: { data: T } | { error: string }

Step 4: Create src/routes/api/preferences.ts following the pattern
Step 5: Verify it matches the existing endpoints
```

## Why this works

- **No guessing**: You're following proven patterns
- **Consistency**: Your code matches the codebase
- **Speed**: No need to research "best practices" — just copy what works
- **Quality**: Existing code has been reviewed and tested

## Notes

- If you find conflicting patterns, ask which is preferred
- If no existing examples exist, you're creating a new pattern — document it
- The system learns from your implementations and creates skills automatically
