How I Built a Memory System for AI Assistants
Stop wasting 30% of every session rediscovering what you already know.

---

The Problem 
Every developer knows this feeling:
Session 1: You either spend way too much time thinking about how to describe your problem set and the elements you might need to mention in order for an update or new feature to make sense, or you don't spend any time on this at all and the AI spends all your tokens and context on re-discovering a code base you have been working on for weeks. 
It doesn't stop there!
Session 2: "Hey, update the auth flow to support OAuth."
Assistant: "I don't see any auth files. Let me search…"
…10 minutes of re-exploration…
Session 3, 4, 5: The same dance. Every. Single. Time.
Your AI assistant has no memory between sessions. And even within a session, it struggles to find the right context amid thousands of files.
Sound familiar? 

---

What If Your AI Actually Remembered?
That's exactly what Mimir does.
Mimir is a knowledge base system that gives your AI assistant permanent, semantic memory across all your projects. You install it once, and it automatically indexes your documentation and code—then serves that context to any AI tool you use.
The result? Your AI stops asking "which auth file?" and starts asking "which OAuth provider do you prefer?"

---

How It Works (In Plain English)

1. Install Once, Use Everywhere
One global install sets up the MCP server and injects memory rules into your AI tool. No environment variables, no config headaches.

2. Index Your Projects
Run one command to index any project's documentation and code:
python .opencode/mimir-index.py
Mimir creates a semantic search index—a vector database that understands meaning, not just keywords. It auto-detects your project root and loads that project's knowledge base.

3. Ask Questions Naturally
# Instead of: "read auth.py, then middleware.py, then token.py"
# You just ask: "How does authentication work in this codebase?"
Mimir finds the relevant files and synthesizes an answer. Even if you use different words than what's in the code.

---

Why Semantic Search Changes Everything
Here's where it gets cool.
Traditional search: "auth" → finds files with "auth" in the name.
Semantic search: "authentication" → finds:
- auth.py (the auth module)
- middleware.py (token parsing)
- api/client.py (refresh token logic)
- config/auth.go (OAuth settings)

Same concept, different words. 
Traditional grep searches for strings. Mimir searches for meaning.

---

Real Numbers
I tracked token usage and costs across multiple projects:
| Scenario | Without Mimir | With Mimir | Savings |
|----------|---------------|------------|---------|
| First refactor | 25k tokens ($0.75) | 8k + $0.001 ($0.25) | 67% |
| Second refactor | 25k tokens ($0.75) | 5k + $0.001 ($0.16) | 79% |
| Third refactor | 25k tokens ($0.75) | 5k + $0.001 ($0.16) | 79% |

Cumulative savings: 75%+ on token costs
But honestly? The real win isn't money—it's time. I saved 5–10 minutes per session on context rebuilding. That adds up fast when you're doing it dozens of times a week.

---

Getting Started (10 Minutes)

Here's exactly what I did to get it running:

1. Install Mimir
```bash
# Clone or copy to a central location
mkdir -p ~/Documents/Mimir
cd ~/Documents/Mimir

# Global install (once)
python ~/Documents/Mimir/mimir.py install
```

2. Initialize Your Project
```bash
cd ~/Documents/YourProject
python ~/Documents/Mimir/mimir.py init --code-dirs=src,tests
```

This creates:
- `docs/` — Add your documentation here
- `.knowledge/llamaindex/` — Your project's search index
- `.mimir/config.json` — Project configuration
- `.opencode/mimir-index.py` — Indexing script

3. Index and Query
```bash
# Index your docs and code
python ~/Documents/Mimir/mimir.py index

# Ask questions
python ~/Documents/Mimir/mimir.py search "How does auth work?"

# Or use RAG for complex analysis
python ~/Documents/Mimir/mimir.py rag "Explain the authentication flow"
```

That's it. Your project is now searchable by meaning.

**After install, you don't touch the CLI again.** Your AI agent follows Mimir rules automatically—searching the knowledge base before every task.

---

Built for AI Agents (Not Just CLI)

Here's what makes Mimir different: **it's designed for AI agents, not humans**.

