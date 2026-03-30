"""Cost and usage metrics tracking for Mimir.

Tracks token usage, costs, and time savings across Mimir operations.
Stores data in JSONL format for easy analysis.
"""

import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# Cost per 1K tokens (as of 2026-03, OpenRouter rates)
MODEL_COSTS = {
    # Embeddings (per 1K tokens)
    "text-embedding-3-small": {"input": 0.00002, "output": 0.0},
    "text-embedding-3-large": {"input": 0.00013, "output": 0.0},
    # Cheap/fast models (per 1K tokens)
    "google/gemini-3.1-flash-lite-preview": {"input": 0.000075, "output": 0.0003},
    "google/gemini-2.0-flash-exp": {"input": 0.0001, "output": 0.0004},
    "openai/gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    # Mid-range (per 1K tokens)
    "anthropic/claude-3.5-haiku": {"input": 0.00025, "output": 0.00125},
    "google/gemini-2.0-pro": {"input": 0.0005, "output": 0.002},
    # Premium (per 1K tokens)
    "anthropic/claude-3.5-sonnet": {"input": 0.003, "output": 0.015},
    "openai/gpt-4o": {"input": 0.0025, "output": 0.01},
}

# Token estimates per query type (conservative averages)
QUERY_TOKEN_ESTIMATES = {
    # Search: query embedding (~100 tokens) + context retrieved (~1500 tokens avg)
    "search": {
        "embedding_tokens": 100,
        "context_tokens": 1500,
        "llm_tokens_in": 0,
        "llm_tokens_out": 0,
    },
    # Query: query embedding (~100) + context (~2000) + LLM processing (~500 in, ~300 out)
    "query": {
        "embedding_tokens": 100,
        "context_tokens": 2000,
        "llm_tokens_in": 500,
        "llm_tokens_out": 300,
    },
    # RAG: query embedding (~100) + context (~3000) + LLM (~800 in, ~400 out)
    "rag": {
        "embedding_tokens": 100,
        "context_tokens": 3000,
        "llm_tokens_in": 800,
        "llm_tokens_out": 400,
    },
    # Agent: query embedding (~100) + context (~4000) + LLM (~1000 in, ~500 out)
    "agent": {
        "embedding_tokens": 100,
        "context_tokens": 4000,
        "llm_tokens_in": 1000,
        "llm_tokens_out": 500,
    },
}

# Estimated tokens for traditional approach (without Mimir)
# Based on: reading files, understanding context, grep searches, etc.
TRADITIONAL_TOKENS_PER_QUERY = {
    "search": 3000,  # ~3 files × 1000 tokens average
    "query": 8000,  # More context needed for synthesis
    "rag": 12000,  # RAG workflow + generation
    "agent": 15000,  # Agentic exploration
    "index": 0,  # One-time cost, calculated separately
}


@dataclass
class TokenUsage:
    """Tracks actual token usage from API calls."""

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
    """Singleton tracker to capture token usage across operations."""

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
    """Single query metrics record."""

    timestamp: str
    query_type: str  # search, query, rag, agent, index
    query_text: Optional[str]
    model: str
    tokens_in: int
    tokens_out: int
    cost: float
    docs_retrieved: int
    duration_ms: int
    project_root: Optional[str] = None
    actual_tokens: Optional[dict] = None  # Real API usage if available

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "QueryMetrics":
        return cls(**data)


