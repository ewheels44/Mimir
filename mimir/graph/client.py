"""Graph Client with Kuzu embedded DB and Qdrant embeddings.

T7: Three-Layer AI Context System - Graph Client Implementation

This module provides a GraphClient class that integrates:
- Kuzu embedded graph database for structural graph operations
- Qdrant vector database for semantic search capabilities
"""

import json
import uuid
from pathlib import Path
from typing import Any

import kuzu
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


# Node types from graph schema (T3)
NODE_TYPES = frozenset(
    [
        "BusinessGoal",
        "Feature",
        "Module",
        "DataModel",
        "RevenueStream",
        "Risk",
        "CustomerSegment",
        "ExternalDep",
    ]
)

# Edge types from graph schema (T3)
EDGE_TYPES = frozenset(
    [
        "implements",
        "depends_on",
        "depends_on_feature",
        "depends_on_data",
        "enables",
        "enables_feature",
        "blocks",
        "blocks_module",
        "serves",
        "serves_segment",
        "requires",
        "requires_data",
        "requires_external",
        "measured_by",
        "funded_by",
    ]
)


class GraphClient:
    """Graph client using Kuzu embedded DB and Qdrant for semantic search.

    This client provides:
    - create_node(): Create nodes of any supported type
    - create_edge(): Create edges between nodes
    - get_neighbors(): Traverse graph to find neighbors
    - find_path(): Find paths between two nodes
    - semantic_search(): Search nodes using vector embeddings
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        qdrant_path: str | Path | None = None,
        project_name: str = "Mimir",
        vector_size: int = 1536,
    ):
        """Initialize the Graph Client.

        Args:
            db_path: Path to Kuzu database directory. Defaults to .mimir/graph.
            qdrant_path: Path to Qdrant storage. Defaults to .mimir/qdrant.
            project_name: Project name for Qdrant collection naming.
            vector_size: Embedding vector size. Defaults to 1536.
        """
        self.project_name = project_name
        self.vector_size = vector_size

        # Initialize Kuzu database
        if db_path is None:
            db_path = Path(".mimir/graph")
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)

        # Kuzu requires the path to be a file (not a directory)
        self._db = kuzu.Database(str(self.db_path / "kuzu_db"))

        # Initialize Qdrant client
        if qdrant_path is None:
            qdrant_path = Path(".mimir/qdrant")
        self.qdrant_path = Path(qdrant_path)
        self.qdrant_path.mkdir(parents=True, exist_ok=True)

        self._qdrant = QdrantClient(path=str(self.qdrant_path))

        # Initialize schema
        self._init_schema()
        self._init_qdrant_collection()

    def _init_schema(self) -> None:
        """Initialize Kuzu schema with node and edge tables."""
        conn = kuzu.Connection(self._db)

        # Create node tables
        for node_type in NODE_TYPES:
            conn.execute(f"""
                CREATE NODE TABLE IF NOT EXISTS {node_type}(
                    id STRING PRIMARY KEY,
                    name STRING,
                    description STRING,
                    metadata JSON
                )
            """)

        # Create edge tables
        edge_definitions = {
            "implements": "FROM Feature TO BusinessGoal",
            "depends_on": "FROM Module TO Module",
            "depends_on_feature": "FROM Feature TO Feature",
            "depends_on_data": "FROM Module TO DataModel",
            "enables": "FROM Feature TO Feature",
            "enables_feature": "FROM Module TO Feature",
            "blocks": "FROM Risk TO Feature",
            "blocks_module": "FROM Risk TO Module",
            "serves": "FROM Feature TO CustomerSegment",
            "serves_segment": "FROM RevenueStream TO CustomerSegment",
            "requires": "FROM Feature TO Module",
            "requires_data": "FROM Feature TO DataModel",
            "requires_external": "FROM Feature TO ExternalDep",
            "measured_by": "FROM BusinessGoal TO RevenueStream",
            "funded_by": "FROM BusinessGoal TO RevenueStream",
        }

        for rel_type, definition in edge_definitions.items():
            conn.execute(f"""
                CREATE REL TABLE IF NOT EXISTS {rel_type}(
                    {definition},
                    MANY_MANY
                )
            """)

    def _init_qdrant_collection(self) -> None:
        """Initialize Qdrant collection for graph node embeddings."""
        collection_name = f"{self.project_name}_graph_nodes"

        # Check if collection exists
        collections = self._qdrant.get_collections()
        collection_names = [c.name for c in collections.collections]

        if collection_name not in collection_names:
            self._qdrant.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                ),
            )

    @property
    def qdrant_collection(self) -> str:
        """Return the Qdrant collection name for graph nodes."""
        return f"{self.project_name}_graph_nodes"

    def create_node(
        self,
        table: str,
        properties: dict[str, Any],
    ) -> str:
        """Create a node in the graph.

        Args:
            table: Node type (one of BusinessGoal, Feature, Module, DataModel,
                   RevenueStream, Risk, CustomerSegment, ExternalDep)
            properties: Node properties including:
                - id: Optional unique identifier (generated if not provided)
                - name: Node name
                - description: Node description
                - metadata: Optional additional metadata dict

        Returns:
            The node ID.

        Raises:
            ValueError: If table is not a valid node type.
        """
        if table not in NODE_TYPES:
            raise ValueError(
                f"Invalid node type: {table}. Valid types: {', '.join(sorted(NODE_TYPES))}"
            )

        # Generate ID if not provided
        node_id = properties.get("id") or f"{table.lower()}_{uuid.uuid4().hex[:8]}"

        # Prepare properties
        name = properties.get("name", "")
        description = properties.get("description", "")
        metadata = properties.get("metadata", {})

        conn = kuzu.Connection(self._db)
        conn.execute(
            f"CREATE (n:{table} {{id: $id, name: $name, description: $description, metadata: $metadata}})",
            {
                "id": node_id,
                "name": name,
                "description": description,
                "metadata": json.dumps(metadata),
            },
        )

        return node_id

    def create_edge(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an edge between two nodes.

        Args:
            from_id: Source node ID
            to_id: Target node ID
            rel_type: Relationship type (one of implements, depends_on, etc.)
            properties: Optional edge properties

        Returns:
            Dict with 'from', 'to', and 'rel_type' keys.

        Raises:
            ValueError: If rel_type is not a valid edge type.
        """
        if rel_type not in EDGE_TYPES:
            raise ValueError(
                f"Invalid edge type: {rel_type}. Valid types: {', '.join(sorted(EDGE_TYPES))}"
            )

        conn = kuzu.Connection(self._db)

        if properties:
            # Convert properties to JSON for storage
            props_json = json.dumps(properties)
            conn.execute(
                f"MATCH (a), (b) WHERE a.id = $from_id AND b.id = $to_id "
                f"CREATE (a)-[r:{rel_type} {{properties: $props}}]->(b)",
                {"from_id": from_id, "to_id": to_id, "props": props_json},
            )
        else:
            conn.execute(
                f"MATCH (a), (b) WHERE a.id = $from_id AND b.id = $to_id "
                f"CREATE (a)-[r:{rel_type}]->(b)",
                {"from_id": from_id, "to_id": to_id},
            )

        return {"from": from_id, "to": to_id, "rel_type": rel_type}

    def get_neighbors(
        self,
        node_id: str,
        depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Get neighbors of a node up to specified depth.

        Args:
            node_id: The node ID to find neighbors for.
            depth: Traversal depth. Defaults to 1.

        Returns:
            List of neighbor nodes with their relationships.
        """
        conn = kuzu.Connection(self._db)

        # Build the traversal query based on depth
        if depth == 1:
            query = """
                MATCH (n)-[r]-(m)
                WHERE n.id = $node_id
                RETURN n, r, m
            """
        else:
            # For deeper traversal, use variable length pattern
            # This is a simplified version - for complex graphs, consider using APOC-like procedures
            query = f"""
                MATCH (n)-[r*1:{depth}]-(m)
                WHERE n.id = $node_id
                RETURN n, r, m
            """

        result = conn.execute(query, {"node_id": node_id})
        rows = result.get_all()

        neighbors = []
        for row in rows:
            source_node = row[0]
            rel = row[1]
            target_node = row[2]

            # Handle both single relationship and list of relationships
            if depth == 1:
                rel_type = rel.get("~type", "Unknown") if isinstance(rel, dict) else "Unknown"
            else:
                rel_type = [
                    r.get("~type", "Unknown") if isinstance(r, dict) else "Unknown" for r in rel
                ]

            neighbor = {
                "source_id": source_node.get("id") if isinstance(source_node, dict) else "",
                "rel_type": rel_type,
                "target_id": target_node.get("id") if isinstance(target_node, dict) else "",
                "target_name": target_node.get("name") if isinstance(target_node, dict) else "",
                "target_description": target_node.get("description")
                if isinstance(target_node, dict)
                else "",
                "target_type": target_node.get("_label", "")
                if isinstance(target_node, dict)
                else "",
            }
            neighbors.append(neighbor)

        return neighbors

    def find_path(
        self,
        from_id: str,
        to_id: str,
    ) -> list[list[dict[str, Any]]]:
        """Find all paths between two nodes.

        Args:
            from_id: Source node ID
            to_id: Target node ID

        Returns:
            List of paths, where each path is a list of node/edge dicts.
        """
        conn = kuzu.Connection(self._db)

        # Find shortest paths using Kuzu's path finding
        query = """
            MATCH path = (a)-[*1..10]-(b)
            WHERE a.id = $from_id AND b.id = $to_id
            RETURN path
            LIMIT 100
        """

        result = conn.execute(query, {"from_id": from_id, "to_id": to_id})
        rows = result.get_all()

        paths = []
        for row in rows:
            # Path is returned as a list of nodes and relationships
            path_data = row[0]

            if path_data and hasattr(path_data, "nodes") and hasattr(path_data, "rels"):
                path_nodes = [
                    {
                        "id": n.get("id"),
                        "name": n.get("name"),
                        "type": n.get("~labels", ["Unknown"])[0]
                        if isinstance(n, dict)
                        else "Unknown",
                    }
                    for n in path_data.nodes
                ]

                path_rels = [
                    {"type": r.get("~type", "Unknown") if isinstance(r, dict) else "Unknown"}
                    for r in path_data.rels
                ]

                # Interleave nodes and relationships
                full_path = []
                for i, node in enumerate(path_nodes):
                    full_path.append({"node": node})
                    if i < len(path_rels):
                        full_path.append({"rel": path_rels[i]})

                paths.append(full_path)

        return paths

    def semantic_search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        node_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search nodes by semantic similarity using Qdrant.

        Args:
            query_vector: The embedding vector to search with.
            top_k: Number of results to return. Defaults to 10.
            node_type: Optional filter to only return nodes of this type.

        Returns:
            List of matching nodes with scores.
        """
        collection_name = self.qdrant_collection

        # Build filter if node_type is specified
        filter_condition = None
        if node_type:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            filter_condition = Filter(
                must=[
                    FieldCondition(
                        key="node_type",
                        match=MatchValue(value=node_type),
                    )
                ]
            )

        results = self._qdrant.query(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=filter_condition,
            with_payload=True,
        )

        return [
            {
                "id": result.id,
                "score": result.score,
                "node_id": result.payload.get("node_id"),
                "node_type": result.payload.get("node_type"),
                "name": result.payload.get("name"),
                "description": result.payload.get("description"),
            }
            for result in results
        ]

    def index_node_embedding(
        self,
        node_id: str,
        node_type: str,
        name: str,
        description: str,
        embedding: list[float],
    ) -> None:
        """Index a node's embedding in Qdrant for semantic search.

        Args:
            node_id: The node's unique ID.
            node_type: The node type (e.g., Feature, Module).
            name: The node's name.
            description: The node's description.
            embedding: The embedding vector.
        """
        point = PointStruct(
            id=node_id,
            vector=embedding,
            payload={
                "node_id": node_id,
                "node_type": node_type,
                "name": name,
                "description": description,
            },
        )

        self._qdrant.upsert(
            collection_name=self.qdrant_collection,
            points=[point],
        )

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Get a node by ID.

        Args:
            node_id: The node ID to retrieve.

        Returns:
            Node properties or None if not found.
        """
        conn = kuzu.Connection(self._db)

        query = """
            MATCH (n)
            WHERE n.id = $node_id
            RETURN n
        """

        result = conn.execute(query, {"node_id": node_id})
        rows = result.get_all()

        if rows:
            node_data = rows[0][0]
            return {
                "id": node_data.get("id"),
                "name": node_data.get("name"),
                "description": node_data.get("description"),
                "metadata": json.loads(node_data.get("metadata", "{}"))
                if node_data.get("metadata")
                else {},
                "type": node_data.get("_label", ""),
            }

        return None

    def delete_node(self, node_id: str) -> bool:
        """Delete a node and all its edges.

        Args:
            node_id: The node ID to delete.

        Returns:
            True if node was deleted, False if not found.
        """
        conn = kuzu.Connection(self._db)

        # Delete all edges first
        conn.execute(
            "MATCH (n)-[r]-(m) WHERE n.id = $node_id DELETE r",
            {"node_id": node_id},
        )
        conn.execute(
            "MATCH (n)-[r]-(m) WHERE m.id = $node_id DELETE r",
            {"node_id": node_id},
        )

        # Delete the node
        result = conn.execute(
            "MATCH (n) WHERE n.id = $node_id DELETE n RETURN n.id",
            {"node_id": node_id},
        )

        deleted = len(result.get_all()) > 0

        # Also delete from Qdrant if exists
        try:
            self._qdrant.delete(
                collection_name=self.qdrant_collection,
                points_selector=[node_id],
            )
        except Exception:
            pass  # Ignore if not found in Qdrant

        return deleted

    def close(self) -> None:
        """Close database connections."""
        # Kuzu automatically handles connection cleanup
        # Just explicitly close the database
        self._db.close()

    def __enter__(self) -> "GraphClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