The CLI is great for manual queries, but the real power is automatic. When you use OpenCode, Mimir injects rules that tell your AI agent: "Before you do anything, search the knowledge base first."

```
You: "Update the auth flow to support OAuth"
Agent: [Calls mimir-knowledge_enrich_task("update auth flow oauth")]
       → Finds auth.py, middleware.py, OAuth config
       → Already knows the codebase structure
       → Skips re-discovering and starts implementing
```

**What agents get automatically:**
- `enrich_task()` — Project context before every task (Rule 1 in their system prompt)
- `search()` — Semantic search for finding files by meaning
- `query()` — Synthesized answers from the knowledge base
- `graph_query()` — Structural paths ("how does X reach Y?")
- `sdk_cache_get()` — Fresh API docs without hallucinations
- `openspace_health()` — Checks if the bridge is working

**No prompts needed.** The install script injects Mimir rules into OpenCode's system context. Agents follow the rules automatically.

---

What Mimir Indexes

By default, Mimir indexes your `docs/` directory. But you can also index source code:

```bash
python ~/Documents/Mimir/mimir.py init --code-dirs=src,tests,lib
```

Now you can ask questions like:
- "Where is the user authentication logic?"
- "Find all files that call the payment API"
- "What does the Config class do?"

Game changer for understanding unfamiliar codebases.

---

The Architecture (For the Curious)

Mimir uses MCP (Model Context Protocol) to integrate with AI tools like OpenCode:

```
┌─────────────────────────────────────────────────────────┐
│  OpenCode (or any MCP-compatible AI tool)               │
│         ↓ "Before any task, call enrich_task()"          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  MCP Server (proxies tools to Mimir)                 │ │
│  │  search, query, rag, graph_*, sdk_cache, health     │ │
│  └─────────────────────────────────────────────────────┘ │
│         ↓                                                │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  LlamaIndex (semantic search, embeddings)           │ │
│  └─────────────────────────────────────────────────────┘ │
│         ↓                                                │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  Per-project Vector Store (.knowledge/llamaindex/) │ │
│  └─────────────────────────────────────────────────────┘ │
```

Key design decisions:
- **Agents use it automatically** — Rules injected into AI tool's system prompt
- **Central server, per-project storage** — One install serves unlimited projects
- **Auto-detects project root** — Uses `.git/`, `.mimir/`, `package.json` as markers
- **OpenRouter support** — No OpenAI API key required
- **OpenSpace bridge** — Circuit breaker, caching, content filtering for reliable tool calls

---

New: Knowledge Graph Query

Here's what I didn't have in the first version: structural understanding.

Mimir now extracts code relationships (imports, calls, inheritance) into a queryable knowledge graph with weighted Dijkstra path-finding.

```
Semantic search: "What does auth do?" → finds files about auth
Graph query: "How does auth reach the database?" → traces the import/call chain
```

**Edge weights by coupling strength:**

| Relationship | Weight | Meaning |
|-------------|--------|---------|
| calls | 1.0 | Direct function/method call |
| has_method | 1.0 | Class → method |
| inherits_from | 1.5 | Class inheritance |
| imports_from | 2.0 | Specific symbol import |
| imports_module | 3.0 | Whole-module import |

Now your AI can answer: "How does the MCP server reach the SDK cache?" or "What depends on config.py?"

---

New: SDK Documentation Cache

Tired of AI hallucinations about library APIs? Mimir caches SDK documentation locally.

```
Agent needs Stripe docs
    ↓
Check .knowledge/sdk-cache/stripe/
    ↓
Fresh (< 7 days) → Use cached docs (instant)
Stale or missing → Fetch from Context7 API → Cache locally
```

Tools:
- `sdk_cache_get` — Get SDK docs (fetches + caches if stale)
- `sdk_cache_list` — List all cached libraries with freshness info

```bash
# CLI access
python ~/Documents/Mimir/mimir.py cache get stripe --topic "checkout sessions"
```

---

New: FDE Toolkit

