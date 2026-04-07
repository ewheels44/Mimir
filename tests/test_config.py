"""Comprehensive tests for Mimir configuration module.

Tests cover:
- MimirConfig.load() basics
- Project root detection
- API key resolution
- Config file loading
- Directory resolution
- Model configuration
- Bridge settings
- validate()
- to_dict()
- Singleton behavior
- DEFAULTS dict
"""

import json
import os
from pathlib import Path

import pytest

from src.mimir.config import (
    DEFAULTS,
    MimirConfig,
    get_config,
    reset_config,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before and after each test to avoid pollution."""
    reset_config()
    yield
    reset_config()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Remove all Mimir-related env vars."""
    env_vars_to_clear = [
        "OPENROUTER_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "PROJECT_ROOT",
        "WORKSPACE_FOLDER",
        "VSCODE_CWD",
        "MIMIR_ROOT",
        "DOCS_DIR",
        "KNOWLEDGE_DIR",
        "CODE_DIRS",
        "EMBEDDING_MODEL",
        "MIMIR_LLM_MODEL",
        "MIMIR_SDK_CACHE_TTL",
        "MIMIR_OPENSPACE_ENABLED",
        "MIMIR_BRIDGE_CACHE_SIZE",
        "MIMIR_BRIDGE_CACHE_TTL",
        "MIMIR_BRIDGE_CB_THRESHOLD",
        "MIMIR_BRIDGE_CB_RESET",
        "MIMIR_BRIDGE_TIMEOUT",
        "MIMIR_BRIDGE_MAX_TOKENS",
        "MIMIR_BRIDGE_TOP_K",
    ]
    for var in env_vars_to_clear:
        monkeypatch.delenv(var, raising=False)


# ─── 1. MimirConfig.load() basics ────────────────────────────────────────────


def test_load_returns_mimir_config_instance(clean_env, tmp_path):
    """Test that load() returns a MimirConfig instance."""
    # Arrange - Create a project with .git marker
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert isinstance(config, MimirConfig)


def test_load_project_root_is_path(clean_env, tmp_path):
    """Test that project_root is a Path instance."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert isinstance(config.project_root, Path)


def test_load_mimir_root_is_path(clean_env, tmp_path):
    """Test that mimir_root is a Path instance."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert isinstance(config.mimir_root, Path)


def test_load_default_values_match_defaults_dict(clean_env, tmp_path):
    """Test that default values match DEFAULTS dict."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert - Check key defaults
    assert config.embedding_model == DEFAULTS["embedding_model"]
    assert config.llm_model == DEFAULTS["llm_model"]
    assert config.docs_dir == project / DEFAULTS["docs_dir"]
    assert config.knowledge_dir == project / DEFAULTS["knowledge_dir"]
    assert config.sdk_cache_ttl_days == DEFAULTS["sdk_cache_ttl_days"]
    assert config.bridge_enabled == DEFAULTS["bridge_enabled"]
    assert config.bridge_cache_maxsize == DEFAULTS["bridge_cache_maxsize"]
    assert config.bridge_cache_ttl_seconds == DEFAULTS["bridge_cache_ttl_seconds"]
    assert config.bridge_top_k == DEFAULTS["bridge_top_k"]


# ─── 2. Project root detection ───────────────────────────────────────────────


def test_project_root_detection_with_git_marker(clean_env, tmp_path, monkeypatch):
    """Test detection with .git marker directory."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    (project / "subdir").mkdir()

    # Act - Change to subdir and detect
    monkeypatch.chdir(project / "subdir")
    config = MimirConfig.load()

    # Assert
    assert config.project_root == project


def test_project_root_detection_with_env_var_override(clean_env, tmp_path, monkeypatch):
    """Test PROJECT_ROOT env var override."""
    # Arrange
    project = tmp_path / "envproject"
    project.mkdir()
    (project / ".git").mkdir()

    other = tmp_path / "other"
    other.mkdir()

    monkeypatch.setenv("PROJECT_ROOT", str(project))
    monkeypatch.chdir(other)

    # Act
    config = MimirConfig.load()

    # Assert
    assert config.project_root == project


def test_project_root_fallback_to_cwd(clean_env, tmp_path, monkeypatch):
    """Test fallback to cwd when no markers found."""
    # Arrange
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    monkeypatch.chdir(isolated)

    # Act
    config = MimirConfig.load()

    # Assert
    assert config.project_root == isolated


# ─── 3. API key resolution ───────────────────────────────────────────────────


def test_api_key_from_openrouter_env_var(clean_env, tmp_path, monkeypatch):
    """Test API key from OPENROUTER_API_KEY env var."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-openrouter-1234")

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.api_key == "sk-test-openrouter-1234"


def test_api_key_from_openai_env_var(clean_env, tmp_path, monkeypatch):
    """Test API key from OPENAI_API_KEY env var."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-5678")

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.api_key == "sk-test-openai-5678"


