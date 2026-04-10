"""Mimir Python sidecar — handles LlamaIndex search/query only.

The Rust backend spawns this process and proxies /api/search and /api/query to it.
Everything else (graph building, metrics, static serving) lives in Rust.
"""

from __future__ import annotations

import argparse
import os
import sys
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

# ---------------------------------------------------------------------------
# Bootstrap Mimir imports
# ---------------------------------------------------------------------------

MIMIR_DIR = Path.home() / "Documents" / "Mimir"
sys.path.insert(0, str(MIMIR_DIR))

try:
    from mcp_server_llamaindex import KnowledgeServer
    from mimir.config import MimirConfig, get_config

    _import_ok = True
    _import_err = None
except Exception as exc:
    _import_ok = False
    _import_err = str(exc)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Mimir Python Sidecar", version="1.0.0")

_config: MimirConfig | None = None


def get_sidecar_config() -> MimirConfig:
    global _config
    if _config is None:
        _config = get_config()
    return _config


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class QueryRequest(BaseModel):
    question: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok", "imports_ok": _import_ok, "error": _import_err}


@app.post("/internal/search")
async def search(req: SearchRequest):
    if not _import_ok:
        return JSONResponse(
            status_code=503,
            content=[{"title": "Import Error", "snippet": _import_err, "source": ""}],
        )
    try:
        server = KnowledgeServer(get_sidecar_config())
        results_text = server.search(req.query, req.top_k)

        if (
            "No relevant documents found" in results_text
            or "No knowledge base" in results_text
        ):
            return [{"title": "No Results", "snippet": results_text, "source": ""}]

        results = []
        for entry in results_text.split("\n\n"):
            if not entry.strip():
                continue
            lines = entry.strip().split("\n")
            header = lines[0]
            content = "\n".join(lines[1:]) if len(lines) > 1 else ""
            match = re.match(r"\[\d+\]\s+(.+?)\s+\(score:", header)
            fname = match.group(1) if match else "Unknown"
            results.append(
                {"title": fname, "snippet": content.strip() or header, "source": fname}
            )
        return results
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.post("/internal/query")
async def query(req: QueryRequest):
    if not _import_ok:
        return JSONResponse(status_code=503, content={"detail": _import_err})
    try:
        server = KnowledgeServer(get_sidecar_config())
        answer = server.query(req.question)
        return {"answer": answer}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/internal/stats")
async def stats():
    if not _import_ok:
        return JSONResponse(status_code=503, content={"detail": _import_err})
    try:
        return KnowledgeServer(get_sidecar_config()).get_stats()
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mimir Python sidecar")
    parser.add_argument("--port", type=int, default=18001)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if not os.environ.get("PROJECT_ROOT"):
        os.environ["PROJECT_ROOT"] = str(Path.cwd())
    if not os.environ.get("KNOWLEDGE_DIR"):
        pr = Path(os.environ["PROJECT_ROOT"])
        os.environ["KNOWLEDGE_DIR"] = str(pr / ".knowledge" / "llamaindex")

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
