> "Mimir is a persistent knowledge layer for AI agents. It indexes your codebase and docs once, then agents query it via semantic search instead of re-discovering your project every session. It cuts context waste from 30% to 5%. 
It integrates with MCP so any agent platform can use it. 
And it has an FDE toolkit — shared indices for cross-codebase search, call prep workflows, handoff generation — for engineers managing multiple customer engagements."

The Longer Version (2 minutes)
> "The problem: AI agents lose context between sessions. Every time you start a new conversation, the agent re-reads your codebase from scratch. 30% of the context window is wasted on exploration.
>
> Mimir solves this by indexing your docs and code into a vector store once. After that, agents use semantic search — 'how does auth work?' returns the relevant files with scores. No grep, no re-reading.
>
> It's built on LlamaIndex for the vector store, exposed via MCP so it works with any agent platform. It has git hooks for auto-indexing on commit, so the knowledge base stays fresh automatically.
>
> For FDEs specifically, there's a shared index feature — you index a large SDK once globally, then reference it from multiple customer projects. Results are tagged so the agent always knows what's your code vs what's the SDK reference. There's also call prep, session diff, and handoff generation workflows.
>
> The config is unified — one class, all settings, env vars override config file overrides defaults. No scattered configuration."
---
Questions They'll Ask + How to Answer
"Why not just use RAG directly?"
> "RAG is the retrieval layer — Mimir IS RAG, but with infrastructure around it. The vector store, the indexing pipeline, the git hooks for freshness, the MCP transport, the SDK caching, the per-project isolation. You could build all that yourself, or you use Mimir and focus on the agent logic."

"How is this different from Cursor or Copilot?"
> "Cursor and Copilot are IDE features. They index your code for autocomplete and chat. Mimir is agent infrastructure — it's for autonomous agents that need to understand your codebase without an IDE. 
It's MCP-native, so any agent platform can use it. And it's project-aware — each project gets its own isolated index."

"What's the scaling story?"
> "Indexing is the bottleneck — it's embedding API calls. The git hooks do incremental reindexing, so only changed files get re-embedded. 
For large SDKs, the shared index feature means you index once and reuse across projects. The vector store itself is LlamaIndex with local persistence — no external vector DB needed for single-user."

"What's the hardest technical problem you solved?"
> "The shared index composition. You can't just merge vector stores — different embedding models produce incompatible vector spaces. 
So there's validation at load time that checks the shared index uses the same embedding model as the project. And results are merged by score with source tags, so the LLM can distinguish 'what the SDK provides' from 'what the customer has.' That distinction is everything in an integration context."

"What would you build next?"
> "Three things. One, a customer onboarding workflow that generates a structured codebase summary — tech stack, architecture, integration points — 
so an FDE can go from zero to productive in hours instead of days. Two, a session diff that shows what you learned today vs yesterday. Three, a handoff generator that produces documentation from the knowledge base when you transfer to the permanent team."

"How do you handle stale data?"
> "Git hooks trigger incremental reindex on every commit — only files whose content actually changed get re-embedded, using SHA-256 hashing. 
The SDK cache has a configurable TTL (default 7 days) and falls back to stale cache if the fetch fails. The OpenSpace bridge has freshness scoring that decays over 7 days, so the agent knows when context is getting old."

"What's the business value?"
> "For an FDE doing 4 customer engagements per quarter, Mimir saves 2 days per engagement on onboarding alone. That's 8 days per quarter, or $15-25K in recovered productivity. The shared index eliminates redundant SDK indexing — you index Stripe once, not once per customer. And the handoff generator means the permanent team inherits the knowledge base, not just the code."

---
The One-Liner (if they just want a sentence)
> "Mimir gives AI agents persistent memory of your codebase so they stop re-discovering the same patterns every session."
---

What NOT to Say
- Don't say "it's like RAG" — that undersells it. It's infrastructure.
- Don't lead with the tech stack (LlamaIndex, MCP, LangGraph) — lead with the problem.
- Don't say "I built this in a weekend" — even if you did. Say "I've been iterating on this."
- Don't apologize for gaps. Say "that's on the roadmap" and move on.
Good luck in the interview.
