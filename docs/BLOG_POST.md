# Mimir: Give Your AI Assistant a Memory That Spans Every Project

*Stop wasting 30% of every session rediscovering what you already know.*

---

## The Problem No One Talks About

Every developer knows this feeling:

**Session 1:** You spend 2 hours explaining your codebase's auth system to an AI assistant. The assistant finally "gets it." You make progress.

**Session 2:** "Hey, update the auth flow to support OAuth."  
Assistant: "I don't see any auth files. Let me search..."  
*...10 minutes of re-exploration...*

**Session 3, 4, 5:** The same dance. Every. Single. Time.

Your AI assistant has **no memory** between sessions. And even within a session, it struggles to find the right context amid thousands of files.

Sound familiar? Yeah, it got me too.

---

## What If Your AI Actually Remembered?

That's exactly what **Mimir** does.

Mimir is a knowledge base system that gives your AI assistant permanent, semantic memory across all your projects. You install it once, and it automatically indexes your documentation and code—then serves that context to any AI tool you use.

The result? Your AI stops asking "which auth file?" and starts asking "which OAuth provider do you prefer?"

Honestly, it's one of those tools that makes you wonder how you lived without it.

---

## How It Works (In Plain English)

### 1. Index Once, Query Forever

You run one command to index your project's documentation and code:

```bash
python .opencode/mimir-index.py
```

Mimir creates a **semantic search index**—a vector database that understands *meaning*, not just keywords.

### 2. Ask Questions Naturally

```bash
# Instead of: "read auth.py, then middleware.py, then token.py"
# You just ask: "How does authentication work in this codebase?"
```

Mimir finds the relevant files and synthesizes an answer. Even if you use different words than what's in the code.

### 3. It Works Across All Your Projects

Switch projects? Mimir auto-detects the project root and loads that project's knowledge base. No configuration. No environment variables. It just works.

This was the part that sold me. I didn't want another tool that needed hand-holding per project.

---

## Why Semantic Search Changes Everything

Here's where it gets cool.

Traditional search: `"auth"` → finds files with "auth" in the name.

Semantic search: `"authentication"` → finds:
- `auth.py` (the auth module)
- `middleware.py` (token parsing)
- `api/client.py` (refresh token logic)
- `config/auth.go` (OAuth settings)

Same concept, different words. **It just works.**

I was skeptical at first. Felt like magic. But after using it for a few weeks, I stopped going back to manual grep searches. The semantic approach just... finds things.

---

## Real Numbers

I tracked token usage and costs across multiple projects:

| Scenario | Without Mimir | With Mimir | Savings |
|----------|--------------|------------|---------|
| First refactor | 25k tokens ($0.75) | 8k + $0.001 ($0.25) | 67% |
| Second refactor | 25k tokens ($0.75) | 5k + $0.001 ($0.16) | 79% |
| Third refactor | 25k tokens ($0.75) | 5k + $0.001 ($0.16) | 79% |

**Cumulative savings: 75%+ on token costs**

But honestly? The real win isn't money—it's **time**. I saved 5-10 minutes per session on context rebuilding. That adds up fast when you're doing it dozens of times a week.

---

## Getting Started (10 Minutes)

Here's exactly what I did to get it running:

### 1. Install Mimir

```bash
# Clone or copy to a central location
mkdir -p ~/Documents/Mimir
cd ~/Documents/Mimir
pip install -r requirements.txt
```

### 2. Initialize Your Project

```bash
cd ~/Documents/YourProject
python ~/Documents/Mimir/mimir-init.py
```

This creates:
- `docs/` — Add your documentation here
- `.knowledge/llamaindex/` — Your project's search index
- `.opencode/mimir-index.py` — Indexing script

### 3. Index and Query

```bash
# Index your docs
python .opencode/mimir-index.py

# Ask questions
python ~/Documents/Mimir/mcp_server_llamaindex.py --query "How does auth work?"
```

That's it. Your project is now searchable by meaning.

---

## Integration with AI Tools

Mimir speaks **MCP (Model Context Protocol)**—the standard for AI tool integration.

Configure it once in your AI tool's config:

```json
{
  "mcp": {
    "mimir-knowledge": {
      "type": "local",
      "command": ["uv", "run", "--python", "3.11", "/path/to/Mimir/mcp_server_llamaindex.py"],
      "environment": {
        "PROJECT_ROOT": "${workspaceFolder}"
      }
    }
  }
}
```

Now your AI assistant automatically has access to your project's knowledge base. No prompts needed.

---

## What Mimir Indexes

By default, Mimir indexes your `docs/` directory. But you can also index source code:

```json
// .mimir/config.json
{
  "docs_dir": "docs",
  "code_dirs": ["src", "tests", "lib"]
}
```

Now you can ask questions like:
- "Where is the user authentication logic?"
- "Find all files that call the payment API"
- "What does the Config class do?"

Game changer for understanding unfamiliar codebases.

---

## The Architecture (For the Curious)

Mimir uses a simple, proven stack:

```
┌─────────────────────────────────────┐
│  Your AI Tool (OpenCode, etc.)      │
│         ↓ MCP Protocol              │
│  ┌─────────────────────────────────┐│
│  │  mcp_server_llamaindex.py       ││
│  │  (Handles requests, routes)      ││
│  └─────────────────────────────────┘│
│         ↓                           │
│  ┌─────────────────────────────────┐│
│  │  LlamaIndex                     ││
│  │  (Semantic search, embeddings)  ││
│  └─────────────────────────────────┘│
│         ↓                           │
│  ┌─────────────────────────────────┐│
│  │  .knowledge/llamaindex/         ││
│  │  (Per-project vector store)    ││
│  └─────────────────────────────────┘│
```

Key design decisions:
- **Central server, per-project storage** — One install serves unlimited projects
- **Auto-detects project root** — Uses `.git/`, `.opencode/`, `package.json` as markers
- **OpenRouter support** — No OpenAI API key required

---

## When Mimir Shines

✅ **Large codebases** — Find anything in seconds, not minutes  
✅ **Cross-cutting changes** — See how features touch multiple systems  
✅ **Team onboarding** — New devs get instant context  
✅ **Maintenance work** — "How does X work again?" queries  
✅ **Multi-project knowledge** — Share patterns across projects

---

## Try It

```bash
# 1. Initialize
python ~/Documents/Mimir/mimir-init.py

# 2. Index
python .opencode/mimir-index.py

# 3. Query
python ~/Documents/Mimir/mcp_server_llamaindex.py --query "Your question here"
```

Or use it directly from your AI assistant—no CLI needed.

---

## The Bottom Line

Every session, you're paying twice: once in tokens, once in time. Mimir eliminates the context tax.

**Install once. Index your knowledge. Query forever.**

Your AI assistant becomes genuinely helpful instead of constantly asking you to re-explain your codebase.

---

*Mimir: Knowledge that follows you, not the other way around.*

**Repository:** [github.com/ewheels44/Mimir](https://github.com/ewheels44/Mimir)