def test_api_key_openrouter_takes_precedence(clean_env, tmp_path, monkeypatch):
    """Test OPENROUTER_API_KEY takes precedence over OPENAI_API_KEY."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-key")

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.api_key == "sk-openrouter-key"


def test_api_key_from_auth_file(clean_env, tmp_path, monkeypatch):
    """Test API key from mock auth file."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    # Create mock auth file
    auth_dir = tmp_path / "auth"
    auth_dir.mkdir()
    auth_file = auth_dir / "auth.json"
    auth_file.write_text(json.dumps({"openrouter": {"key": "sk-auth-file-key"}}))

    # Monkeypatch the auth file paths
    import src.mimir.config as config_module

    original_paths = config_module._AUTH_FILE_PATHS
    config_module._AUTH_FILE_PATHS = [auth_file]

    try:
        # Act
        config = MimirConfig.load(project_root=project)

        # Assert
        assert config.api_key == "sk-auth-file-key"
    finally:
        config_module._AUTH_FILE_PATHS = original_paths


def test_api_key_no_key_available(clean_env, tmp_path, monkeypatch):
    """Test with no key available returns empty string."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    # Ensure no auth files exist
    import src.mimir.config as config_module

    original_paths = config_module._AUTH_FILE_PATHS
    config_module._AUTH_FILE_PATHS = []  # No auth files to check

    try:
        # Act
        config = MimirConfig.load(project_root=project)

        # Assert
        assert config.api_key == ""
    finally:
        config_module._AUTH_FILE_PATHS = original_paths


# ─── 4. Config file loading ──────────────────────────────────────────────────


def test_config_file_with_values(clean_env, tmp_path):
    """Test with .mimir/config.json containing values."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    config_dir = project / ".mimir"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "embedding_model": "custom-embedding-model",
                "llm_model": "custom-llm-model",
                "docs_dir": "documentation",
            }
        )
    )

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.embedding_model == "custom-embedding-model"
    assert config.llm_model == "custom-llm-model"
    assert config.docs_dir.name == "documentation"


def test_config_file_missing_uses_defaults(clean_env, tmp_path):
    """Test with missing config file uses defaults."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    # No .mimir/config.json created

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.embedding_model == DEFAULTS["embedding_model"]
    assert config.llm_model == DEFAULTS["llm_model"]


def test_config_file_malformed_json_falls_back(clean_env, tmp_path, caplog):
    """Test with malformed JSON falls back gracefully."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    config_dir = project / ".mimir"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text("{ invalid json }")

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert - Should use defaults despite malformed config
    assert config.embedding_model == DEFAULTS["embedding_model"]
    assert "Failed to load config file" in caplog.text


# ─── 5. Directory resolution ─────────────────────────────────────────────────


def test_docs_dir_from_config_file(clean_env, tmp_path):
    """Test docs_dir from config file."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    config_dir = project / ".mimir"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({"docs_dir": "my-docs"}))

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.docs_dir == project / "my-docs"


def test_docs_dir_from_env_var(clean_env, tmp_path, monkeypatch):
    """Test docs_dir from env var."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.setenv("DOCS_DIR", "env-docs")

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.docs_dir == project / "env-docs"


def test_docs_dir_default(clean_env, tmp_path):
    """Test docs_dir default."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.docs_dir == project / DEFAULTS["docs_dir"]


def test_knowledge_dir_resolution(clean_env, tmp_path):
    """Test knowledge_dir resolution."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.knowledge_dir == project / DEFAULTS["knowledge_dir"]


def test_code_dirs_from_config_file(clean_env, tmp_path):
    """Test code_dirs from config file."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    config_dir = project / ".mimir"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({"code_dirs": ["src", "lib"]}))

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert len(config.code_dirs) == 2
    assert config.code_dirs[0] == Path("src")
    assert config.code_dirs[1] == Path("lib")


def test_code_dirs_from_env_var(clean_env, tmp_path, monkeypatch):
    """Test code_dirs from env var (comma-separated)."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.setenv("CODE_DIRS", "src,lib,tests")

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert len(config.code_dirs) == 3
    assert config.code_dirs[0] == Path("src")
    assert config.code_dirs[1] == Path("lib")
    assert config.code_dirs[2] == Path("tests")


# ─── 6. Model configuration ──────────────────────────────────────────────────


