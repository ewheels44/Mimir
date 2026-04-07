#!/usr/bin/env python3
"""Tests for the Mimir ↔ OpenSpace bridge adapter."""

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

from src.mimir.openspace_bridge import (
    BridgeConfig,
    EnrichmentResult,
    MimirOpenSpaceBridge,
    SearchResult,
    _CircuitBreakerState,
    _TimedCache,
    _compute_freshness,
    _filter_sensitive,
    _is_blocked_filename,
    _is_sensitive,
    _resolve_api_key_from_env,
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
        """Should block .env files."""
        assert _is_blocked_filename(".env") is True

    def test_blocks_env_local(self):
        """Should block .env.local files."""
        assert _is_blocked_filename(".env.local") is True

    def test_blocks_env_production(self):
        """Should block .env.production files."""
        assert _is_blocked_filename(".env.production") is True

    def test_blocks_env_staging(self):
        """Should block .env.staging files."""
        assert _is_blocked_filename(".env.staging") is True

    def test_blocks_credentials_json(self):
        """Should block credentials.json files."""
        assert _is_blocked_filename("credentials.json") is True

    def test_blocks_secrets_json(self):
        """Should block secrets.json files."""
        assert _is_blocked_filename("secrets.json") is True

    def test_blocks_auth_json(self):
        """Should block auth.json files."""
        assert _is_blocked_filename("auth.json") is True

    def test_blocks_id_rsa(self):
        """Should block id_rsa files."""
        assert _is_blocked_filename("id_rsa") is True

    def test_blocks_id_ed25519(self):
        """Should block id_ed25519 files."""
        assert _is_blocked_filename("id_ed25519") is True

    def test_blocks_pem_files(self):
        """Should block .pem files."""
        assert _is_blocked_filename("cert.pem") is True
        assert _is_blocked_filename("key.pem") is True

    def test_allows_normal_files(self):
        """Should allow normal files."""
        assert _is_blocked_filename("main.py") is False
        assert _is_blocked_filename("config.py") is False
        assert _is_blocked_filename("app.js") is False
        assert _is_blocked_filename("README.md") is False

    def test_handles_path_objects(self):
        """Should handle Path objects."""
        assert _is_blocked_filename("/path/to/.env") is True
        assert _is_blocked_filename("/path/to/config.py") is False


# ─── Circuit Breaker Tests ──────────────────────────────────────────────────


class TestCircuitBreaker:
    """Tests for circuit breaker state."""

    def test_starts_closed(self):
        """Should start in closed state."""
        cb = _CircuitBreakerState()
        assert cb.is_open is False
        assert cb.failure_count == 0

    def test_check_returns_false_when_closed(self):
        """Should return False when circuit is closed."""
        cb = _CircuitBreakerState()
        assert cb.check(60) is False

    def test_opens_after_threshold(self):
        """Should open after reaching threshold."""
        cb = _CircuitBreakerState()
        cb.record_failure(3, 60)
        cb.record_failure(3, 60)
        assert cb.is_open is False
        cb.record_failure(3, 60)
        assert cb.is_open is True
        assert cb.check(60) is True

    def test_resets_on_success(self):
        """Should reset on success."""
        cb = _CircuitBreakerState()
        cb.record_failure(3, 60)
        cb.record_failure(3, 60)
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.is_open is False

    def test_auto_reset_after_cooldown(self):
        """Should auto-reset after cooldown period."""
        cb = _CircuitBreakerState()
        cb.record_failure(1, 0)  # threshold=1, reset=0s
        assert cb.is_open is True
        time.sleep(0.1)
        assert cb.check(0) is False  # Should auto-reset

    def test_failure_count_increments(self):
        """Should increment failure count."""
        cb = _CircuitBreakerState()
        assert cb.failure_count == 0
        cb.record_failure(5, 60)
        assert cb.failure_count == 1
        cb.record_failure(5, 60)
        assert cb.failure_count == 2

    def test_records_failure_time(self):
        """Should record last failure time."""
        cb = _CircuitBreakerState()
        before = time.time()
        cb.record_failure(3, 60)
        after = time.time()
        assert before <= cb.last_failure_time <= after


# ─── Cache Tests ─────────────────────────────────────────────────────────────


class TestTimedCache:
    """Tests for timed cache."""

    def test_returns_none_on_miss(self):
        """Should return None when key not in cache."""
        cache = _TimedCache(maxsize=10, ttl_seconds=60)
        assert cache.get("test query", 5) is None

    def test_returns_cached_result(self):
        """Should return cached result on hit."""
        cache = _TimedCache(maxsize=10, ttl_seconds=60)
        result = EnrichmentResult(success=True, context="cached context")
        cache.put("test query", 5, result)
        cached = cache.get("test query", 5)
        assert cached is not None
        assert cached.context == "cached context"
        assert cached.cache_hit is True

    def test_expires_after_ttl(self):
        """Should expire entries after TTL."""
        cache = _TimedCache(maxsize=10, ttl_seconds=0)
        result = EnrichmentResult(success=True, context="will expire")
        cache.put("test", 5, result)
        time.sleep(0.1)
        assert cache.get("test", 5) is None

    def test_evicts_oldest_at_capacity(self):
        """Should evict oldest entry when at capacity."""
        cache = _TimedCache(maxsize=2, ttl_seconds=60)
        r1 = EnrichmentResult(success=True, context="first")
        r2 = EnrichmentResult(success=True, context="second")
        r3 = EnrichmentResult(success=True, context="third")
        cache.put("q1", 5, r1)
        cache.put("q2", 5, r2)
        cache.put("q3", 5, r3)  # Should evict q1
        assert cache.get("q1", 5) is None
        assert cache.get("q2", 5) is not None
        assert cache.get("q3", 5) is not None

    def test_size_property(self):
        """Should report correct size."""
        cache = _TimedCache(maxsize=10, ttl_seconds=60)
        assert cache.size == 0
        cache.put("q1", 5, EnrichmentResult(success=True))
        assert cache.size == 1
        cache.put("q2", 5, EnrichmentResult(success=True))
        assert cache.size == 2

    def test_different_top_k_different_keys(self):
        """Should create different keys for different top_k values."""
        cache = _TimedCache(maxsize=10, ttl_seconds=60)
        r1 = EnrichmentResult(success=True, context="k=5")
        r2 = EnrichmentResult(success=True, context="k=10")
        cache.put("query", 5, r1)
        cache.put("query", 10, r2)
        assert cache.get("query", 5).context == "k=5"
        assert cache.get("query", 10).context == "k=10"


# ─── SearchResult Tests ─────────────────────────────────────────────────────


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_to_prompt_chunk_fresh(self):
        """Should format fresh results correctly."""
        r = SearchResult(
            source="auth.py", score=0.9, text="def login():", freshness=0.8
        )
        chunk = r.to_prompt_chunk()
        assert "auth.py" in chunk
        assert "fresh" in chunk
        assert "score=0.90" in chunk

    def test_to_prompt_chunk_recent(self):
        """Should format recent results correctly."""
        r = SearchResult(source="module.py", score=0.7, text="code", freshness=0.5)
        chunk = r.to_prompt_chunk()
        assert "recent" in chunk

    def test_to_prompt_chunk_stale(self):
        """Should format stale results correctly."""
        r = SearchResult(source="old.py", score=0.5, text="old code", freshness=0.1)
        chunk = r.to_prompt_chunk()
        assert "stale" in chunk

    def test_to_prompt_chunk_includes_text(self):
        """Should include text content in chunk."""
        r = SearchResult(
            source="file.py", score=0.8, text="def function():\n    pass", freshness=1.0
        )
        chunk = r.to_prompt_chunk()
        assert "def function():" in chunk


# ─── EnrichmentResult Tests ─────────────────────────────────────────────────


class TestEnrichmentResult:
    """Tests for EnrichmentResult dataclass."""

    def test_default_status_is_ok(self):
        """Should default status to 'ok'."""
        result = EnrichmentResult(success=True)
        assert result.status == "ok"

    def test_to_dict_includes_status(self):
        """Should include status in dict output."""
        result = EnrichmentResult(success=True, context="test", status="ok")
        d = result.to_dict()
        assert "status" in d
        assert d["status"] == "ok"

    def test_to_dict_includes_all_fields(self):
        """Should include all expected fields."""
        result = EnrichmentResult(
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
        """Should preserve custom status values."""
        result = EnrichmentResult(success=False, status="no_index")
        assert result.status == "no_index"


# ─── Bridge Config Tests ────────────────────────────────────────────────────


class TestBridgeConfig:
    """Tests for BridgeConfig dataclass."""

    def test_defaults(self):
        """Should have sensible defaults."""
        config = BridgeConfig()
        assert config.enabled is True
        assert config.cache_maxsize == 128
        assert config.cache_ttl_seconds == 600
        assert config.circuit_breaker_threshold == 3
        assert config.circuit_breaker_reset_seconds == 60
        assert config.search_timeout_seconds == 30.0
        assert config.max_context_tokens == 2500
        assert config.top_k == 5

    def test_from_env_enabled(self, monkeypatch):
        """Should read enabled from env."""
        monkeypatch.setenv("MIMIR_OPENSPACE_ENABLED", "false")
        config = BridgeConfig.from_env()
        assert config.enabled is False

    def test_from_env_cache_size(self, monkeypatch):
        """Should read cache size from env."""
        monkeypatch.setenv("MIMIR_BRIDGE_CACHE_SIZE", "256")
        config = BridgeConfig.from_env()
        assert config.cache_maxsize == 256

    def test_from_env_cache_ttl(self, monkeypatch):
        """Should read cache TTL from env."""
        monkeypatch.setenv("MIMIR_BRIDGE_CACHE_TTL", "300")
        config = BridgeConfig.from_env()
        assert config.cache_ttl_seconds == 300

    def test_from_env_circuit_breaker_threshold(self, monkeypatch):
        """Should read circuit breaker threshold from env."""
        monkeypatch.setenv("MIMIR_BRIDGE_CB_THRESHOLD", "5")
        config = BridgeConfig.from_env()
        assert config.circuit_breaker_threshold == 5

    def test_from_env_circuit_breaker_reset(self, monkeypatch):
        """Should read circuit breaker reset from env."""
        monkeypatch.setenv("MIMIR_BRIDGE_CB_RESET", "120")
        config = BridgeConfig.from_env()
        assert config.circuit_breaker_reset_seconds == 120

    def test_from_env_timeout(self, monkeypatch):
        """Should read timeout from env."""
        monkeypatch.setenv("MIMIR_BRIDGE_TIMEOUT", "45.5")
        config = BridgeConfig.from_env()
        assert config.search_timeout_seconds == 45.5

    def test_from_env_max_tokens(self, monkeypatch):
        """Should read max tokens from env."""
        monkeypatch.setenv("MIMIR_BRIDGE_MAX_TOKENS", "3000")
        config = BridgeConfig.from_env()
        assert config.max_context_tokens == 3000

    def test_from_env_top_k(self, monkeypatch):
        """Should read top_k from env."""
        monkeypatch.setenv("MIMIR_BRIDGE_TOP_K", "10")
        config = BridgeConfig.from_env()
        assert config.top_k == 10

    def test_frozen_dataclass(self):
        """Should be immutable."""
        config = BridgeConfig()
        with pytest.raises(Exception):  # FrozenInstanceError
            config.enabled = False


# ─── Freshness Tests ────────────────────────────────────────────────────────


class TestComputeFreshness:
    """Tests for _compute_freshness function."""

    def test_returns_1_for_just_indexed(self):
        """Should return 1.0 for just-indexed content."""
        now = time.time()
        timestamp = _compute_freshness(
            datetime.fromtimestamp(now).isoformat(), decay_hours=168.0
        )
        assert timestamp >= 0.99

    def test_returns_0_5_for_unknown(self):
        """Should return 0.5 when no timestamp provided."""
        result = _compute_freshness(None, decay_hours=168.0)
        assert result == 0.5

    def test_returns_0_for_very_stale(self):
        """Should return 0.0 for very old content."""
        old_time = datetime.now() - timedelta(days=30)
        result = _compute_freshness(old_time.isoformat(), decay_hours=168.0)
        assert result == 0.0

    def test_decays_linearly(self):
        """Should decay linearly over time."""
        half_decay = datetime.now() - timedelta(days=3.5)  # Half of 7 days
        result = _compute_freshness(half_decay.isoformat(), decay_hours=168.0)
        assert 0.4 < result < 0.6

    def test_handles_invalid_timestamp(self):
        """Should return 0.5 for invalid timestamp."""
        result = _compute_freshness("not-a-timestamp", decay_hours=168.0)
        assert result == 0.5


# ─── API Key Resolution Tests ───────────────────────────────────────────────


class TestResolveApiKeyFromEnv:
    """Tests for _resolve_api_key_from_env function."""

    def test_returns_openrouter_key(self, monkeypatch):
        """Should return OPENROUTER_API_KEY when set."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        key, base = _resolve_api_key_from_env()
        assert key == "sk-or-test"
        assert base == "https://openrouter.ai/api/v1"

    def test_returns_openai_key(self, monkeypatch):
        """Should return OPENAI_API_KEY when OPENROUTER not set."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-test")
        key, base = _resolve_api_key_from_env()
        assert key == "sk-oai-test"

    def test_openrouter_takes_precedence(self, monkeypatch):
        """OPENROUTER_API_KEY should take precedence."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-first")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai-second")
        key, _ = _resolve_api_key_from_env()
        assert key == "sk-or-first"

    def test_custom_base_url(self, monkeypatch):
        """Should use OPENAI_BASE_URL when set."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.api/v1")
        key, base = _resolve_api_key_from_env()
        assert base == "https://custom.api/v1"

    def test_reads_from_auth_file(self, monkeypatch, tmp_path: Path):
        """Should read from opencode auth file."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        auth_dir = tmp_path / ".local" / "share" / "opencode"
        auth_dir.mkdir(parents=True)
        auth_file = auth_dir / "auth.json"
        auth_file.write_text('{"openrouter": {"key": "sk-file-key"}}')

        with patch("src.mimir.openspace_bridge.Path.home", return_value=tmp_path):
            key, base = _resolve_api_key_from_env()

        assert key == "sk-file-key"
        assert base == "https://openrouter.ai/api/v1"

    def test_returns_empty_when_no_key(self, monkeypatch, tmp_path: Path):
        """Should return empty string when no key found."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with patch("src.mimir.openspace_bridge.Path.home", return_value=tmp_path):
            key, base = _resolve_api_key_from_env()

        assert key == ""
        assert base is None


