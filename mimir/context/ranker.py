"""Relevance Ranker for scoring and selecting top-K memories and graph nodes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class ScoredItem:
    """An item paired with its relevance score."""

    item: Any
    score: float


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns a value in [-1, 1]. Returns 0.0 if either vector has zero magnitude.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Vector length mismatch: {len(vec_a)} vs {len(vec_b)}")

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))

    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0

    return dot / (mag_a * mag_b)


class Ranker:
    """Scores memories and graph nodes by relevance to a query embedding.

    Uses cosine similarity between the query embedding and item embeddings.
    No ML-based ranking, no caching — pure vector similarity.
    """

    def score_memory(self, memory: dict[str, Any], query_embedding: list[float]) -> float:
        """Score a memory dict against a query embedding.

        The memory dict must contain an ``embedding`` key with a list of floats.

        Args:
            memory: A memory dict with at least an ``embedding`` field.
            query_embedding: The query's embedding vector.

        Returns:
            Cosine similarity score in [-1, 1].

        Raises:
            KeyError: If ``memory`` does not contain an ``embedding`` key.
            ValueError: If the embedding vectors have different lengths.
        """
        memory_embedding: list[float] = memory["embedding"]
        return _cosine_similarity(memory_embedding, query_embedding)

    def score_graph_node(self, node: dict[str, Any], query_embedding: list[float]) -> float:
        """Score a graph node dict against a query embedding.

        The node dict must contain an ``embedding`` key with a list of floats.

        Args:
            node: A graph node dict with at least an ``embedding`` field.
            query_embedding: The query's embedding vector.

        Returns:
            Cosine similarity score in [-1, 1].

        Raises:
            KeyError: If ``node`` does not contain an ``embedding`` key.
            ValueError: If the embedding vectors have different lengths.
        """
        node_embedding: list[float] = node["embedding"]
        return _cosine_similarity(node_embedding, query_embedding)

    def rank_items(
        self,
        items: list[dict[str, Any]],
        query_embedding: list[float],
        top_k: int,
        item_type: str = "memory",
    ) -> list[ScoredItem]:
        """Score all items and return the top-K by cosine similarity.

        Args:
            items: List of memory dicts or graph node dicts, each with an
                ``embedding`` field.
            query_embedding: The query's embedding vector.
            top_k: Maximum number of results to return.
            item_type: Either ``"memory"`` or ``"graph_node"``. Determines
                which scoring method is used. Defaults to ``"memory"``.

        Returns:
            List of :class:`ScoredItem` sorted by descending score, at most
            ``top_k`` entries.

        Raises:
            ValueError: If ``item_type`` is not ``"memory"`` or ``"graph_node"``.
        """
        if item_type not in ("memory", "graph_node"):
            raise ValueError(f"item_type must be 'memory' or 'graph_node', got {item_type!r}")

        score_fn = self.score_memory if item_type == "memory" else self.score_graph_node

        scored = [ScoredItem(item=item, score=score_fn(item, query_embedding)) for item in items]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top_k]