def test_embedding_model_from_config_file(clean_env, tmp_path):
    """Test embedding_model from config file."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    config_dir = project / ".mimir"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({"embedding_model": "text-embedding-3-large"}))

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.embedding_model == "text-embedding-3-large"


def test_embedding_model_from_env_var(clean_env, tmp_path, monkeypatch):
    """Test embedding_model from env var."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.setenv("EMBEDDING_MODEL", "custom-embedding")

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.embedding_model == "custom-embedding"


def test_embedding_model_default(clean_env, tmp_path):
    """Test embedding_model default."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.embedding_model == DEFAULTS["embedding_model"]


def test_llm_model_from_config_file(clean_env, tmp_path):
    """Test llm_model from config file."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    config_dir = project / ".mimir"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(json.dumps({"llm_model": "gpt-4"}))

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.llm_model == "gpt-4"


def test_llm_model_from_env_var(clean_env, tmp_path, monkeypatch):
    """Test llm_model from env var (MIMIR_LLM_MODEL)."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.setenv("MIMIR_LLM_MODEL", "claude-3-opus")

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.llm_model == "claude-3-opus"


def test_llm_model_default(clean_env, tmp_path):
    """Test llm_model default."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.llm_model == DEFAULTS["llm_model"]


# ─── 7. Bridge settings ──────────────────────────────────────────────────────


def test_bridge_settings_from_config_file(clean_env, tmp_path):
    """Test bridge settings from config file."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    config_dir = project / ".mimir"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "bridge": {
                    "enabled": False,
                    "cache_maxsize": 256,
                    "top_k": 10,
                }
            }
        )
    )

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.bridge_enabled is False
    assert config.bridge_cache_maxsize == 256
    assert config.bridge_top_k == 10


def test_bridge_settings_from_env_vars(clean_env, tmp_path, monkeypatch):
    """Test bridge settings from env vars."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.setenv("MIMIR_OPENSPACE_ENABLED", "false")
    monkeypatch.setenv("MIMIR_BRIDGE_CACHE_SIZE", "512")
    monkeypatch.setenv("MIMIR_BRIDGE_TOP_K", "20")

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.bridge_enabled is False
    assert config.bridge_cache_maxsize == 512
    assert config.bridge_top_k == 20


def test_bridge_defaults(clean_env, tmp_path):
    """Test bridge defaults."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    # Act
    config = MimirConfig.load(project_root=project)

    # Assert
    assert config.bridge_enabled == DEFAULTS["bridge_enabled"]
    assert config.bridge_cache_maxsize == DEFAULTS["bridge_cache_maxsize"]
    assert config.bridge_cache_ttl_seconds == DEFAULTS["bridge_cache_ttl_seconds"]
    assert (
        config.bridge_circuit_breaker_threshold
        == DEFAULTS["bridge_circuit_breaker_threshold"]
    )
    assert (
        config.bridge_search_timeout_seconds
        == DEFAULTS["bridge_search_timeout_seconds"]
    )
    assert config.bridge_top_k == DEFAULTS["bridge_top_k"]


# ─── 8. validate() ───────────────────────────────────────────────────────────


def test_validate_with_valid_config(clean_env, tmp_path, monkeypatch):
    """Test with valid config (no warnings)."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    (project / "docs").mkdir()
    knowledge = project / ".knowledge" / "llamaindex"
    knowledge.mkdir(parents=True)
    (knowledge / "index_store.json").write_text("{}")

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-1234")

    config = MimirConfig.load(project_root=project)

    # Act
    warnings = config.validate()

    # Assert
    assert len(warnings) == 0


def test_validate_with_missing_api_key(clean_env, tmp_path, monkeypatch):
    """Test with missing api_key (warning)."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    (project / "docs").mkdir()
    knowledge = project / ".knowledge" / "llamaindex"
    knowledge.mkdir(parents=True)
    (knowledge / "index_store.json").write_text("{}")

    # Ensure no API key is set (clean_env already clears env vars)
    # But we need to make sure auth files don't exist either
    import src.mimir.config as config_module

    original_paths = config_module._AUTH_FILE_PATHS
    config_module._AUTH_FILE_PATHS = []  # No auth files to check

    try:
        config = MimirConfig.load(project_root=project)
        # api_key will be empty string

        # Act
        warnings = config.validate()

        # Assert
        assert any("No API key found" in w for w in warnings)
    finally:
        config_module._AUTH_FILE_PATHS = original_paths


def test_validate_with_missing_docs_dir(clean_env, tmp_path):
    """Test with missing docs_dir (warning)."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    # No docs directory created
    knowledge = project / ".knowledge" / "llamaindex"
    knowledge.mkdir(parents=True)
    (knowledge / "index_store.json").write_text("{}")

    config = MimirConfig.load(project_root=project)

    # Act
    warnings = config.validate()

    # Assert
    assert any("Docs directory does not exist" in w for w in warnings)