class MetricsTracker:
    """Track and report Mimir usage metrics."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or self._detect_project_root()
        self.metrics_file = self.project_root / ".knowledge" / "cost_metrics.jsonl"
        self._ensure_metrics_dir()

    def _detect_project_root(self) -> Path:
        """Detect project root from current directory."""
        cwd = Path.cwd().resolve()
        markers = [
            ".opencode",
            ".git",
            "pyproject.toml",
            "package.json",
            "opencode.json",
        ]

        current = cwd
        while current != current.parent:
            if any((current / marker).exists() for marker in markers):
                return current
            current = current.parent

        return cwd

    def _ensure_metrics_dir(self):
        """Ensure metrics directory exists."""
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

    def calculate_query_cost(
        self,
        query_type: str,
        model: str = "google/gemini-3.1-flash-lite-preview",
        embedding_model: str = "text-embedding-3-small",
    ) -> dict:
        """Calculate realistic cost breakdown for a query type.

        Returns dict with token breakdown and costs.
        """
        estimates = QUERY_TOKEN_ESTIMATES.get(
            query_type, QUERY_TOKEN_ESTIMATES["query"]
        )

        # Get model costs
        llm_costs = MODEL_COSTS.get(
            model, MODEL_COSTS["google/gemini-3.1-flash-lite-preview"]
        )
        embed_costs = MODEL_COSTS.get(
            embedding_model, MODEL_COSTS["text-embedding-3-small"]
        )

        # Calculate embedding cost (input only)
        embedding_cost = (estimates["embedding_tokens"] / 1000) * embed_costs["input"]

        # Calculate LLM cost (if applicable)
        llm_input_cost = (estimates["llm_tokens_in"] / 1000) * llm_costs["input"]
        llm_output_cost = (estimates["llm_tokens_out"] / 1000) * llm_costs["output"]
        llm_cost = llm_input_cost + llm_output_cost

        total_cost = embedding_cost + llm_cost
        total_tokens = (
            estimates["embedding_tokens"]
            + estimates["context_tokens"]
            + estimates["llm_tokens_in"]
            + estimates["llm_tokens_out"]
        )

        return {
            "embedding_tokens": estimates["embedding_tokens"],
            "context_tokens": estimates["context_tokens"],
            "llm_tokens_in": estimates["llm_tokens_in"],
            "llm_tokens_out": estimates["llm_tokens_out"],
            "total_tokens": total_tokens,
            "embedding_cost": round(embedding_cost, 6),
            "llm_cost": round(llm_cost, 6),
            "total_cost": round(total_cost, 6),
        }

    def calculate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Legacy method: Calculate cost in USD for a model and token count."""
        costs = MODEL_COSTS.get(
            model, MODEL_COSTS["google/gemini-3.1-flash-lite-preview"]
        )

        input_cost = (tokens_in / 1000) * costs["input"]
        output_cost = (tokens_out / 1000) * costs["output"]

        return round(input_cost + output_cost, 6)

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
        """Record a query metric with realistic cost estimation.

        If actual_tokens dict is provided with 'prompt_tokens', 'completion_tokens',
        and 'total_tokens', uses real API usage data. Otherwise falls back to estimates.
        """
        # Check if we have actual token usage
        if actual_tokens and actual_tokens.get("total_tokens", 0) > 0:
            # Use actual token data
            cost = self._calculate_cost_from_dict(actual_tokens, model)
            total_tokens = actual_tokens.get("total_tokens", 0)
            tokens_in_actual = actual_tokens.get(
                "prompt_tokens", 0
            ) + actual_tokens.get("embedding_tokens", 0)
            tokens_out_actual = actual_tokens.get("completion_tokens", 0)
        else:
            # Fall back to estimates
            cost_breakdown = self.calculate_query_cost(query_type, model)
            cost = cost_breakdown["total_cost"]
            total_tokens = cost_breakdown["total_tokens"]
            tokens_in_actual = total_tokens
            tokens_out_actual = cost_breakdown["llm_tokens_out"]
            actual_tokens = None

        metrics = QueryMetrics(
            timestamp=datetime.now().isoformat(),
            query_type=query_type,
            query_text=query_text[:200]
            if query_text
            else None,  # Truncate long queries
            model=model,
            tokens_in=tokens_in_actual if tokens_in == 0 else tokens_in,
            tokens_out=tokens_out_actual if tokens_out == 0 else tokens_out,
            cost=cost,
            docs_retrieved=docs_retrieved,
            duration_ms=duration_ms,
            project_root=str(self.project_root),
            actual_tokens=actual_tokens,
        )

        # Append to JSONL file
        with open(self.metrics_file, "a") as f:
            f.write(json.dumps(metrics.to_dict()) + "\n")

        return metrics

    def _calculate_cost_from_dict(self, usage: dict, model: str) -> float:
        """Calculate cost from actual token usage dict."""
        costs = MODEL_COSTS.get(
            model, MODEL_COSTS["google/gemini-3.1-flash-lite-preview"]
        )
        embed_costs = MODEL_COSTS["text-embedding-3-small"]

        # Embedding cost
        embed_cost = (usage.get("embedding_tokens", 0) / 1000) * embed_costs["input"]

        # LLM cost
        llm_input_cost = (usage.get("prompt_tokens", 0) / 1000) * costs["input"]
        llm_output_cost = (usage.get("completion_tokens", 0) / 1000) * costs["output"]

        return round(embed_cost + llm_input_cost + llm_output_cost, 6)

    def load_metrics(self, days: Optional[int] = None) -> list[QueryMetrics]:
        """Load all metrics, optionally filtered by days."""
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
                        if cutoff:
                            ts = datetime.fromisoformat(data["timestamp"])
                            if ts < cutoff:
                                continue
                        metrics.append(QueryMetrics.from_dict(data))
                    except (json.JSONDecodeError, KeyError):
                        continue
        except FileNotFoundError:
            pass

        return metrics

    def get_summary(self, days: Optional[int] = None) -> dict:
        """Get cost summary for a time period."""
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

        # Calculate traditional cost (without Mimir)
        traditional_tokens = 0
        for m in metrics:
            traditional_tokens += TRADITIONAL_TOKENS_PER_QUERY.get(m.query_type, 5000)

        # Assume traditional approach uses same model at avg $0.001/1K tokens
        traditional_cost = (traditional_tokens / 1000) * 0.001

        savings = traditional_cost - total_cost
        savings_percent = (
            (savings / traditional_cost * 100) if traditional_cost > 0 else 0
        )

        return {
            "total_queries": total_queries,
            "total_cost": round(total_cost, 4),
            "traditional_cost": round(traditional_cost, 4),
            "savings": round(savings, 4),
            "savings_percent": round(savings_percent, 1),
            "by_type": self._breakdown_by_type(metrics),
        }

    def _breakdown_by_type(self, metrics: list[QueryMetrics]) -> dict:
        """Break down metrics by query type."""
        breakdown = {}

        for m in metrics:
            if m.query_type not in breakdown:
                breakdown[m.query_type] = {
                    "count": 0,
                    "cost": 0.0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                }

            breakdown[m.query_type]["count"] += 1
            breakdown[m.query_type]["cost"] += m.cost
            breakdown[m.query_type]["tokens_in"] += m.tokens_in
            breakdown[m.query_type]["tokens_out"] += m.tokens_out

        # Round costs
        for data in breakdown.values():
            data["cost"] = round(data["cost"], 4)

        return breakdown

    def format_report(self, days: Optional[int] = 30) -> str:
        """Generate a formatted cost report."""
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
            f"",
            f"  Savings:               ${summary['savings']:.4f} ({summary['savings_percent']:.0f}%)",
            "",
        ]

        # Add breakdown by type
        if summary.get("by_type"):
            lines.append("Usage breakdown:")
            lines.append("-" * 40)

            for query_type, data in sorted(summary["by_type"].items()):
                lines.append(
                    f"  {query_type:12} {data['count']:4} queries  ${data['cost']:.4f}"
                )

            lines.append("")

        lines.append(f"{'=' * 60}\n")

        return "\n".join(lines)

    def get_daily_stats(self, days: int = 30) -> list[dict]:
        """Get daily stats for the last N days."""
        metrics = self.load_metrics(days)

        daily = {}
        for m in metrics:
            day = m.timestamp[:10]
            if day not in daily:
                daily[day] = {"queries": 0, "cost": 0.0, "traditional_tokens": 0}
            daily[day]["queries"] += 1
            daily[day]["cost"] += m.cost
            daily[day]["traditional_tokens"] += TRADITIONAL_TOKENS_PER_QUERY.get(
                m.query_type, 5000
            )

        result = []
        for day, data in sorted(daily.items()):
            traditional_cost = (data["traditional_tokens"] / 1000) * 0.001
            result.append(
                {
                    "date": day,
                    "queries": data["queries"],
                    "cost": round(data["cost"], 4),
                    "traditional_cost": round(traditional_cost, 4),
                }
            )

        return result


# Global tracker instance
_tracker: Optional[MetricsTracker] = None


def get_tracker(project_root: Optional[Path] = None) -> MetricsTracker:
    """Get or create global metrics tracker."""
    global _tracker
    if _tracker is None:
        _tracker = MetricsTracker(project_root)
    return _tracker


def record_query(**kwargs) -> QueryMetrics:
    """Convenience function to record a query."""
    return get_tracker().record_query(**kwargs)


def format_report(days: Optional[int] = 30) -> str:
    """Convenience function to format a report."""
    return get_tracker().format_report(days)


def get_summary(days: Optional[int] = None) -> dict:
    """Convenience function to get summary."""
    return get_tracker().get_summary(days)
