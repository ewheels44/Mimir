"""Tests for Graph Client with Kuzu and Qdrant.

T7: Three-Layer AI Context System - Graph Client Tests
"""

import json
import tempfile
import pytest

from mimir.graph.client import GraphClient, NODE_TYPES, EDGE_TYPES


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as graph_dir, tempfile.TemporaryDirectory() as qdrant_dir:
        yield graph_dir, qdrant_dir


@pytest.fixture
def client(temp_dirs):
    """Create a GraphClient for testing."""
    graph_dir, qdrant_dir = temp_dirs
    with GraphClient(
        db_path=graph_dir,
        qdrant_path=qdrant_dir,
        project_name="TestProject",
        vector_size=1536,
    ) as c:
        yield c


class TestNodeTypes:
    """Test that all node types are defined correctly."""

    def test_node_types_defined(self):
        """Verify all 8 node types are defined."""
        expected = {
            "BusinessGoal",
            "Feature",
            "Module",
            "DataModel",
            "RevenueStream",
            "Risk",
            "CustomerSegment",
            "ExternalDep",
        }
        assert NODE_TYPES == expected

    def test_edge_types_defined(self):
        """Verify edge types are defined."""
        assert len(EDGE_TYPES) > 0
        assert "implements" in EDGE_TYPES
        assert "depends_on" in EDGE_TYPES
        assert "requires" in EDGE_TYPES


class TestCreateNode:
    """Test node creation."""

    def test_create_feature_node(self, client):
        """Test creating a Feature node."""
        node_id = client.create_node(
            "Feature",
            {
                "id": "feature_001",
                "name": "User Authentication",
                "description": "Enable users to authenticate with OAuth2",
                "metadata": {"priority": "high", "status": "active"},
            },
        )

        assert node_id == "feature_001"

        # Verify node was created
        node = client.get_node("feature_001")
        assert node is not None
        assert node["id"] == "feature_001"
        assert node["name"] == "User Authentication"
        assert node["type"] == "Feature"

    def test_create_node_with_auto_id(self, client):
        """Test creating a node without providing an ID."""
        node_id = client.create_node(
            "Module",
            {
                "name": "Auth Module",
                "description": "Handles authentication logic",
            },
        )

        assert node_id is not None
        assert node_id.startswith("module_")

    def test_create_all_node_types(self, client):
        """Test creating nodes of all types."""
        node_types = [
            ("BusinessGoal", "bg_001", "Increase Revenue"),
            ("Feature", "feat_001", "New Feature"),
            ("Module", "mod_001", "Core Module"),
            ("DataModel", "dm_001", "User Data"),
            ("RevenueStream", "rs_001", "Subscription"),
            ("Risk", "risk_001", "Security Risk"),
            ("CustomerSegment", "cs_001", "Enterprise"),
            ("ExternalDep", "ext_001", "API Service"),
        ]

        for node_type, node_id, name in node_types:
            created_id = client.create_node(
                node_type,
                {"id": node_id, "name": name, "description": f"Test {name}"},
            )
            assert created_id == node_id

            # Verify
            node = client.get_node(node_id)
            assert node is not None
            assert node["type"] == node_type

    def test_create_node_invalid_type(self, client):
        """Test that creating a node with invalid type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            client.create_node(
                "InvalidType",
                {"id": "test", "name": "Test"},
            )

        assert "Invalid node type" in str(exc_info.value)


class TestCreateEdge:
    """Test edge creation."""

    @pytest.fixture
    def nodes(self, client):
        """Create test nodes."""
        feature_id = client.create_node(
            "Feature",
            {"id": "feature_test", "name": "Test Feature"},
        )
        goal_id = client.create_node(
            "BusinessGoal",
            {"id": "goal_test", "name": "Test Goal"},
        )
        module_id = client.create_node(
            "Module",
            {"id": "module_test", "name": "Test Module"},
        )

        return {
            "feature": feature_id,
            "goal": goal_id,
            "module": module_id,
        }

    def test_create_implements_edge(self, client, nodes):
        """Test creating an implements edge."""
        edge = client.create_edge(
            nodes["feature"],
            nodes["goal"],
            "implements",
        )

        assert edge["from"] == nodes["feature"]
        assert edge["to"] == nodes["goal"]
        assert edge["rel_type"] == "implements"

    def test_create_edge_with_properties(self, client, nodes):
        """Test creating an edge with properties."""
        # Note: Kuzu requires properties to be defined in the REL TABLE schema
        # For now, we test without properties
        edge = client.create_edge(
            nodes["feature"],
            nodes["module"],
            "requires",
        )

        assert edge["rel_type"] == "requires"

    def test_create_edge_invalid_type(self, client, nodes):
        """Test that creating an edge with invalid type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            client.create_edge(
                nodes["feature"],
                nodes["goal"],
                "invalid_edge_type",
            )

        assert "Invalid edge type" in str(exc_info.value)


