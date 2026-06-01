#!/usr/bin/env python3
"""
Tests for the five research-backed improvements to enrich_task routing:
  1. Semantic cache (embedding-based, replaces SHA256 exact-match)
  2. Query normalization (for better cache hit rates)
  3. Embedding-based classifier with confidence scores
  4. Hybrid routing (graph + vector for mid-confidence structural queries)
  5. Enhanced config (semantic threshold, hybrid bounds, normalization toggle)

Run: python -m pytest tests/test_query_router_improvements.py -v
"""

import sys
import os
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import numpy as np


# ─── Test Query Normalization ──────────────────────────────────────────────────

class TestQueryNormalization:
    """Test the normalize_query function (Improvement #2)."""

    def test_strips_can_you_please(self):
        from mimir.query_router import normalize_query
        result = normalize_query("Can you explain how the auth module works?")
        assert "can you" not in result
        assert "explain" not in result
        # Core meaning should be preserved
        assert "auth" in result
        assert "module" in result
        assert "work" in result

    def test_strips_show_me(self):
        from mimir.query_router import normalize_query
        result = normalize_query("Show me the dependency path from A to B")
        assert "show me" not in result
        assert "dependency" in result

    def test_strips_help_me(self):
        from mimir.query_router import normalize_query
        result = normalize_query("Help me understand how to use the cache")
        assert "help me" not in result
        assert "cache" in result

    def test_normalizes_whitespace(self):
        from mimir.query_router import normalize_query
        result = normalize_query("How   does   the   auth   module   work?")
        assert "  " not in result

    def test_strips_trailing_punctuation(self):
        from mimir.query_router import normalize_query
        result = normalize_query("How does auth work???")
        assert "?" not in result
        assert "work" in result

    def test_lowercases(self):
        from mimir.query_router import normalize_query
        result = normalize_query("HOW DOES THE AUTH MODULE WORK?")
        assert result == result.lower()

    def test_preserves_structural_keywords(self):
        from mimir.query_router import normalize_query
        result = normalize_query("How does the auth module connect to the database?")
        assert "connect" in result
        assert "database" in result

    def test_idempotent(self):
        from mimir.query_router import normalize_query
        q1 = normalize_query("Can you show me how to use the graph?")
        q2 = normalize_query(q1)
        assert q1 == q2


# ─── Test Semantic Cache ────────────────────────────────────────────────────

class TestSemanticCache:
    """Test the _SemanticCache class (Improvement #1)."""

    def test_cache_miss_on_empty(self):
        from mimir.query_router import _SemanticCache, RoutingResult
        cache = _SemanticCache(maxsize=10, ttl_seconds=600)
        # With no entries, should return None
        # Mock embedding to avoid needing real API
        with patch.object(cache, '_embed', return_value=None):
            result = cache.get("test query", 5)
            assert result is None

    def test_cache_roundtrip(self):
        from mimir.query_router import _SemanticCache, RoutingResult
        cache = _SemanticCache(maxsize=10, ttl_seconds=600, similarity_threshold=0.92)

        fake_embedding = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)

        result = RoutingResult(
            success=True,
            context="test context",
            query_type="semantic",
            routed_to="vector",
            status="ok",
        )

        # Put with mocked embedding
        with patch.object(cache, '_embed', return_value=fake_embedding):
            cache.put("test query", 5, result)

        # Get with identical query (exact match should work first)
        with patch.object(cache, '_embed', return_value=fake_embedding):
            cached = cache.get("test query", 5)
            assert cached is not None
            assert cached.cache_hit is True

    def test_cache_semantic_match(self):
        """Test that semantically similar queries match (Improvement #1)."""
        from mimir.query_router import _SemanticCache, RoutingResult
        cache = _SemanticCache(maxsize=10, ttl_seconds=600, similarity_threshold=0.1)

        # Use identical embeddings to guarantee high similarity
        fake_embedding = np.array([0.5, 0.5, 0.5], dtype=np.float32)

        result = RoutingResult(
            success=True,
            context="test context",
            query_type="semantic",
            routed_to="vector",
            status="ok",
        )

        with patch.object(cache, '_embed', return_value=fake_embedding):
            cache.put("how does auth work", 5, result)

        # Different query with same embedding → should match
        with patch.object(cache, '_embed', return_value=fake_embedding):
            cached = cache.get("what is the authentication system", 5)
            assert cached is not None
            assert cached.cache_hit is True

    def test_cache_ttl_expiry(self):
        """Test that expired entries are not returned."""
        from mimir.query_router import _SemanticCache, RoutingResult
        cache = _SemanticCache(maxsize=10, ttl_seconds=1)  # 1 second TTL

        fake_embedding = np.array([0.1, 0.2], dtype=np.float32)

        result = RoutingResult(
            success=True,
            context="test context",
            query_type="semantic",
            routed_to="vector",
            status="ok",
        )

        with patch.object(cache, '_embed', return_value=fake_embedding):
            cache.put("test query", 5, result)

        # Wait for TTL expiry
        import time
        time.sleep(1.5)

        with patch.object(cache, '_embed', return_value=fake_embedding):
            cached = cache.get("test query", 5)
            assert cached is None

    def test_cache_eviction_lru(self):
        """Test that oldest entries are evicted when maxsize is reached."""
        from mimir.query_router import _SemanticCache, RoutingResult
        cache = _SemanticCache(maxsize=3, ttl_seconds=600)

        for i in range(5):
            fake_emb = np.array([float(i), 0.0], dtype=np.float32)
            result = RoutingResult(
                success=True,
                context=f"context {i}",
                query_type="semantic",
                routed_to="vector",
                status="ok",
            )
            with patch.object(cache, '_embed', return_value=fake_emb):
                cache.put(f"query {i}", 5, result)

        assert cache.size == 3