Working with multiple customer engagements? Mimir has a complete toolkit for Forward Deployed Engineers.

### Multi-Project Management
```bash
# Register and switch between projects
python ~/Documents/Mimir/mimir.py projects add ~/Projects/customer-a
python ~/Documents/Mimir/mimir.py projects switch customer-a
python ~/Documents/Mimir/mimir.py projects list
```

### Shared Indexes
Reference large SDKs (indexed once globally) alongside customer code:
```bash
# Index a shared SDK (once, globally)
python ~/Documents/Mimir/mimir.py index --shared-index ~/path/to/sdk/ --name acme-sdk

# Search with scope
search(query="voice pipeline", scope="all")           # Everything
search(query="voice pipeline", scope="local")        # Customer code only
search(query="voice pipeline", scope="shared:acme") # SDK only
```

### Customer Call Prep
```bash
# Generate briefing before a customer call
python ~/Documents/Mimir/mimir.py prep "video latency issues"
```

Includes relevant code sections, known patterns, questions to ask, common pitfalls, proposed approach, and things to verify.

### Session Diff
```bash
# What happened in the last day?
python ~/Documents/Mimir/mimir.py diff

# Last 3 days
python ~/Documents/Mimir/mimir.py diff --days 3
```

### Handoff Documentation
```bash
# Generate handoff when transferring to permanent team
python ~/Documents/Mimir/mimir.py handoff --project customer-a \
  --summary "Built video calling integration using WebRTC" \
  --customer "Acme Corp"
```

---

New: Auto-Indexing

Mimir keeps your knowledge base current automatically via git hooks:

```bash
# Install in current project
bash ~/Documents/Mimir/scripts/install-git-hooks.sh

# Install in all Mimir projects
bash ~/Documents/Mimir/scripts/install-git-hooks.sh --all
```

After installation, every `git commit` triggers a background incremental reindex. Only files whose content actually changed are reindexed.

---

New: Skills System

Mimir includes seed skills that give agents immediate knowledge for common tasks:

| Skill | Purpose |
|-------|---------|
| `unified-query` | Searches OpenSpace skills, SDK cache, and Mimir automatically |
| `sdk-onboarding` | Guide for onboarding developers to any SDK |
| `codebase-analysis-workflow` | Systematic codebase analysis in 5 steps |
| `fde-call-prep` | Pre-call briefing with relevant code and questions |

The `unified-query` skill automatically hits all knowledge layers:
```
Your question
    ↓
Layer 1: OpenSpace Skills — "Do I already know the answer?"
    ↓
Layer 2: SDK Doc Cache — "Do I have fresh docs for this?"
    ↓
Layer 3: Mimir Knowledge — "What does the project codebase say?"
    ↓
Layer 4: Synthesize — Combined answer with source attribution
```

**Subagents work too.** ContextScout, CoderAgent, and TaskManager have Mimir tools built-in. Spawn them and they can search the knowledge base without extra configuration:

```typescript
// Just tell them to use it — tools are pre-loaded
task(subagent_type="ContextScout", prompt="Analyze auth patterns")
// → Agent calls mimir-knowledge_search automatically
```

---

When Mimir Shines

✅ Large codebases — Find anything in seconds, not minutes
✅ Cross-cutting changes — See how features touch multiple systems
✅ Team onboarding — New devs get instant context
✅ Maintenance work — "How does X work again?" queries
✅ Multi-project knowledge — Share patterns across projects
✅ FDE engagements — Customer onboarding, call prep, handoff
✅ External APIs — Cached SDK docs prevent hallucinations

---

The Bottom Line

Every session, you're paying twice: once in tokens, once in time. Mimir eliminates the context tax.

**Install once. Index your knowledge. Your AI agent uses it automatically.**

No prompts. No "read the README first." Your AI assistant becomes genuinely helpful because it actually knows your codebase—and uses that knowledge before every task.

---

Mimir: Knowledge that follows you, not the other way around.
Repository: github.com/ewheels44/Mimir

---

Mimir: Knowledge that follows you, not the other way around.
Repository: github.com/ewheels44/Mimir