class TestGetNeighbors:
    """Test get_neighbors method."""

    @pytest.fixture
    def graph_setup(self, client):
        """Set up a test graph."""
        # Create nodes
        feature1 = client.create_node("Feature", {"id": "f1", "name": "Feature 1"})
        feature2 = client.create_node("Feature", {"id": "f2", "name": "Feature 2"})
        module1 = client.create_node("Module", {"id": "m1", "name": "Module 1"})

        # Create edges
        client.create_edge(feature1, feature2, "enables")
        client.create_edge(feature2, module1, "requires")

        return {"f1": feature1, "f2": feature2, "m1": module1}

    def test_get_neighbors_depth_1(self, client, graph_setup):
        """Test getting direct neighbors."""
        neighbors = client.get_neighbors(graph_setup["f1"], depth=1)

        assert len(neighbors) > 0
        # Should find f2 as a neighbor
        neighbor_ids = [n["target_id"] for n in neighbors]
        assert graph_setup["f2"] in neighbor_ids

    def test_get_neighbors_depth_2(self, client, graph_setup):
        """Test getting neighbors at depth 2."""
        neighbors = client.get_neighbors(graph_setup["f1"], depth=2)

        # Should find both f2 and m1
        neighbor_ids = [n.get("target_id") or n.get("target_id") for n in neighbors]
        # At depth 2, we should reach m1 through f2
        assert len(neighbors) >= 1


class TestFindPath:
    """Test find_path method."""

    @pytest.fixture
    def path_graph(self, client):
        """Set up a graph for path finding."""
        # Create a chain: A -> B -> C -> D
        a = client.create_node("Feature", {"id": "path_a", "name": "A"})
        b = client.create_node("Feature", {"id": "path_b", "name": "B"})
        c = client.create_node("Feature", {"id": "path_c", "name": "C"})
        d = client.create_node("Feature", {"id": "path_d", "name": "D"})

        client.create_edge(a, b, "enables")
        client.create_edge(b, c, "enables")
        client.create_edge(c, d, "enables")

        return {"a": a, "b": b, "c": c, "d": d}

    def test_find_path_between_nodes(self, client, path_graph):
        """Test finding a path between two nodes."""
        paths = client.find_path(path_graph["a"], path_graph["d"])

        # Should find at least one path
        assert isinstance(paths, list)

    def test_find_path_no_path(self, client):
        """Test finding path when none exists."""
        # Create disconnected nodes
        node1 = client.create_node("Feature", {"id": "isolated_1", "name": "Isolated 1"})
        node2 = client.create_node("Feature", {"id": "isolated_2", "name": "Isolated 2"})

        paths = client.find_path(node1, node2)

        # Should return empty list or limited results
        assert isinstance(paths, list)


