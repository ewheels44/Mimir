#!/usr/bin/env python3
"""Tests for the metrics tracking module."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

MIMIR_DIR = Path("/Users/ethanwheeler/Documents/Mimir")
sys.path.insert(0, str(MIMIR_DIR))

from src.mimir.metrics import (
    MODEL_COSTS,
    QUERY_TOKEN_ESTIMATES,
    TRADITIONAL_TOKENS_PER_QUERY,
    MetricsTracker,
    QueryMetrics,
    TokenTracker,
    TokenUsage,
    format_report,
    get_summary,
    get_tracker,
    record_query,
)


# ─── Constants Tests ─────────────────────────────────────────────────────────


class TestConstants:
    """Tests for module constants."""

    def test_model_costs_is_non_empty_dict(self):
        """MODEL_COSTS should be a non-empty dict."""
        assert isinstance(MODEL_COSTS, dict)
        assert len(MODEL_COSTS) > 0

    def test_model_costs_has_expected_keys(self):
        """MODEL_COSTS should contain expected model entries."""
        assert "text-embedding-3-small" in MODEL_COSTS
        assert "openai/gpt-4o" in MODEL_COSTS
        assert "anthropic/claude-3.5-sonnet" in MODEL_COSTS

    def test_model_costs_has_input_output_keys(self):
        """Each model cost entry should have input and output keys."""
        for model, costs in MODEL_COSTS.items():
            assert "input" in costs, f"Missing 'input' for {model}"
            assert "output" in costs, f"Missing 'output' for {model}"

    def test_query_token_estimates_is_non_empty_dict(self):
        """QUERY_TOKEN_ESTIMATES should be a non-empty dict."""
        assert isinstance(QUERY_TOKEN_ESTIMATES, dict)
        assert len(QUERY_TOKEN_ESTIMATES) > 0

    def test_query_token_estimates_has_expected_keys(self):
        """QUERY_TOKEN_ESTIMATES should contain expected query types."""
        assert "search" in QUERY_TOKEN_ESTIMATES
        assert "query" in QUERY_TOKEN_ESTIMATES
        assert "rag" in QUERY_TOKEN_ESTIMATES
        assert "agent" in QUERY_TOKEN_ESTIMATES


# ─── TokenUsage Tests ─────────────────────────────────────────────────────────


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_default_values_are_zero(self):
        """Should default all values to zero."""
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0
        assert usage.embedding_tokens == 0

    def test_add_llm_tokens_updates_values(self):
        """Should update prompt and completion tokens."""
        usage = TokenUsage()
        usage.add_llm_tokens(100, 50)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150

    def test_add_llm_tokens_accumulates(self):
        """Should accumulate tokens across multiple calls."""
        usage = TokenUsage()
        usage.add_llm_tokens(100, 50)
        usage.add_llm_tokens(50, 25)
        assert usage.prompt_tokens == 150
        assert usage.completion_tokens == 75
        assert usage.total_tokens == 225

    def test_add_embedding_tokens_updates_values(self):
        """Should update embedding tokens."""
        usage = TokenUsage()
        usage.add_embedding_tokens(200)
        assert usage.embedding_tokens == 200
        assert usage.total_tokens == 200

    def test_add_embedding_tokens_accumulates(self):
        """Should accumulate embedding tokens."""
        usage = TokenUsage()
        usage.add_embedding_tokens(100)
        usage.add_embedding_tokens(50)
        assert usage.embedding_tokens == 150

    def test_to_dict_returns_correct_structure(self):
        """Should return dict with all token counts."""
        usage = TokenUsage()
        usage.add_llm_tokens(100, 50)
        usage.add_embedding_tokens(25)
        d = usage.to_dict()
        assert d["prompt_tokens"] == 100
        assert d["completion_tokens"] == 50
        assert d["embedding_tokens"] == 25
        assert d["total_tokens"] == 175


# ─── TokenTracker Tests ──────────────────────────────────────────────────────


class TestTokenTracker:
    """Tests for TokenTracker singleton."""

    def test_singleton_returns_same_instance(self):
        """Should return the same instance."""
        t1 = TokenTracker()
        t2 = TokenTracker()
        assert t1 is t2

    def test_reset_clears_usage(self):
        """Should reset usage to zero."""
        tracker = TokenTracker()
        tracker.on_llm_response(100, 50)
        tracker.reset()
        assert tracker.usage.total_tokens == 0

    def test_on_llm_response_updates_usage(self):
        """Should update usage on LLM response."""
        tracker = TokenTracker()
        tracker.reset()
        tracker.on_llm_response(200, 100)
        assert tracker.usage.prompt_tokens == 200
        assert tracker.usage.completion_tokens == 100

    def test_on_embedding_updates_usage(self):
        """Should update usage on embedding."""
        tracker = TokenTracker()
        tracker.reset()
        tracker.on_embedding(150)
        assert tracker.usage.embedding_tokens == 150

    def test_has_actual_data_flag(self):
        """Should track if actual data was recorded."""
        tracker = TokenTracker()
        tracker.reset()
        assert tracker.has_actual_data is False
        tracker.on_llm_response(100, 50)
        assert tracker.has_actual_data is True


# ─── QueryMetrics Tests ───────────────────────────────────────────────────────


class TestQueryMetrics:
    """Tests for QueryMetrics dataclass."""

    def test_to_dict_returns_all_fields(self):
        """Should return dict with all fields."""
        metrics = QueryMetrics(
            timestamp="2024-01-01T00:00:00",
            query_type="search",
            query_text="test query",
            model="test-model",
            tokens_in=100,
            tokens_out=50,
            cost=0.001,
            docs_retrieved=5,
            duration_ms=100,
            project_root="/test",
            embedding_cost=0.0001,
            llm_input_cost=0.0005,
            llm_output_cost=0.0004,
        )
        d = metrics.to_dict()
        assert d["query_type"] == "search"
        assert d["cost"] == 0.001
        assert d["embedding_cost"] == 0.0001

    def test_from_dict_creates_instance(self):
        """Should create instance from dict."""
        data = {
            "timestamp": "2024-01-01T00:00:00",
            "query_type": "query",
            "query_text": "test",
            "model": "test-model",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost": 0.001,
            "docs_retrieved": 5,
            "duration_ms": 100,
            "project_root": "/test",
            "embedding_cost": 0.0001,
            "llm_input_cost": 0.0005,
            "llm_output_cost": 0.0004,
        }
        metrics = QueryMetrics.from_dict(data)
        assert metrics.query_type == "query"
        assert metrics.cost == 0.001

    def test_from_dict_backward_compatibility_v1(self):
        """Should handle v1 records without component costs."""
        # v1 record has no embedding_cost, llm_input_cost, llm_output_cost
        data = {
            "timestamp": "2024-01-01T00:00:00",
            "query_type": "search",
            "query_text": "test",
            "model": "test-model",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost": 0.001,
            "docs_retrieved": 5,
            "duration_ms": 100,
        }
        metrics = QueryMetrics.from_dict(data)
        # Should compute component costs from estimates
        assert metrics.embedding_cost > 0
        assert metrics.llm_input_cost >= 0
        assert metrics.llm_output_cost >= 0

    def test_from_dict_ignores_unknown_fields(self):
        """Should ignore unknown fields in dict."""
        data = {
            "timestamp": "2024-01-01T00:00:00",
            "query_type": "query",
            "query_text": "test",
            "model": "test-model",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost": 0.001,
            "docs_retrieved": 5,
            "duration_ms": 100,
            "unknown_field": "should be ignored",
        }
        metrics = QueryMetrics.from_dict(data)
        assert not hasattr(metrics, "unknown_field")


# ─── MetricsTracker Tests ─────────────────────────────────────────────────────


class TestMetricsTracker:
    """Tests for MetricsTracker class."""

    def test_init_creates_metrics_file_path(self, tmp_path: Path):
        """Should create metrics file path under .knowledge."""
        tracker = MetricsTracker(project_root=tmp_path)
        assert tracker.metrics_file.parent.name == ".knowledge"

    def test_calculate_query_cost_returns_breakdown(self, tmp_path: Path):
        """Should return cost breakdown dict."""
        tracker = MetricsTracker(project_root=tmp_path)
        breakdown = tracker.calculate_query_cost("search")
        assert "embedding_tokens" in breakdown
        assert "embedding_cost" in breakdown
        assert "llm_input_cost" in breakdown
        assert "llm_output_cost" in breakdown
        assert "total_cost" in breakdown

    def test_calculate_query_cost_different_types(self, tmp_path: Path):
        """Should return different costs for different query types."""
        tracker = MetricsTracker(project_root=tmp_path)
        search_cost = tracker.calculate_query_cost("search")["total_cost"]
        agent_cost = tracker.calculate_query_cost("agent")["total_cost"]
        # Agent should cost more than search
        assert agent_cost > search_cost

    def test_record_query_with_estimates(self, tmp_path: Path):
        """Should record query with estimated tokens."""
        tracker = MetricsTracker(project_root=tmp_path)
        metrics = tracker.record_query(
            query_type="search",
            query_text="test query",
        )
        assert metrics.query_type == "search"
        assert metrics.cost > 0

    def test_record_query_with_actual_tokens(self, tmp_path: Path):
        """Should record query with actual tokens."""
        tracker = MetricsTracker(project_root=tmp_path)
        metrics = tracker.record_query(
            query_type="query",
            query_text="test",
            actual_tokens={
                "prompt_tokens": 500,
                "completion_tokens": 200,
                "embedding_tokens": 100,
                "total_tokens": 800,
            },
        )
        assert metrics.tokens_in == 600  # prompt + embedding
        assert metrics.tokens_out == 200

    def test_record_query_writes_to_file(self, tmp_path: Path):
        """Should write metrics to JSONL file."""
        tracker = MetricsTracker(project_root=tmp_path)
        tracker.record_query(query_type="search", query_text="test")
        assert tracker.metrics_file.exists()
        content = tracker.metrics_file.read_text()
        assert "search" in content

    def test_load_metrics_empty_file(self, tmp_path: Path):
        """Should return empty list for missing file."""
        tracker = MetricsTracker(project_root=tmp_path)
        metrics = tracker.load_metrics()
        assert metrics == []

    def test_load_metrics_valid_jsonl(self, tmp_path: Path):
        """Should load metrics from valid JSONL file."""
        tracker = MetricsTracker(project_root=tmp_path)

        # Write some metrics
        tracker.record_query(query_type="search", query_text="test1")
        tracker.record_query(query_type="query", query_text="test2")

        # Load them back
        metrics = tracker.load_metrics()
        assert len(metrics) == 2
        assert metrics[0].query_type == "search"
        assert metrics[1].query_type == "query"

    def test_load_metrics_with_days_filter(self, tmp_path: Path):
        """Should filter metrics by days."""
        tracker = MetricsTracker(project_root=tmp_path)

        # Write metrics
        tracker.record_query(query_type="search", query_text="recent")

        # Create old metric manually
        old_metric = {
            "timestamp": (datetime.now() - timedelta(days=10)).isoformat(),
            "query_type": "old",
            "query_text": "old query",
            "model": "test",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost": 0.001,
            "docs_retrieved": 1,
            "duration_ms": 100,
        }
        with open(tracker.metrics_file, "a") as f:
            f.write(json.dumps(old_metric) + "\n")

        # Load with filter
        metrics = tracker.load_metrics(days=5)
        assert len(metrics) == 1
        assert metrics[0].query_type == "search"

    def test_get_summary_no_metrics(self, tmp_path: Path):
        """Should return zero summary when no metrics."""
        tracker = MetricsTracker(project_root=tmp_path)
        summary = tracker.get_summary()
        assert summary["total_queries"] == 0
        assert summary["total_cost"] == 0.0

    def test_get_summary_with_metrics(self, tmp_path: Path):
        """Should return correct summary with metrics."""
        tracker = MetricsTracker(project_root=tmp_path)
        tracker.record_query(query_type="search", query_text="test1")
        tracker.record_query(query_type="query", query_text="test2")

        summary = tracker.get_summary()
        assert summary["total_queries"] == 2
        assert summary["total_cost"] > 0
        assert "by_type" in summary

    def test_get_component_totals(self, tmp_path: Path):
        """Should return component cost totals."""
        tracker = MetricsTracker(project_root=tmp_path)
        tracker.record_query(query_type="search", query_text="test")
        tracker.record_query(query_type="rag", query_text="test2")

        totals = tracker.get_component_totals()
        assert "embedding_cost" in totals
        assert "llm_input_cost" in totals
        assert "llm_output_cost" in totals
        assert "total_cost" in totals

    def test_format_report_no_metrics(self, tmp_path: Path):
        """Should return message when no metrics."""
        tracker = MetricsTracker(project_root=tmp_path)
        report = tracker.format_report()
        assert "No metrics found" in report

    def test_format_report_with_metrics(self, tmp_path: Path):
        """Should format report with metrics."""
        tracker = MetricsTracker(project_root=tmp_path)
        tracker.record_query(query_type="search", query_text="test")
        tracker.record_query(query_type="query", query_text="test2")

        report = tracker.format_report()
        assert "Mimir Cost Report" in report
        assert "Total queries:" in report


# ─── Module-level Functions Tests ─────────────────────────────────────────────


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_tracker_returns_tracker(self):
        """Should return MetricsTracker instance."""
        tracker = get_tracker()
        assert isinstance(tracker, MetricsTracker)

    def test_record_query_returns_metrics(self):
        """Should return QueryMetrics instance."""
        metrics = record_query(query_type="search", query_text="test")
        assert isinstance(metrics, QueryMetrics)

    def test_format_report_returns_string(self):
        """Should return formatted string."""
        report = format_report()
        assert isinstance(report, str)

    def test_get_summary_returns_dict(self):
        """Should return summary dict."""
        summary = get_summary()
        assert isinstance(summary, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