# ─── Bridge Integration Tests ───────────────────────────────────────────────


class TestBridge:
    """Tests for MimirOpenSpaceBridge."""

    def test_disabled_returns_error(self):
        """Should return error when disabled."""
        config = BridgeConfig(enabled=False)
        bridge = MimirOpenSpaceBridge(project_root=MIMIR_DIR, config=config)
        result = bridge.enrich_task("test task")
        assert result.success is False
        assert result.status == "disabled"
        assert "disabled" in result.error.lower()

    def test_circuit_open_returns_error(self):
        """Should return error when circuit is open."""
        config = BridgeConfig(circuit_breaker_threshold=1)
        bridge = MimirOpenSpaceBridge(project_root=MIMIR_DIR, config=config)
        # Trigger circuit open
        bridge._circuit.record_failure(1, 60)
        result = bridge.enrich_task("test task")
        assert result.success is False
        assert result.status == "circuit_open"
        assert result.circuit_open is True

    def test_health_check_returns_structure(self):
        """Should return health check structure."""
        bridge = MimirOpenSpaceBridge(project_root=MIMIR_DIR)
        health = bridge.health_check()
        assert "enabled" in health
        assert "circuit_open" in health
        assert "has_index" in health
        assert "project_root" in health

    def test_get_stats_includes_config(self):
        """Should include config in stats."""
        bridge = MimirOpenSpaceBridge(project_root=MIMIR_DIR)
        stats = bridge.get_stats()
        assert "config" in stats
        assert "cache_maxsize" in stats["config"]

    def test_is_enabled_property(self):
        """Should reflect enabled state."""
        config = BridgeConfig(enabled=True)
        bridge = MimirOpenSpaceBridge(project_root=MIMIR_DIR, config=config)
        assert bridge.is_enabled is True

        config = BridgeConfig(enabled=False)
        bridge = MimirOpenSpaceBridge(project_root=MIMIR_DIR, config=config)
        assert bridge.is_enabled is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
