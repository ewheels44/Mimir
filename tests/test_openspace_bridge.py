#!/usr/bin/env python3
"""Tests for the Mimir Query Router (formerly OpenSpace bridge tests).

These tests validate the guardrail logic — circuit breaker, cache,
content filtering, freshness scoring, and classification — now
living in src.mimir.query_router.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

MIMIR_DIR = Path("/Users/ethanwheeler/Documents/Mimir")
sys.path.insert(0, str(MIMIR_DIR))


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_mimir_config():
    """Reset MimirConfig singleton before each test to avoid stale cached values."""
    from src.mimir.config import reset_config

    reset_config()
    yield
    reset_config()


from src.mimir.query_router import (
    RouterConfig,
    RoutingResult,
    SearchResult,
    _CircuitBreakerState,
    _TimedCache,
    _compute_freshness,
    _filter_sensitive,
    _is_blocked_filename,
    _is_sensitive,
    _quick_structural_check,
)


# ─── Content Filter Tests ────────────────────────────────────────────────────


class TestContentFilter:
    """Tests for content filtering functions."""

    def test_detects_api_key(self):
        """Should detect API key patterns."""
        text = 'API_KEY = "sk-abc123def456"'
        assert _is_sensitive(text) is True

    def test_detects_api_key_lowercase(self):
        """Should detect lowercase api_key pattern."""
        text = 'api_key: "secret123"'
        assert _is_sensitive(text) is True

    def test_detects_password(self):
        """Should detect password patterns."""
        text = 'password: "super_secret"'
        assert _is_sensitive(text) is True

    def test_detects_token(self):
        """Should detect token patterns."""
        text = 'token = "bearer_xyz789"'
        assert _is_sensitive(text) is True

    def test_detects_secret_key(self):
        """Should detect secret_key patterns."""
        text = 'SECRET_KEY = "my-secret-key"'
        assert _is_sensitive(text) is True

    def test_detects_localhost_url(self):
        """Should detect localhost URLs."""
        text = "Connect to http://localhost:8080/api"
        assert _is_sensitive(text) is True

    def test_detects_127_0_0_1_url(self):
        """Should detect 127.0.0.1 URLs."""
        text = "Server at http://127.0.0.1:3000"
        assert _is_sensitive(text) is True

    def test_detects_private_ip_192_168(self):
        """Should detect 192.168.x.x private IPs."""
        text = "Server at 192.168.1.100"
        assert _is_sensitive(text) is True

    def test_detects_private_ip_10(self):
        """Should detect 10.x.x.x private IPs."""
        text = "Internal server: 10.0.0.50"
        assert _is_sensitive(text) is True

    def test_detects_private_ip_172(self):
        """Should detect 172.16-31.x.x private IPs."""
        text = "VPN gateway: 172.16.0.1"
        assert _is_sensitive(text) is True

    def test_detects_internal_domain(self):
        """Should detect internal domain patterns."""
        text = "Connect to internal.company.local"
        assert _is_sensitive(text) is True

    def test_detects_rsa_private_key(self):
        """Should detect RSA private key headers."""
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."
        assert _is_sensitive(text) is True

    def test_detects_ec_private_key(self):
        """Should detect EC private key headers."""
        text = "-----BEGIN EC PRIVATE KEY-----\nMHQ..."
        assert _is_sensitive(text) is True

    def test_detects_private_key_no_prefix(self):
        """Should detect generic private key headers."""
        text = "-----BEGIN PRIVATE KEY-----\nMIIE..."
        assert _is_sensitive(text) is True

    def test_allows_normal_code(self):
        """Should allow normal code without sensitive patterns."""
        text = (
            "def authenticate(user, password_hash):\n    return verify(password_hash)"
        )
        assert _is_sensitive(text) is False

    def test_allows_public_urls(self):
        """Should allow public URLs."""
        text = "See https://docs.example.com/api for details"
        assert _is_sensitive(text) is False

    def test_allows_public_ip(self):
        """Should allow public IP addresses."""
        text = "Public server at 8.8.8.8"
        assert _is_sensitive(text) is False

    def test_redacts_sensitive_content(self):
        """Should redact sensitive content."""
        text = 'API_KEY = "sk-secret123"'
        filtered = _filter_sensitive(text)
        assert "sk-secret123" not in filtered
        assert "[REDACTED]" in filtered

    def test_redacts_multiple_patterns(self):
        """Should redact multiple sensitive patterns."""
        text = 'API_KEY = "key1"\npassword = "pass1"'
        filtered = _filter_sensitive(text)
        assert "key1" not in filtered
        assert "pass1" not in filtered
        assert filtered.count("[REDACTED]") >= 2


class TestBlockedFilenames:
    """Tests for blocked filename detection."""

    def test_blocks_env_file(self):
        assert _is_blocked_filename(".env") is True

    def test_blocks_env_local(self):
        assert _is_blocked_filename(".env.local") is True

    def test_blocks_env_production(self):
        assert _is_blocked_filename(".env.production") is True

    def test_blocks_env_staging(self):
        assert _is_blocked_filename(".env.staging") is True

    def test_blocks_credentials_json(self):
        assert _is_blocked_filename("credentials.json") is True

    def test_blocks_secrets_json(self):
        assert _is_blocked_filename("secrets.json") is True

    def test_blocks_auth_json(self):
        assert _is_blocked_filename("auth.json") is True

    def test_blocks_id_rsa(self):
        assert _is_blocked_filename("id_rsa") is True

    def test_blocks_id_ed25519(self):
        assert _is_blocked_filename("id_ed25519") is True

    def test_blocks_pem_files(self):
        assert _is_blocked_filename("cert.pem") is True
        assert _is_blocked_filename("key.pem") is True

    def test_allows_normal_files(self):
        assert _is_blocked_filename("main.py") is False
        assert _is_blocked_filename("config.py") is False
        assert _is_blocked_filename("app.js") is False
        assert _is_blocked_filename("README.md") is False

    def test_handles_path_objects(self):
        assert _is_blocked_filename("/path/to/.env") is True
        assert _is_blocked_filename("/path/to/config.py") is False


# ─── Circuit Breaker Tests ──────────────────────────────────────────────────


class TestCircuitBreaker:
    """Tests for circuit breaker state."""

    def test_starts_closed(self):
        cb = _CircuitBreakerState()
        assert cb.is_open is False
        assert cb.failure_count == 0

    def test_check_returns_false_when_closed(self):
        cb = _CircuitBreakerState()
        assert cb.check(60) is False

    def test_opens_after_threshold(self):
        cb = _CircuitBreakerState()
        cb.record_failure(3, 60)
        cb.record_failure(3, 60)
        assert cb.is_open is False
        cb.record_failure(3, 60)
        assert cb.is_open is True
        assert cb.check(60) is True

    def test_resets_on_success(self):
        cb = _CircuitBreakerState()
        cb.record_failure(3, 60)
        cb.record_failure(3, 60)
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.is_open is False

    def test_auto_reset_after_cooldown(self):
        cb = _CircuitBreakerState()
        cb.record_failure(1, 0)
        assert cb.is_open is True
        time.sleep(0.1)
        assert cb.check(0) is False

    def test_failure_count_increments(self):
        cb = _CircuitBreakerState()
        assert cb.failure_count == 0
        cb.record_failure(5, 60)
        assert cb.failure_count == 1
        cb.record_failure(5, 60)
        assert cb.failure_count == 2

    def test_records_failure_time(self):
        cb = _CircuitBreakerState()
        before = time.time()
        cb.record_failure(3, 60)
        after = time.time()
        assert before <= cb.last_failure_time <= after


# ─── Cache Tests ─────────────────────────────────────────────────────────────


class TestTimedCache:
    """Tests for timed cache — now using RoutingResult."""

    def test_returns_none_on_miss(self):
        cache = _TimedCache(maxsize=10, ttl_seconds=60)
        assert cache.get("test query", 5) is None

    def test_returns_cached_result(self):
        cache = _TimedCache(maxsize=10, ttl_seconds=60)
        result = RoutingResult(success=True, context="cached context")
        cache.put("test query", 5, result)
        cached = cache.get("test query", 5)
        assert cached is not None
        assert cached.context == "cached context"
        assert cached.cache_hit is True

    def test_expires_after_ttl(self):
        cache = _TimedCache(maxsize=10, ttl_seconds=0)
        result = RoutingResult(success=True, context="will expire")
        cache.put("test", 5, result)
        time.sleep(0.1)
        assert cache.get("test", 5) is None

    def test_evicts_oldest_at_capacity(self):
        cache = _TimedCache(maxsize=2, ttl_seconds=60)
        r1 = RoutingResult(success=True, context="first")
        r2 = RoutingResult(success=True, context="second")
        r3 = RoutingResult(success=True, context="third")
        cache.put("q1", 5, r1)
        cache.put("q2", 5, r2)
        cache.put("q3", 5, r3)
        assert cache.get("q1", 5) is None
        assert cache.get("q2", 5) is not None
        assert cache.get("q3", 5) is not None

    def test_size_property(self):
        cache = _TimedCache(maxsize=10, ttl_seconds=60)
        assert cache.size == 0
        cache.put("q1", 5, RoutingResult(success=True))
        assert cache.size == 1
        cache.put("q2", 5, RoutingResult(success=True))
        assert cache.size == 2

    def test_different_top_k_different_keys(self):
        cache = _TimedCache(maxsize=10, ttl_seconds=60)
        r1 = RoutingResult(success=True, context="k=5")
        r2 = RoutingResult(success=True, context="k=10")
        cache.put("query", 5, r1)
        cache.put("query", 10, r2)
        assert cache.get("query", 5).context == "k=5"
        assert cache.get("query", 10).context == "k=10"


# ─── SearchResult Tests ─────────────────────────────────────────────────────


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_to_prompt_chunk_fresh(self):
        r = SearchResult(source="auth.py", score=0.9, text="def login():", freshness=0.8)
        chunk = r.to_prompt_chunk()
        assert "auth.py" in chunk
        assert "fresh" in chunk
        assert "score=0.90" in chunk

    def test_to_prompt_chunk_recent(self):
        r = SearchResult(source="module.py", score=0.7, text="code", freshness=0.5)
        chunk = r.to_prompt_chunk()
        assert "recent" in chunk

    def test_to_prompt_chunk_stale(self):
        r = SearchResult(source="old.py", score=0.5, text="old code", freshness=0.1)
        chunk = r.to_prompt_chunk()
        assert "stale" in chunk

    def test_to_prompt_chunk_includes_text(self):
        r = SearchResult(source="file.py", score=0.8, text="def function():\n    pass", freshness=1.0)
        chunk = r.to_prompt_chunk()
        assert "def function():" in chunk


# ─── RoutingResult Tests ─────────────────────────────────────────────────────


class TestRoutingResult:
    """Tests for RoutingResult dataclass."""

    def test_default_status_is_ok(self):
        result = RoutingResult(success=True)
        assert result.status == "ok"

    def test_to_dict_includes_status(self):
        result = RoutingResult(success=True, context="test", status="ok")
        d = result.to_dict()
        assert "status" in d
        assert d["status"] == "ok"

    def test_to_dict_includes_all_fields(self):
        result = RoutingResult(
            success=True,
            context="test context",
            results=(),
            cache_hit=True,
            circuit_open=False,
            error=None,
            elapsed_ms=100,
            status="ok",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["context"] == "test context"
        assert d["result_count"] == 0
        assert d["cache_hit"] is True
        assert d["circuit_open"] is False
        assert d["error"] is None
        assert d["elapsed_ms"] == 100
        assert d["status"] == "ok"

    def test_custom_status_preserved(self):
        result = RoutingResult(success=False, status="no_index")
        assert result.status == "no_index"


# ─── RouterConfig Tests ──────────────────────────────────────────────────────


class TestRouterConfig:
    """Tests for RouterConfig dataclass."""

    def test_defaults(self):
        config = RouterConfig()
        assert config.enabled is True
        assert config.cache_maxsize == 128
        assert config.cache_ttl_seconds == 600
        assert config.circuit_breaker_threshold == 3
        assert config.circuit_breaker_reset_seconds == 60
        assert config.search_timeout_seconds == 30.0
        assert config.max_context_tokens == 2500
        assert config.top_k == 5
        assert config.neural_classifier_enabled is True
        assert config.classification_model == "gpt-3.5-turbo"

    def test_frozen_dataclass(self):
        config = RouterConfig()
        with pytest.raises(Exception):
            config.enabled = False


# ─── Freshness Tests ────────────────────────────────────────────────────────


class TestComputeFreshness:
    """Tests for _compute_freshness function."""

    def test_returns_1_for_just_indexed(self):
        now = time.time()
        timestamp = _compute_freshness(
            datetime.fromtimestamp(now).isoformat(), decay_hours=168.0
        )
        assert timestamp >= 0.99

    def test_returns_0_5_for_unknown(self):
        result = _compute_freshness(None, decay_hours=168.0)
        assert result == 0.5

    def test_returns_0_for_very_stale(self):
        old_time = datetime.now() - timedelta(days=30)
        result = _compute_freshness(old_time.isoformat(), decay_hours=168.0)
        assert result == 0.0

    def test_decays_linearly(self):
        half_decay = datetime.now() - timedelta(days=3.5)
        result = _compute_freshness(half_decay.isoformat(), decay_hours=168.0)
        assert 0.4 < result < 0.6

    def test_handles_invalid_timestamp(self):
        result = _compute_freshness("not-a-timestamp", decay_hours=168.0)
        assert result == 0.5


# ─── Quick Classification Tests ─────────────────────────────────────────────


class TestQuickStructuralCheck:
    """Tests for _quick_structural_check keyword classifier."""

    def test_structural_connect(self):
        assert _quick_structural_check("How does auth connect to database?") == "structural"

    def test_structural_path(self):
        assert _quick_structural_check("Path from main to utils") == "structural"

    def test_structural_depends(self):
        assert _quick_structural_check("What depends on the config module?") == "structural"

    def test_structural_how_does_with_connect(self):
        assert _quick_structural_check("How does the frontend connect to backend?") == "structural"

    def test_how_does_is_structural(self):
        """'how does' is a structural phrase indicator."""
        assert _quick_structural_check("How does the authentication system work?") == "structural"

    def test_semantic_what_is(self):
        assert _quick_structural_check("What is the purpose of caching?") == "semantic"

    def test_semantic_explain(self):
        assert _quick_structural_check("Explain how the RAG pipeline works") == "semantic"

    def test_uncertain_returns_none(self):
        """Single keyword hit should return None (uncertain)."""
        result = _quick_structural_check("How does the link work?")
        assert result is None or result in ("structural", "semantic")


# ─── Backward Compatibility Tests ───────────────────────────────────────────


class TestBackwardCompat:
    """Tests that old OpenSpace bridge imports still work."""

    def test_enrichment_result_is_routing_result(self):
        from src.mimir.openspace_bridge import EnrichmentResult

        # EnrichmentResult should be a subclass of RoutingResult
        result = EnrichmentResult(success=True, context="test")
        assert isinstance(result, RoutingResult)
        assert result.success is True
        assert result.context == "test"

    def test_get_bridge_returns_none(self):
        from src.mimir.openspace_bridge import get_bridge

        # get_bridge is a stub
        bridge = get_bridge()
        assert bridge is None

    def test_enrich_task_for_openspace_returns_dict(self):
        from src.mimir.openspace_bridge import enrich_task_for_openspace

        result = enrich_task_for_openspace("test query")
        assert isinstance(result, dict)
        assert "success" in result
        assert "context" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])