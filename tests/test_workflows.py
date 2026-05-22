#!/usr/bin/env python3
"""Test LangGraph workflows.

This is a smoke/integration test that requires langchain_core and langgraph.
It will be skipped if dependencies are not installed.
"""

import sys
from pathlib import Path

import pytest

MIMIR_DIR = Path("/Users/ethanwheeler/Documents/Mimir")
sys.path.insert(0, str(MIMIR_DIR))

# Skip entire module if langchain_core is not installed
pytest.importorskip("langchain_core")


@pytest.mark.asyncio
async def test_rag_workflow():
    """Test RAG workflow executes without error."""
    from langchain_core.messages import HumanMessage
    from langgraph.workflows.rag import graph as rag_graph

    test_query = "What is the Mimir project?"
    config = {"configurable": {"thread_id": "test-rag"}}
    result = await rag_graph.ainvoke(
        {"messages": [HumanMessage(content=test_query)]}, config
    )
    assert result is not None
    assert "messages" in result


@pytest.mark.asyncio
async def test_knowledge_agent_workflow():
    """Test Knowledge Agent workflow executes without error."""
    from langchain_core.messages import HumanMessage
    from langgraph.workflows.knowledge_agent import graph as agent_graph

    test_query = "What is the Mimir project?"
    config = {"configurable": {"thread_id": "test-agent"}}
    result = await agent_graph.ainvoke(
        {"messages": [HumanMessage(content=test_query)]}, config
    )
    assert result is not None
    assert "messages" in result


if __name__ == "__main__":
    import asyncio

    pytest.main([__file__, "-v"])
