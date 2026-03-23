"""Tests for MemoryClient."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_memory():
    """Create a mock Memory instance."""
    with patch("mimir.memory.client.Memory") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.from_config.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def client(mock_memory):
    """Create MemoryClient with mocked Mem0."""
    from mimir.memory.client import MemoryClient

    with patch("mimir.memory.client.Memory") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.from_config.return_value = mock_instance

        client = MemoryClient(config_path=".mimir/config.yaml")
        client._memory = mock_instance
        return client


class TestMemoryClientInit:
    """Tests for MemoryClient initialization."""

    def test_init_loads_config(self):
        """Test that init loads config from file."""
        with patch("mimir.memory.client.Memory") as mock_memory_cls:
            mock_memory_cls.from_config.return_value = MagicMock()

            from mimir.memory.client import MemoryClient

            client = MemoryClient(config_path=".mimir/config.yaml")

            assert client.project_name == "Mimir"
            assert client.embedding_model == "text-embedding-3-small"

    def test_init_uses_default_config_when_missing(self):
        """Test default config when file doesn't exist."""
        with patch("mimir.memory.client.Memory") as mock_memory_cls:
            mock_memory_cls.from_config.return_value = MagicMock()

            from mimir.memory.client import MemoryClient

            client = MemoryClient(config_path="/nonexistent/config.yaml")

            assert client.project_name == "Mimir"
            assert client.embedding_model == "text-embedding-3-small"

    def test_init_sets_qdrant_path(self):
        """Test Qdrant path is set correctly."""
        with patch("mimir.memory.client.Memory") as mock_memory_cls:
            mock_memory_cls.from_config.return_value = MagicMock()

            from mimir.memory.client import MemoryClient

            client = MemoryClient(config_path=".mimir/config.yaml")

            assert client.qdrant_path == ".mimir/qdrant"

    def test_init_configures_mem0_correctly(self):
        """Test Mem0 is configured with correct params."""
        with patch("mimir.memory.client.Memory") as mock_memory_cls:
            mock_memory_cls.from_config.return_value = MagicMock()

            from mimir.memory.client import MemoryClient

            client = MemoryClient(config_path=".mimir/config.yaml")

            call_args = mock_memory_cls.from_config.call_args[0][0]

            assert call_args["vector_store"]["provider"] == "qdrant"
            assert call_args["vector_store"]["config"]["collection_name"] == "Mimir_memories"
            assert call_args["vector_store"]["config"]["path"] == ".mimir/qdrant"
            assert call_args["version"] == "v1.1"


class TestMemoryClientAdd:
    """Tests for MemoryClient.add() method."""

    def test_add_basic_messages(self, client):
        """Test adding basic messages."""
        client._memory.add.return_value = {
            "results": [{"id": "mem1", "memory": "Test memory", "event": "ADD"}]
        }

        messages = [{"role": "user", "content": "I prefer dark mode"}]
        result = client.add(messages, user_id="user1")

        client._memory.add.assert_called_once()
        call_kwargs = client._memory.add.call_args.kwargs
        assert call_kwargs["messages"] == messages
        assert call_kwargs["user_id"] == "user1"
        assert call_kwargs["metadata"] == {}

    def test_add_with_metadata(self, client):
        """Test adding messages with metadata."""
        client._memory.add.return_value = {
            "results": [{"id": "mem1", "memory": "Test", "event": "ADD"}]
        }

        messages = [{"role": "user", "content": "I like Python"}]
        metadata = {"type": "preference", "language": "Python"}
        result = client.add(messages, user_id="user1", metadata=metadata)

        call_kwargs = client._memory.add.call_args.kwargs
        assert call_kwargs["metadata"] == metadata

    def test_add_with_valid_memory_type(self, client):
        """Test adding with valid memory types."""
        client._memory.add.return_value = {"results": []}

        for mem_type in ["preference", "decision", "convention", "episodic", "correction"]:
            messages = [{"role": "user", "content": "Test"}]
            metadata = {"type": mem_type}
            client.add(messages, user_id="user1", metadata=metadata)

            call_kwargs = client._memory.add.call_args.kwargs
            assert call_kwargs["metadata"]["type"] == mem_type

    def test_add_with_invalid_memory_type_raises(self, client):
        """Test that invalid memory type raises ValueError."""
        client._memory.add.return_value = {"results": []}

        messages = [{"role": "user", "content": "Test"}]
        metadata = {"type": "invalid_type"}

        with pytest.raises(ValueError) as exc_info:
            client.add(messages, user_id="user1", metadata=metadata)

        assert "Invalid memory type" in str(exc_info.value)

    def test_add_handles_runtime_error(self, client):
        """Test that add wraps exceptions in RuntimeError."""
        client._memory.add.side_effect = Exception("Mem0 error")

        messages = [{"role": "user", "content": "Test"}]

        with pytest.raises(RuntimeError) as exc_info:
            client.add(messages, user_id="user1")

        assert "Failed to add memory" in str(exc_info.value)


