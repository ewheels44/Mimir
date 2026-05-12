"""Cost and usage metrics tracking for Mimir.

Tracks token usage, costs, and time savings across Mimir operations.
Stores data in JSONL format for easy analysis.

v2 additions:
- QueryMetrics now stores per-component costs (embedding, llm_input, llm_output)
  so the web dashboard can show where each dollar actually goes.
- get_component_breakdown() for the /api/metrics/breakdown endpoint.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Cost tables
# ---------------------------------------------------------------------------

MODEL_COSTS = {
    "text-embedding-3-small": {"input": 0.00002, "output": 0.0},
    "text-embedding-3-large": {"input": 0.00013, "output": 0.0},
    "google/gemini-3.1-flash-lite-preview": {"input": 0.000075, "output": 0.0003},
    "google/gemini-2.0-flash-exp": {"input": 0.0001, "output": 0.0004},
    "openai/gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "anthropic/claude-3.5-haiku": {"input": 0.00025, "output": 0.00125},
    "google/gemini-2.0-pro": {"input": 0.0005, "output": 0.002},
    "moonshotai/kimi-k2.5": {"input": 0.00042, "output": 0.0022},
    "anthropic/claude-3.5-sonnet": {"input": 0.003, "output": 0.015},
    "openai/gpt-4o": {"input": 0.0025, "output": 0.01},
}

# Conservative per-query token estimates broken out by component
QUERY_TOKEN_ESTIMATES = {
    "search": {
        "embedding_tokens": 100,
        "context_tokens": 1500,
        "llm_tokens_in": 0,
        "llm_tokens_out": 0,
    },
    "query": {
        "embedding_tokens": 100,
        "context_tokens": 2000,
        "llm_tokens_in": 500,
        "llm_tokens_out": 300,
    },
    "rag": {
        "embedding_tokens": 100,
        "context_tokens": 3000,
        "llm_tokens_in": 800,
        "llm_tokens_out": 400,
    },
    "agent": {
        "embedding_tokens": 100,
        "context_tokens": 4000,
        "llm_tokens_in": 1000,
        "llm_tokens_out": 500,
    },
}

TRADITIONAL_TOKENS_PER_QUERY = {
    "search": 3000,
    "query": 8000,
    "rag": 12000,
    "agent": 15000,
    "index": 0,
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    embedding_tokens: int = 0

    def add_llm_tokens(self, prompt: int, completion: int):
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens = self.prompt_tokens + self.completion_tokens

    def add_embedding_tokens(self, tokens: int):
        self.embedding_tokens += tokens
        self.total_tokens = (
            self.prompt_tokens + self.completion_tokens + self.embedding_tokens
        )

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "embedding_tokens": self.embedding_tokens,
        }


class TokenTracker:
    _instance: Optional["TokenTracker"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.reset()
        return cls._instance

    def reset(self):
        self.usage = TokenUsage()
        self.has_actual_data = False

    def on_llm_response(self, prompt_tokens: int, completion_tokens: int):
        self.usage.add_llm_tokens(prompt_tokens, completion_tokens)
        self.has_actual_data = True

    def on_embedding(self, token_count: int):
        self.usage.add_embedding_tokens(token_count)
        self.has_actual_data = True

    def get_usage(self) -> TokenUsage:
        return self.usage


def get_token_tracker() -> TokenTracker:
    return TokenTracker()


@dataclass
class QueryMetrics:
    """Single query metrics record — v2 adds per-component cost breakdown."""

    timestamp: str
    query_type: str
    query_text: Optional[str]
    model: str
    tokens_in: int
    tokens_out: int
    cost: float
    docs_retrieved: int
    duration_ms: int
    project_root: Optional[str] = None
    actual_tokens: Optional[dict] = None

    # v2: per-component costs (0.0 for older records)
    embedding_cost: float = 0.0
    llm_input_cost: float = 0.0
    llm_output_cost: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "QueryMetrics":
        # Tolerate records written before v2 (missing component fields)
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}

        has_components = (
            filtered.get("embedding_cost", 0) > 0
            or filtered.get("llm_input_cost", 0) > 0
            or filtered.get("llm_output_cost", 0) > 0
        )
        if not has_components and filtered.get("cost", 0) > 0:
            qt = filtered.get("query_type", "query")
            estimates = QUERY_TOKEN_ESTIMATES.get(qt, QUERY_TOKEN_ESTIMATES["query"])

            embed_rate = MODEL_COSTS["text-embedding-3-small"]["input"]
            llm_rate_in = MODEL_COSTS["google/gemini-3.1-flash-lite-preview"]["input"]
            llm_rate_out = MODEL_COSTS["google/gemini-3.1-flash-lite-preview"]["output"]

            filtered["embedding_cost"] = round(
                (estimates["embedding_tokens"] / 1000) * embed_rate, 6
            )
            filtered["llm_input_cost"] = round(
                (estimates["llm_tokens_in"] / 1000) * llm_rate_in, 6
            )
            filtered["llm_output_cost"] = round(
                (estimates["llm_tokens_out"] / 1000) * llm_rate_out, 6
            )

        return cls(**filtered)


# ---------------------------------------------------------------------------
# Metrics tracker
# ---------------------------------------------------------------------------


class MetricsTracker:
    """Track and report Mimir usage metrics."""

    def __init__(self, project_root: Optional[Path] = None):
        from src.mimir.config import get_config

        config = get_config(project_root=project_root)
        self.project_root = config.project_root
        self.metrics_file = self.project_root / ".knowledge" / "cost_metrics.jsonl"
        self._ensure_metrics_dir()

    def _ensure_metrics_dir(self):
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Cost calculation
    # ------------------------------------------------------------------

    def calculate_query_cost(
        self,
        query_type: str,
        model: str = "google/gemini-3.1-flash-lite-preview",
        embedding_model: str = "text-embedding-3-small",
    ) -> dict:
        """Return full cost breakdown dict including per-component costs."""
        estimates = QUERY_TOKEN_ESTIMATES.get(
            query_type, QUERY_TOKEN_ESTIMATES["query"]
        )
        llm_costs = MODEL_COSTS.get(
            model, MODEL_COSTS["google/gemini-3.1-flash-lite-preview"]
        )
        embed_costs = MODEL_COSTS.get(
            embedding_model, MODEL_COSTS["text-embedding-3-small"]
        )

        embedding_cost = (estimates["embedding_tokens"] / 1000) * embed_costs["input"]
        llm_input_cost = (estimates["llm_tokens_in"] / 1000) * llm_costs["input"]
        llm_output_cost = (estimates["llm_tokens_out"] / 1000) * llm_costs["output"]
        total_cost = embedding_cost + llm_input_cost + llm_output_cost

        return {
            "embedding_tokens": estimates["embedding_tokens"],
            "context_tokens": estimates["context_tokens"],
            "llm_tokens_in": estimates["llm_tokens_in"],
            "llm_tokens_out": estimates["llm_tokens_out"],
            "total_tokens": (
                estimates["embedding_tokens"]
                + estimates["context_tokens"]
                + estimates["llm_tokens_in"]
                + estimates["llm_tokens_out"]
            ),
            "embedding_cost": round(embedding_cost, 6),
            "llm_input_cost": round(llm_input_cost, 6),
            "llm_output_cost": round(llm_output_cost, 6),
            "total_cost": round(total_cost, 6),
        }

    def calculate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Legacy helper: total cost from raw token counts."""
        costs = MODEL_COSTS.get(
            model, MODEL_COSTS["google/gemini-3.1-flash-lite-preview"]
        )
        return round(
            (tokens_in / 1000) * costs["input"] + (tokens_out / 1000) * costs["output"],
            6,
        )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_query(
        self,
        query_type: str,
        query_text: Optional[str] = None,
        model: str = "google/gemini-3.1-flash-lite-preview",
        tokens_in: int = 0,
        tokens_out: int = 0,
        docs_retrieved: int = 0,
        duration_ms: int = 0,
        actual_tokens: Optional[dict] = None,
    ) -> QueryMetrics:
        """Record a query metric with per-component cost breakdown.

        When *actual_tokens* is provided and contains real API usage, those
        numbers are used.  Otherwise conservative estimates are applied.
        """
        embedding_model = "text-embedding-3-small"

        if actual_tokens and actual_tokens.get("total_tokens", 0) > 0:
            # Real API data path
            embed_costs = MODEL_COSTS[embedding_model]
            llm_costs = MODEL_COSTS.get(
                model, MODEL_COSTS["google/gemini-3.1-flash-lite-preview"]
            )

            embedding_cost = round(
                (actual_tokens.get("embedding_tokens", 0) / 1000)
                * embed_costs["input"],
                6,
            )
            llm_input_cost = round(
                (actual_tokens.get("prompt_tokens", 0) / 1000) * llm_costs["input"], 6
            )
            llm_output_cost = round(
                (actual_tokens.get("completion_tokens", 0) / 1000)
                * llm_costs["output"],
                6,
            )
            total_cost = embedding_cost + llm_input_cost + llm_output_cost

            tokens_in_use = actual_tokens.get("prompt_tokens", 0) + actual_tokens.get(
                "embedding_tokens", 0
            )
            tokens_out_use = actual_tokens.get("completion_tokens", 0)
        else:
            # Estimate path
            breakdown = self.calculate_query_cost(query_type, model, embedding_model)
            embedding_cost = breakdown["embedding_cost"]
            llm_input_cost = breakdown["llm_input_cost"]
            llm_output_cost = breakdown["llm_output_cost"]
            total_cost = breakdown["total_cost"]
            tokens_in_use = breakdown["total_tokens"]
            tokens_out_use = breakdown["llm_tokens_out"]
            actual_tokens = None

        metrics = QueryMetrics(
            timestamp=datetime.now().isoformat(),
            query_type=query_type,
            query_text=query_text[:200] if query_text else None,
            model=model,
            tokens_in=tokens_in if tokens_in else tokens_in_use,
            tokens_out=tokens_out if tokens_out else tokens_out_use,
            cost=round(total_cost, 6),
            docs_retrieved=docs_retrieved,
            duration_ms=duration_ms,
            project_root=str(self.project_root),
            actual_tokens=actual_tokens,
            embedding_cost=embedding_cost,
            llm_input_cost=llm_input_cost,
            llm_output_cost=llm_output_cost,
        )

        with open(self.metrics_file, "a") as f:
            f.write(json.dumps(metrics.to_dict()) + "\n")

        return metrics

    # ------------------------------------------------------------------
    # Loading & aggregation
    # ------------------------------------------------------------------

    def load_metrics(self, days: Optional[int] = None) -> list:
        if not self.metrics_file.exists():
            return []
        metrics = []
        cutoff = datetime.now() - timedelta(days=days) if days else None
        try:
            with open(self.metrics_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if cutoff and datetime.fromisoformat(data["timestamp"]) < cutoff:
                                continue
                        metrics.append(QueryMetrics.from_dict(data))
                    except (json.JSONDecodeError, KeyError, TypeError):
                        continue
        except FileNotFoundError:
            pass
        return metrics

    def get_summary(self, days: Optional[int] = None) -> dict:
        metrics = self.load_metrics(days)
        if not metrics:
            return {
                "total_queries": 0,
                "total_cost": 0.0,
                "traditional_cost": 0.0,
                "savings": 0.0,
                "savings_percent": 0.0,
            }
        total_cost = sum(m.cost for m in metrics)
        total_queries = len(metrics)
        traditional_tokens = sum(
            TRADITIONAL_TOKENS_PER_QUERY.get(m.query_type, 5000) for m in metrics
        )
        traditional_cost = (traditional_tokens / 1000) * 0.001
        savings = traditional_cost - total_cost
        savings_pct = (savings / traditional_cost * 100) if traditional_cost > 0 else 0
        return {
            "total_queries": total_queries,
            "total_cost": round(total_cost, 4),
            "traditional_cost": round(traditional_cost, 4),
            "savings": round(savings, 4),
            "savings_percent": round(savings_pct, 1),
            "by_type": self._breakdown_by_type(metrics),
        }

    def _breakdown_by_type(self, metrics: list) -> dict:
        breakdown: dict = {}
        for m in metrics:
            qt = m.query_type
            if qt not in breakdown:
                breakdown[qt] = {
                    "count": 0,
                    "cost": 0.0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    # v2 component totals
                    "embedding_cost": 0.0,
                    "llm_input_cost": 0.0,
                    "llm_output_cost": 0.0,
                }
            breakdown[qt]["count"] += 1
            breakdown[qt]["cost"] += m.cost
            breakdown[qt]["tokens_in"] += m.tokens_in
            breakdown[qt]["tokens_out"] += m.tokens_out
            breakdown[qt]["embedding_cost"] += m.embedding_cost
            breakdown[qt]["llm_input_cost"] += m.llm_input_cost
            breakdown[qt]["llm_output_cost"] += m.llm_output_cost

        for data in breakdown.values():
            data["cost"] = round(data["cost"], 4)
            data["embedding_cost"] = round(data["embedding_cost"], 6)
            data["llm_input_cost"] = round(data["llm_input_cost"], 6)
            data["llm_output_cost"] = round(data["llm_output_cost"], 6)
        return breakdown

    def get_component_totals(self, days: Optional[int] = None) -> dict:
        """Aggregate embedding vs LLM spend across all query types."""
        metrics = self.load_metrics(days)
        totals = {
            "embedding_cost": round(sum(m.embedding_cost for m in metrics), 6),
            "llm_input_cost": round(sum(m.llm_input_cost for m in metrics), 6),
            "llm_output_cost": round(sum(m.llm_output_cost for m in metrics), 6),
            "total_cost": round(sum(m.cost for m in metrics), 6),
        }
        return totals

    def format_report(self, days: Optional[int] = 30) -> str:
        summary = self.get_summary(days)
        if summary["total_queries"] == 0:
            return "No metrics found. Start using Mimir to track savings!"
        period = f"Last {days} days" if days else "All time"
        lines = [
            f"\n{'=' * 60}",
            f"Mimir Cost Report ({period})",
            f"{'=' * 60}",
            "",
            f"Total queries:           {summary['total_queries']}",
            f"Total Mimir cost:        ${summary['total_cost']:.4f}",
            "",
            "Estimated without Mimir:",
            f"  Traditional cost:      ${summary['traditional_cost']:.4f}",
            f"  Mimir cost:            ${summary['total_cost']:.4f}",
            "",
            f"  Savings:               ${summary['savings']:.4f} ({summary['savings_percent']:.0f}%)",
            "",
        ]
        if summary.get("by_type"):
            lines.append("Usage breakdown:")
            lines.append("-" * 40)
            for qt, data in sorted(summary["by_type"].items()):
                embed_pct = (
                    (data["embedding_cost"] / data["cost"] * 100) if data["cost"] else 0
                )
                lines.append(
                    f"  {qt:12} {data['count']:4} queries  "
                    f"${data['cost']:.4f}  "
                    f"(embed {embed_pct:.0f}%)"
                )
            lines.append("")
        lines.append(f"{'=' * 60}\n")
        return "\n".join(lines)

    def get_daily_stats(self, days: int = 30) -> list:
        metrics = self.load_metrics(days)
        daily: dict = {}
        for m in metrics:
            day = m.timestamp[:10]
            if day not in daily:
                daily[day] = {
                    "queries": 0,
                    "cost": 0.0,
                    "traditional_tokens": 0,
                    "embedding_cost": 0.0,
                    "llm_input_cost": 0.0,
                    "llm_output_cost": 0.0,
                }
            daily[day]["queries"] += 1
            daily[day]["cost"] += m.cost
            daily[day]["traditional_tokens"] += TRADITIONAL_TOKENS_PER_QUERY.get(
                m.query_type, 5000
            )
            daily[day]["embedding_cost"] += m.embedding_cost
            daily[day]["llm_input_cost"] += m.llm_input_cost
            daily[day]["llm_output_cost"] += m.llm_output_cost

        result = []
        for day, data in sorted(daily.items()):
            trad_cost = (data["traditional_tokens"] / 1000) * 0.001
            result.append(
                {
                    "date": day,
                    "queries": data["queries"],
                    "cost": round(data["cost"], 4),
                    "traditional_cost": round(trad_cost, 4),
                    "embedding_cost": round(data["embedding_cost"], 6),
                    "llm_input_cost": round(data["llm_input_cost"], 6),
                    "llm_output_cost": round(data["llm_output_cost"], 6),
                }
            )
        return result


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_tracker: Optional[MetricsTracker] = None


def get_tracker(project_root: Optional[Path] = None) -> MetricsTracker:
    global _tracker
    if _tracker is None:
        _tracker = MetricsTracker(project_root)
    return _tracker


def record_query(**kwargs) -> QueryMetrics:
    return get_tracker().record_query(**kwargs)


def format_report(days: Optional[int] = 30) -> str:
    return get_tracker().format_report(days)


def get_summary(days: Optional[int] = None) -> dict:
    return get_tracker().get_summary(days)
