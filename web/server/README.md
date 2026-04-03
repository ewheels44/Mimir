# Mimir Web UI

React + TypeScript frontend, Axum (Rust) backend, Python sidecar for LlamaIndex.

## Structure

```
web/
├── server/          Rust/Axum HTTP server
│   └── src/
│       ├── main.rs          Routing + handlers
│       ├── graph.rs         Docstore parser, graph builder, cache
│       ├── metrics.rs       JSONL metrics reader
│       ├── proxy.rs         HTTP proxy to Python sidecar
│       └── sidecar.rs      Child process manager
├── sidecar/
│   └── sidecar.py          Python sidecar (search + query only)
├── client/          React/Vite frontend
│   └── src/
│       ├── pages/           GraphPage, MetricsPage
│       ├── components/      Sidebar, ModuleSidebar, ContextPanel, ResultsPanel
│       ├── hooks/           useGraphSettings, useGraphCache
│       └── lib/             cytoscapeSetup, physics, insights
├── dev.sh           Development runner (Rust + Vite in parallel)
└── build.sh         Production build
```

## Quick start (dev)

```bash
cd web

# First time: make sure Rust toolchain and Node 20+ are installed
# Activate your Mimir Python virtualenv first so sidecar.py can import LlamaIndex

./dev.sh --project /path/to/your/project
```

Opens at http://localhost:5173 (Vite, proxies `/api` to Rust on 8000).
The Python sidecar starts automatically on port 18001.

## Production

```bash
./build.sh
./server/target/release/mimir-web --project /path/to/your/project
```

Open http://localhost:8000. The Rust binary serves the React build statically
and spawns the Python sidecar automatically.

## Environment variables

| Variable           | Default                          | Description                        |
|--------------------|----------------------------------|------------------------------------|
| `PROJECT_ROOT`     | cwd                              | Root of the project to analyse     |
| `KNOWLEDGE_DIR`    | `$PROJECT_ROOT/.knowledge/llamaindex` | LlamaIndex docstore location  |
| `PYTHON_EXECUTABLE`| `python3`                        | Python binary for the sidecar      |
| `RUST_LOG`         | `mimir_web=info,warn`            | Tracing filter                     |

## How the cache works

| Layer | What | TTL |
|-------|------|-----|
| Rust in-process | Graph nodes + edges | Invalidated when `docstore.json` or `code_relationships.json` mtimes change |
| Client sessionStorage | Serialised Cytoscape graph | 5 minutes, also invalidated via `/api/graph/cache-key` |
| Client sessionStorage | UI settings | Persists for session |

Navigating to `/metrics` and back restores the graph instantly from the client
cache — no waiting for nodes to repopulate.

## Notes

- `server.py` is superseded by this directory and can be removed from the repo.
- The sidecar only handles `/internal/search`, `/internal/query`, `/internal/stats`.
  All graph building, metrics, and static serving have moved to Rust.
- The `templates/` directory is no longer needed — the metrics page is a React route.