def test_validate_with_missing_knowledge_dir(clean_env, tmp_path):
    """Test with missing knowledge_dir (warning)."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    (project / "docs").mkdir()
    # No knowledge directory created

    config = MimirConfig.load(project_root=project)

    # Act
    warnings = config.validate()

    # Assert
    assert any("Knowledge directory does not exist" in w for w in warnings)


def test_validate_with_missing_index(clean_env, tmp_path):
    """Test with missing index (warning)."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    (project / "docs").mkdir()
    knowledge = project / ".knowledge" / "llamaindex"
    knowledge.mkdir(parents=True)
    # No index_store.json created

    config = MimirConfig.load(project_root=project)

    # Act
    warnings = config.validate()

    # Assert
    assert any("No index found" in w for w in warnings)


# ─── 9. to_dict() ────────────────────────────────────────────────────────────


def test_to_dict_masks_api_key(clean_env, tmp_path, monkeypatch):
    """Test that api_key is masked (shows ***last4)."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-1234")

    config = MimirConfig.load(project_root=project)

    # Act
    result = config.to_dict()

    # Assert
    assert result["api_key"] == "***1234"


def test_to_dict_all_expected_keys_present(clean_env, tmp_path):
    """Test that all expected keys are present."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    config = MimirConfig.load(project_root=project)

    # Act
    result = config.to_dict()

    # Assert
    expected_keys = [
        "project_root",
        "mimir_root",
        "api_key",
        "api_base",
        "embedding_model",
        "llm_model",
        "docs_dir",
        "knowledge_dir",
        "code_dirs",
        "sdk_cache_ttl_days",
        "bridge_enabled",
        "bridge_top_k",
        "_config_source",
    ]
    for key in expected_keys:
        assert key in result


def test_to_dict_paths_are_strings(clean_env, tmp_path):
    """Test that paths are strings."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    config = MimirConfig.load(project_root=project)

    # Act
    result = config.to_dict()

    # Assert
    assert isinstance(result["project_root"], str)
    assert isinstance(result["mimir_root"], str)
    assert isinstance(result["docs_dir"], str)
    assert isinstance(result["knowledge_dir"], str)


# ─── 10. Singleton behavior ──────────────────────────────────────────────────


def test_get_config_returns_same_instance(clean_env, tmp_path):
    """Test get_config() returns same instance on repeated calls."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    # Act
    config1 = get_config(project_root=project)
    config2 = get_config()

    # Assert
    assert config1 is config2


def test_reset_config_clears_singleton(clean_env, tmp_path):
    """Test reset_config() clears singleton."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    config1 = get_config(project_root=project)
    reset_config()

    # Act
    config2 = get_config(project_root=project)

    # Assert
    assert config1 is not config2


def test_get_config_after_reset_returns_new_instance(clean_env, tmp_path):
    """Test get_config() after reset returns new instance."""
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()
    (project / ".git").mkdir()

    config1 = get_config(project_root=project)
    reset_config()
    config2 = get_config(project_root=project)

    # Assert
    assert config1 is not config2
    # But they should have the same values
    assert config1.project_root == config2.project_root


# ─── 11. DEFAULTS dict ───────────────────────────────────────────────────────


def test_defaults_contains_expected_keys():
    """Test that DEFAULTS contains expected keys."""
    expected_keys = [
        "embedding_model",
        "llm_model",
        "docs_dir",
        "knowledge_dir",
        "sdk_cache_ttl_days",
        "bridge_enabled",
        "bridge_cache_maxsize",
        "bridge_cache_ttl_seconds",
        "bridge_circuit_breaker_threshold",
        "bridge_circuit_breaker_reset_seconds",
        "bridge_search_timeout_seconds",
        "bridge_max_context_tokens",
        "bridge_top_k",
        "bridge_freshness_decay_hours",
        "api_base_url",
    ]
    for key in expected_keys:
        assert key in DEFAULTS


def test_defaults_values_are_correct_types():
    """Test that DEFAULTS values are correct types."""
    assert isinstance(DEFAULTS["embedding_model"], str)
    assert isinstance(DEFAULTS["llm_model"], str)
    assert isinstance(DEFAULTS["docs_dir"], str)
    assert isinstance(DEFAULTS["knowledge_dir"], str)
    assert isinstance(DEFAULTS["sdk_cache_ttl_days"], int)
    assert isinstance(DEFAULTS["bridge_enabled"], bool)
    assert isinstance(DEFAULTS["bridge_cache_maxsize"], int)
    assert isinstance(DEFAULTS["bridge_cache_ttl_seconds"], int)
    assert isinstance(DEFAULTS["bridge_search_timeout_seconds"], float)
    assert isinstance(DEFAULTS["bridge_top_k"], int)