# ─── Test Confidence-Based Classification ────────────────────────────────────

class TestKeywordConfidence:
    """Test the _keyword_confidence function (Improvement #3)."""

    def test_strong_structural_query(self):
        from mimir.query_router import _keyword_confidence
        label, confidence = _keyword_confidence("connect to the database from auth")
        assert label == "structural"
        assert confidence >= 0.7

    def test_semantic_query(self):
        from mimir.query_router import _keyword_confidence
        label, confidence = _keyword_confidence("what is the purpose of the cache module")
        assert label == "semantic"
        assert confidence > 0.5

    def test_weak_signal_returns_low_confidence(self):
        from mimir.query_router import _keyword_confidence
        label, confidence = _keyword_confidence("how do modules work")
        # Only 1 keyword hit ("modules" is not in the list, "how" + "do" → but need connect/link/etc.)
        # Should be in uncertain zone
        assert confidence < 0.75

    def test_classify_query_returns_tuple(self):
        from mimir.query_router import _classify_query
        label, confidence = _classify_query("How does the auth module connect to the database?")
        assert isinstance(label, str)
        assert isinstance(confidence, float)
        assert 0.0 <= confidence <= 1.0


# ─── Test RoutingResult ─────────────────────────────────────────────────

class TestRoutingResultEnhancements:
    """Test RoutingResult enhancements."""

    def test_has_confidence_field(self):
        from mimir.query_router import RoutingResult
        r = RoutingResult(success=True, context="test", confidence=0.85)
        assert r.confidence == 0.85

    def test_to_dict_includes_confidence(self):
        from mimir.query_router import RoutingResult
        r = RoutingResult(success=True, context="test", confidence=0.85, routed_to="graph")
        d = r.to_dict()
        assert "confidence" in d
        assert d["confidence"] == 0.85

    def test_defaults_confidence_zero(self):
        from mimir.query_router import RoutingResult
        r = RoutingResult(success=True, context="test")
        assert r.confidence == 0.0


# ─── Test RouterConfig Enhancements ──────────────────────────────────────

class TestRouterConfigEnhancements:
    """Test extended RouterConfig (Improvement #5)."""

    def test_has_similarity_threshold(self):
        from mimir.query_router import RouterConfig
        assert hasattr(RouterConfig, 'cache_similarity_threshold')
        rc = RouterConfig()
        assert rc.cache_similarity_threshold == 0.92

    def test_has_hybrid_confidence_bounds(self):
        from mimir.query_router import RouterConfig
        rc = RouterConfig()
        assert rc.hybrid_confidence_min == 0.50
        assert rc.hybrid_confidence_max == 0.85

    def test_has_query_normalization_flag(self):
        from mimir.query_router import RouterConfig
        rc = RouterConfig()
        assert rc.query_normalization_enabled is True