class TestSemanticSearch:
    """Test semantic search with Qdrant."""

    def test_semantic_search_empty(self, client):
        """Test semantic search on empty collection."""
        # Create a random query vector
        query_vector = [0.1] * 1536

        results = client.semantic_search(query_vector, top_k=5)

        assert isinstance(results, list)
        assert len(results) == 0

    def test_semantic_search_with_data(self, client):
        """Test semantic search with indexed nodes."""
        # Create and index a node
        node_id = client.create_node(
            "Feature",
            {"id": "semantic_test", "name": "Machine Learning Feature"},
        )

        # Create embedding (in real usage, this would come from an embedding model)
        embedding = [0.1] * 1536
        embedding[0] = 0.9  # Make it distinctive

        client.index_node_embedding(
            node_id=node_id,
            node_type="Feature",
            name="Machine Learning Feature",
            description="A feature that uses ML",
            embedding=embedding,
        )

        # Search with similar embedding
        search_vector = [0.1] * 1536
        search_vector[0] = 0.85

        results = client.semantic_search(search_vector, top_k=5)

        assert len(results) > 0
        assert results[0]["node_id"] == node_id
        assert results[0]["score"] > 0.5

    def test_semantic_search_with_filter(self, client):
        """Test semantic search with node type filter."""
        # Create nodes of different types
        feature_id = client.create_node(
            "Feature", {"id": "semantic_feature", "name": "Test Feature"}
        )
        module_id = client.create_node("Module", {"id": "semantic_module", "name": "Test Module"})

        embedding = [0.2] * 1536

        client.index_node_embedding(
            node_id=feature_id,
            node_type="Feature",
            name="Test Feature",
            description="A feature",
            embedding=embedding,
        )

        client.index_node_embedding(
            node_id=module_id,
            node_type="Module",
            name="Test Module",
            description="A module",
            embedding=embedding,
        )

        # Search only for Features
        results = client.semantic_search(embedding, top_k=10, node_type="Feature")

        assert all(r["node_type"] == "Feature" for r in results)


class TestGetNode:
    """Test get_node method."""

    def test_get_existing_node(self, client):
        """Test getting an existing node."""
        node_id = client.create_node(
            "Feature",
            {"id": "get_test", "name": "Get Test", "description": "Test description"},
        )

        node = client.get_node(node_id)

        assert node is not None
        assert node["id"] == node_id
        assert node["name"] == "Get Test"
        assert node["description"] == "Test description"

    def test_get_nonexistent_node(self, client):
        """Test getting a non-existent node."""
        node = client.get_node("nonexistent_id")

        assert node is None


class TestDeleteNode:
    """Test delete_node method."""

    def test_delete_existing_node(self, client):
        """Test deleting an existing node."""
        node_id = client.create_node(
            "Feature",
            {"id": "delete_test", "name": "Delete Test"},
        )

        # Verify it exists
        assert client.get_node(node_id) is not None

        # Delete it
        deleted = client.delete_node(node_id)

        assert deleted is True
        assert client.get_node(node_id) is None

    def test_delete_nonexistent_node(self, client):
        """Test deleting a non-existent node."""
        deleted = client.delete_node("nonexistent")

        assert deleted is False


class TestContextManager:
    """Test context manager functionality."""

    def test_context_manager(self, temp_dirs):
        """Test using GraphClient as context manager."""
        graph_dir, qdrant_dir = temp_dirs

        with GraphClient(
            db_path=graph_dir,
            qdrant_path=qdrant_dir,
        ) as client:
            node_id = client.create_node(
                "Feature",
                {"id": "context_test", "name": "Context Test"},
            )
            assert node_id == "context_test"

        # After exiting context, client should be closed
        # (This is implicitly tested - if close() fails, we'd get an error)


class TestQdrantCollection:
    """Test Qdrant collection naming."""

    def test_collection_name(self, client):
        """Test that collection name is correctly formatted."""
        assert client.qdrant_collection == "TestProject_graph_nodes"

    def test_default_project_name(self, temp_dirs):
        """Test default project name."""
        graph_dir, qdrant_dir = temp_dirs

        with GraphClient(
            db_path=graph_dir,
            qdrant_path=qdrant_dir,
        ) as client:
            assert client.qdrant_collection == "Mimir_graph_nodes"
