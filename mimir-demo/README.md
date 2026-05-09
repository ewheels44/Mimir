# Mimir Interactive Demo

An interactive visualization of Mimir's core flows for explaining design decisions.

## Features

- **Indexing Flow** - SHA-256 hashing, incremental updates, vector embedding
- **RAG Pipeline** - Query embedding, semantic search, context assembly
- **Knowledge Agent** - Multi-turn tool calling loop
- **OpenSpace Bridge** - Circuit breakers, caching, content filtering

## Running

```bash
cd mimir-demo
npm install
npm run dev
```

Then open http://localhost:5173

## What It Demonstrates

Each flow shows:
1. **Step-by-step execution** with timing estimates
2. **State inspector** showing variables at each step
3. **Design rationale** explaining why each decision was made

Use Previous/Next buttons or click any step directly to explore.