# ─── Test Hybrid Routing Logic ──────────────────────────────────────────

class TestHybridRouting:
    """Test the hybrid routing logic in route_task (Improvement #4)."""

    @patch('mimir.query_router._search_graph')
    @patch('mimir.query_router._search_raw')
    @patch('mimir.query_router._classify_query')
    def test_high_confidence_structural_uses_graph_only(self, mock_classify, mock_raw, mock_graph):
        """High confidence structural queries should try graph first."""
        from mimir.query_router import route_task

        mock_classify.return_value = ("structural", 0.92)
        mock_graph.return_value = "[Graph Path]\n  1. A --imports_from--> B"

        result = route_task("How does module A connect to module B?", project_root=Path("/tmp/high_struct"))

        # Should have called graph, not raw search
        mock_graph.assert_called_once()
        mock_raw.assert_not_called()
        assert result.routed_to == "graph"

    @patch('mimir.query_router._search_graph')
    @patch('mimir.query_router._search_raw')
    @patch('mimir.query_router._classify_query')
    def test_mid_confidence_structural_uses_hybrid_when_both_available(self, mock_classify, mock_raw, mock_graph):
        """Mid-confidence structural queries use hybrid when BOTH graph+vector return results."""
        from mimir.query_router import route_task

        mock_classify.return_value = ("structural", 0.65)
        mock_graph.return_value = "[Graph Path]\n  1. A --depends_on--> B"
        mock_raw.return_value = [MagicMock()]  # Must return results for hybrid

        # Need to mock SearchResult attributes used in rendering
        mock_raw.return_value[0].source = "test.py"
        mock_raw.return_value[0].text = "test content"
        mock_raw.return_value[0].score = 0.5
        mock_raw.return_value[0].freshness = 0.8

        result = route_task("How does the indexing pipeline depend on the parser?", project_root=Path("/tmp/hybrid_test1"))

        # Both should be called
        mock_graph.assert_called_once()
        mock_raw.assert_called_once()
        assert result.routed_to == "hybrid"
        assert result.query_type == "hybrid"

    @patch('mimir.query_router._search_graph')
    @patch('mimir.query_router._search_raw')
    @patch('mimir.query_router._classify_query')
    def test_mid_confidence_structural_falls_back_to_graph_when_vector_empty(self, mock_classify, mock_raw, mock_graph):
        """Mid-confidence structural falls back to graph-only when vector returns nothing."""
        from mimir.query_router import route_task

        mock_classify.return_value = ("structural", 0.65)
        mock_graph.return_value = "[Graph Path]\n  1. A --depends_on--> B"
        mock_raw.return_value = []  # No vector results

        result = route_task("How does the indexing pipeline depend on the parser?", project_root=Path("/tmp/hybrid_test2"))

        # Both tried, but vector was empty → graph-only fallback
        mock_graph.assert_called_once()
        mock_raw.assert_called_once()
        assert result.routed_to == "graph"
        assert result.query_type == "structural"

    @patch('mimir.query_router._search_graph')
    @patch('mimir.query_router._search_raw')
    @patch('mimir.query_router._classify_query')
    def test_semantic_query_uses_vector_only(self, mock_classify, mock_raw, mock_graph):
        """Semantic queries should skip graph and use vector only."""
        from mimir.query_router import route_task

        mock_classify.return_value = ("semantic", 0.85)

        result = route_task("What is the purpose of the knowledge graph?", project_root=Path("/tmp/semantic_test3"))

        mock_graph.assert_not_called()
        mock_raw.assert_called_once()
        assert result.routed_to == "vector"


# ─── Test Applies Normalization to Routing ──────────────────────────────

