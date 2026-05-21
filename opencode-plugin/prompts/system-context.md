# System Context

This context is injected at the start of every session.

## Session Info
- **Date**: {{date}}
- **Git Branch**: {{git_branch}}
- **Working Directory**: {{cwd}}
- **Platform**: {{platform}}

## Instructions
<!-- Edit below this line to customize what gets injected -->

MUST SAY **Mimir Loaded**

Read ~/Documents/Mimir/docs/mimir-sys-prompt.txt

## Tool Priority

When exploring code, answering questions about SDKs, or onboarding to libraries, use these tools in order:

### For SDK/Library Questions
1. `sdk_cache_get(library, topic)` — Get current API docs (cached, fast)
2. `mimir-knowledge_search(query)` — Find existing usage in the codebase

### For Project Questions
1. `mimir-knowledge_enrich_task(task)` — Get project-specific context before executing
2. `mimir-knowledge_search(query)` — Semantic search across indexed docs and code
3. `mimir-knowledge_query(question)` — Synthesized answers from knowledge base

### For Complex Analysis
1. `mimir-knowledge_rag_workflow(query)` — Structured retrieve → generate
2. `mimir-knowledge_knowledge_agent(question)` — Agentic multi-step exploration

### Skills to Load
- `unified-query` — Single entry point that searches all layers automatically
- `sdk-onboarding` — Guide for onboarding to any SDK
- `mimir-knowledge` — Search project knowledge base before executing tasks
- `find-and-follow-pattern` — "How do I add a new X?" pattern discovery