class TestMemoryClientSearch:
    """Tests for MemoryClient.search() method."""

    def test_search_basic(self, client):
        """Test basic search functionality."""
        client._memory.search.return_value = {
            "results": [
                {"id": "mem1", "memory": "I like Python", "score": 0.9},
                {"id": "mem2", "memory": "I prefer dark mode", "score": 0.8},
            ]
        }

        results = client.search("Python preferences", user_id="user1")

        client._memory.search.assert_called_once()
        call_kwargs = client._memory.search.call_args.kwargs
        assert call_kwargs["query"] == "Python preferences"
        assert call_kwargs["user_id"] == "user1"
        assert call_kwargs["limit"] == 10
        assert call_kwargs["threshold"] is None
        assert len(results) == 2

    def test_search_with_limit(self, client):
        """Test search with custom limit."""
        client._memory.search.return_value = {"results": []}

        client.search("query", user_id="user1", limit=5)

        call_kwargs = client._memory.search.call_args.kwargs
        assert call_kwargs["limit"] == 5

    def test_search_with_threshold(self, client):
        """Test search with similarity threshold."""
        client._memory.search.return_value = {
            "results": [
                {"id": "mem1", "memory": "High score", "score": 0.9},
                {"id": "mem2", "memory": "Low score", "score": 0.5},
            ]
        }

        results = client.search("query", user_id="user1", threshold=0.7)

        assert len(results) == 1
        assert results[0]["id"] == "mem1"

    def test_search_requires_user_id(self, client):
        """Test that search requires user_id."""
        with pytest.raises(ValueError) as exc_info:
            client.search("query", user_id="")

        assert "user_id is required" in str(exc_info.value)

    def test_search_handles_runtime_error(self, client):
        """Test that search wraps exceptions in RuntimeError."""
        client._memory.search.side_effect = Exception("Search failed")

        with pytest.raises(RuntimeError) as exc_info:
            client.search("query", user_id="user1")

        assert "Failed to search memories" in str(exc_info.value)


class TestMemoryClientDelete:
    """Tests for MemoryClient.delete() method."""

    def test_delete_basic(self, client):
        """Test basic delete functionality."""
        client._memory.delete.return_value = {"message": "Memory deleted successfully!"}

        result = client.delete(memory_id="mem123")

        client._memory.delete.assert_called_once_with(memory_id="mem123")
        assert result["message"] == "Memory deleted successfully!"

    def test_delete_requires_memory_id(self, client):
        """Test that delete requires memory_id."""
        with pytest.raises(ValueError) as exc_info:
            client.delete(memory_id="")

        assert "memory_id is required" in str(exc_info.value)

    def test_delete_handles_runtime_error(self, client):
        """Test that delete wraps exceptions in RuntimeError."""
        client._memory.delete.side_effect = Exception("Delete failed")

        with pytest.raises(RuntimeError) as exc_info:
            client.delete(memory_id="mem123")

        assert "Failed to delete memory" in str(exc_info.value)


class TestMemoryClientGet:
    """Tests for MemoryClient.get() method."""

    def test_get_basic(self, client):
        """Test getting a memory by ID."""
        client._memory.get.return_value = {
            "id": "mem1",
            "memory": "Test memory",
            "metadata": {"type": "preference"},
        }

        result = client.get(memory_id="mem1")

        client._memory.get.assert_called_once_with(memory_id="mem1")
        assert result["id"] == "mem1"

    def test_get_returns_none_when_not_found(self, client):
        """Test get returns None when memory not found."""
        client._memory.get.return_value = None

        result = client.get(memory_id="nonexistent")

        assert result is None

    def test_get_requires_memory_id(self, client):
        """Test that get requires memory_id."""
        with pytest.raises(ValueError) as exc_info:
            client.get(memory_id="")

        assert "memory_id is required" in str(exc_info.value)


class TestMemoryClientGetAll:
    """Tests for MemoryClient.get_all() method."""

    def test_get_all_basic(self, client):
        """Test getting all memories for a user."""
        client._memory.get_all.return_value = {
            "results": [
                {"id": "mem1", "memory": "Memory 1"},
                {"id": "mem2", "memory": "Memory 2"},
            ]
        }

        result = client.get_all(user_id="user1")

        client._memory.get_all.assert_called_once_with(user_id="user1", limit=100)
        assert len(result) == 2

    def test_get_all_with_limit(self, client):
        """Test get_all with custom limit."""
        client._memory.get_all.return_value = {"results": []}

        client.get_all(user_id="user1", limit=10)

        call_kwargs = client._memory.get_all.call_args.kwargs
        assert call_kwargs["limit"] == 10

    def test_get_all_requires_user_id(self, client):
        """Test that get_all requires user_id."""
        with pytest.raises(ValueError) as exc_info:
            client.get_all(user_id="")

        assert "user_id is required" in str(exc_info.value)


class TestMemoryTypes:
    """Tests for memory type validation."""

    def test_memory_types_constant(self):
        """Test MEMORY_TYPES constant is defined correctly."""
        from mimir.memory.client import MEMORY_TYPES

        assert MEMORY_TYPES == ["preference", "decision", "convention", "episodic", "correction"]

    def test_all_valid_memory_types_accepted(self, client):
        """Test all defined memory types are valid."""
        client._memory.add.return_value = {"results": []}

        for mem_type in ["preference", "decision", "convention", "episodic", "correction"]:
            messages = [{"role": "user", "content": f"Test {mem_type}"}]
            metadata = {"type": mem_type}

            try:
                client.add(messages, user_id="user1", metadata=metadata)
            except ValueError:
                pytest.fail(f"Memory type '{mem_type}' should be valid")