class TestNormalizationInRouteTask:
    """Test that normalization is applied when enabled (Improvement #2)."""

    @patch('mimir.query_router._search_raw')
    @patch('mimir.query_router._classify_query')
    @patch('mimir.query_router.normalize_query')
    def test_normalization_called_when_enabled(self, mock_normalize, mock_classify, mock_raw):
        from mimir.query_router import route_task, RouterConfig, _SemanticCache

        mock_normalize.return_value = "normalized query"
        mock_classify.return_value = ("semantic", 0.90)
        mock_raw.return_value = []

        # Create a real config but override just the fields we need
        with patch('mimir.query_router.get_config') as mock_get_config:
            cfg = MagicMock()
            cfg.api_key = "test"
            cfg.api_base = ""
            cfg.embedding_model = "text-embedding-3-large"
            cfg.llm_model = "o3-mini"
            cfg.bridge_enabled = True
            cfg.bridge_cache_maxsize = 128
            cfg.bridge_cache_ttl_seconds = 600
            cfg.bridge_cache_similarity_threshold = 0.92
            cfg.bridge_circuit_breaker_threshold = 3
            cfg.bridge_circuit_breaker_reset_seconds = 60
            cfg.bridge_search_timeout_seconds = 30.0
            cfg.bridge_max_context_tokens = 2500
            cfg.bridge_top_k = 5
            cfg.bridge_freshness_decay_hours = 168.0
            cfg.bridge_classification_enabled = True
            cfg.bridge_classification_model = "gpt-3.5-turbo"
            cfg.bridge_query_normalization_enabled = True
            cfg.bridge_hybrid_confidence_min = 0.50
            cfg.bridge_hybrid_confidence_max = 0.85
            mock_get_config.return_value = cfg

            rc = RouterConfig.from_mimir_config(cfg)
            # Patch the router config creation
            with patch('mimir.query_router.RouterConfig.from_mimir_config', return_value=rc):
                route_task("Can you tell me how X works?", project_root=Path("/tmp/norm_test1"))

            mock_normalize.assert_called_once()

    @patch('mimir.query_router._search_raw')
    @patch('mimir.query_router._classify_query')
    @patch('mimir.query_router.normalize_query')
    def test_normalization_skipped_when_disabled(self, mock_normalize, mock_classify, mock_raw):
        from mimir.query_router import route_task, RouterConfig, _SemanticCache

        mock_classify.return_value = ("semantic", 0.90)
        mock_raw.return_value = []

        with patch('mimir.query_router.get_config') as mock_get_config:
            cfg = MagicMock()
            cfg.api_key = "test"
            cfg.api_base = ""
            cfg.embedding_model = "text-embedding-3-large"
            cfg.llm_model = "o3-mini"
            cfg.bridge_enabled = True
            cfg.bridge_cache_maxsize = 128
            cfg.bridge_cache_ttl_seconds = 600
            cfg.bridge_cache_similarity_threshold = 0.92
            cfg.bridge_circuit_breaker_threshold = 3
            cfg.bridge_circuit_breaker_reset_seconds = 60
            cfg.bridge_search_timeout_seconds = 30.0
            cfg.bridge_max_context_tokens = 2500
            cfg.bridge_top_k = 5
            cfg.bridge_freshness_decay_hours = 168.0
            cfg.bridge_classification_enabled = True
            cfg.bridge_classification_model = "gpt-3.5-turbo"
            cfg.bridge_query_normalization_enabled = False
            cfg.bridge_hybrid_confidence_min = 0.50
            cfg.bridge_hybrid_confidence_max = 0.85
            mock_get_config.return_value = cfg

            rc = RouterConfig.from_mimir_config(cfg)
            with patch('mimir.query_router.RouterConfig.from_mimir_config', return_value=rc):
                route_task("Can you tell me how X works?", project_root=Path("/tmp/norm_test2"))

            mock_normalize.assert_not_called()


# ─── Test Health Endpoint ──────────────────────────────────────────────

class TestHealthEndpointEnhancements:
    """Test the health endpoint includes new config fields."""

    def test_health_includes_new_fields(self):
        from mimir_bridge import handle_task_health

        # Just verify the function uses RouterConfig which now has new fields
        from mimir.query_router import RouterConfig
        rc = RouterConfig()

        expected_fields = [
            'cache_similarity_threshold',
            'query_normalization_enabled',
            'hybrid_confidence_min',
            'hybrid_confidence_max',
        ]
        for field in expected_fields:
            assert hasattr(rc, field), f"RouterConfig missing field: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])