"""Tests for mimir.context.ranker."""

from __future__ import annotations

import math

import pytest

from mimir.context.ranker import Ranker, ScoredItem, _cosine_similarity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def unit_vec(dim: int, index: int) -> list[float]:
    """Return a unit vector of length *dim* with a 1.0 at *index*."""
    v = [0.0] * dim
    v[index] = 1.0
    return v


def make_memory(embedding: list[float], content: str = "test") -> dict:
    return {"embedding": embedding, "content": content}


def make_node(embedding: list[float], label: str = "node") -> dict:
    return {"embedding": embedding, "label": label}


# ---------------------------------------------------------------------------
# _cosine_similarity unit tests
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector_a(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_zero_vector_b(self):
        a = [1.0, 2.0, 3.0]
        b = [0.0, 0.0, 0.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_both_zero_vectors(self):
        a = [0.0, 0.0]
        b = [0.0, 0.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="Vector length mismatch"):
            _cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])

    def test_known_value(self):
        # [1,1] vs [1,0] → cos(45°) = 1/√2
        a = [1.0, 1.0]
        b = [1.0, 0.0]
        expected = 1.0 / math.sqrt(2)
        assert _cosine_similarity(a, b) == pytest.approx(expected)

    def test_scaled_vectors_same_similarity(self):
        a = [1.0, 0.0]
        b = [5.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Ranker.score_memory
# ---------------------------------------------------------------------------


class TestScoreMemory:
    def setup_method(self):
        self.ranker = Ranker()

    def test_identical_embedding(self):
        emb = [1.0, 0.0, 0.0]
        memory = make_memory(emb)
        assert self.ranker.score_memory(memory, emb) == pytest.approx(1.0)

    def test_orthogonal_embedding(self):
        memory = make_memory([1.0, 0.0])
        query = [0.0, 1.0]
        assert self.ranker.score_memory(memory, query) == pytest.approx(0.0)

    def test_missing_embedding_key_raises(self):
        memory = {"content": "no embedding here"}
        with pytest.raises(KeyError):
            self.ranker.score_memory(memory, [1.0, 0.0])

    def test_score_is_float(self):
        memory = make_memory([0.5, 0.5])
        score = self.ranker.score_memory(memory, [1.0, 0.0])
        assert isinstance(score, float)

    def test_extra_fields_ignored(self):
        memory = {
            "embedding": [1.0, 0.0],
            "content": "hello",
            "type": "preference",
            "confidence": 0.9,
        }
        assert self.ranker.score_memory(memory, [1.0, 0.0]) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Ranker.score_graph_node
# ---------------------------------------------------------------------------


class TestScoreGraphNode:
    def setup_method(self):
        self.ranker = Ranker()

    def test_identical_embedding(self):
        emb = [0.0, 1.0, 0.0]
        node = make_node(emb)
        assert self.ranker.score_graph_node(node, emb) == pytest.approx(1.0)

    def test_orthogonal_embedding(self):
        node = make_node([1.0, 0.0])
        query = [0.0, 1.0]
        assert self.ranker.score_graph_node(node, query) == pytest.approx(0.0)

    def test_missing_embedding_key_raises(self):
        node = {"label": "no embedding"}
        with pytest.raises(KeyError):
            self.ranker.score_graph_node(node, [1.0, 0.0])

    def test_score_range(self):
        node = make_node([0.6, 0.8])
        query = [0.8, 0.6]
        score = self.ranker.score_graph_node(node, query)
        assert -1.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Ranker.rank_items
# ---------------------------------------------------------------------------


class TestRankItems:
    def setup_method(self):
        self.ranker = Ranker()
        # 3-dimensional space; each memory points along a different axis
        self.memories = [
            make_memory(unit_vec(3, 0), "mem_x"),  # along x
            make_memory(unit_vec(3, 1), "mem_y"),  # along y
            make_memory(unit_vec(3, 2), "mem_z"),  # along z
        ]
        self.nodes = [
            make_node(unit_vec(3, 0), "node_x"),
            make_node(unit_vec(3, 1), "node_y"),
            make_node(unit_vec(3, 2), "node_z"),
        ]

    # --- basic ordering ---

    def test_top1_memory_returns_best_match(self):
        query = unit_vec(3, 0)  # points along x
        results = self.ranker.rank_items(self.memories, query, top_k=1)
        assert len(results) == 1
        assert results[0].item["content"] == "mem_x"
        assert results[0].score == pytest.approx(1.0)

    def test_top1_graph_node_returns_best_match(self):
        query = unit_vec(3, 2)  # points along z
        results = self.ranker.rank_items(self.nodes, query, top_k=1, item_type="graph_node")
        assert len(results) == 1
        assert results[0].item["label"] == "node_z"

    def test_results_sorted_descending(self):
        # Query slightly biased toward y
        query = [0.1, 0.9, 0.0]
        results = self.ranker.rank_items(self.memories, query, top_k=3)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_top_k_limits_results(self):
        query = unit_vec(3, 0)
        results = self.ranker.rank_items(self.memories, query, top_k=2)
        assert len(results) == 2

    def test_top_k_larger_than_items(self):
        query = unit_vec(3, 0)
        results = self.ranker.rank_items(self.memories, query, top_k=100)
        assert len(results) == len(self.memories)

    def test_top_k_zero_returns_empty(self):
        query = unit_vec(3, 0)
        results = self.ranker.rank_items(self.memories, query, top_k=0)
        assert results == []

    def test_empty_items_returns_empty(self):
        results = self.ranker.rank_items([], unit_vec(3, 0), top_k=5)
        assert results == []

    # --- return type ---

    def test_returns_list_of_scored_items(self):
        query = unit_vec(3, 0)
        results = self.ranker.rank_items(self.memories, query, top_k=3)
        for r in results:
            assert isinstance(r, ScoredItem)
            assert isinstance(r.score, float)
            assert isinstance(r.item, dict)

    # --- item_type validation ---

    def test_invalid_item_type_raises(self):
        with pytest.raises(ValueError, match="item_type must be"):
            self.ranker.rank_items(self.memories, unit_vec(3, 0), top_k=1, item_type="unknown")

    def test_default_item_type_is_memory(self):
        """Calling without item_type should use memory scoring (no error)."""
        query = unit_vec(3, 0)
        results = self.ranker.rank_items(self.memories, query, top_k=1)
        assert len(results) == 1

    # --- graph_node item_type ---

    def test_graph_node_item_type(self):
        query = unit_vec(3, 1)
        results = self.ranker.rank_items(self.nodes, query, top_k=1, item_type="graph_node")
        assert results[0].item["label"] == "node_y"

    # --- score accuracy ---

    def test_scores_match_direct_scoring(self):
        query = [0.3, 0.7, 0.0]
        results = self.ranker.rank_items(self.memories, query, top_k=3)
        for scored in results:
            expected = self.ranker.score_memory(scored.item, query)
            assert scored.score == pytest.approx(expected)

    def test_graph_node_scores_match_direct_scoring(self):
        query = [0.5, 0.5, 0.0]
        results = self.ranker.rank_items(self.nodes, query, top_k=3, item_type="graph_node")
        for scored in results:
            expected = self.ranker.score_graph_node(scored.item, query)
            assert scored.score == pytest.approx(expected)
