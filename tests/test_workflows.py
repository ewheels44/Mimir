#!/usr/bin/env python3
"""Test LangGraph workflows."""

import sys
import asyncio
from pathlib import Path

MIMIR_DIR = Path("/Users/ethanwheeler/Documents/Mimir")
sys.path.insert(0, str(MIMIR_DIR))
sys.path.insert(0, str(MIMIR_DIR / "langgraph" / "workflows"))

from langchain_core.messages import HumanMessage
from rag import graph as rag_graph
from knowledge_agent import graph as agent_graph


async def test():
    print("Testing LangGraph workflows...\n")
    test_query = "What is the RavenEye project?"

    print("1. Testing RAG workflow...")
    try:
        config = {"configurable": {"thread_id": "test-rag"}}
        result = await rag_graph.ainvoke(
            {"messages": [HumanMessage(content=test_query)]}, config
        )
        print("   RAG workflow: OK")
        print(f"   Response preview: {result['messages'][-1].content[:100]}...")
    except Exception as e:
        print(f"   RAG workflow: FAILED - {e}")
        import traceback

        traceback.print_exc()

    print("\n2. Testing Knowledge Agent workflow...")
    try:
        config = {"configurable": {"thread_id": "test-agent"}}
        result = await agent_graph.ainvoke(
            {"messages": [HumanMessage(content=test_query)]}, config
        )
        print("   Knowledge Agent workflow: OK")
        print(f"   Response preview: {result['messages'][-1].content[:100]}...")
    except Exception as e:
        print(f"   Knowledge Agent workflow: FAILED - {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test())
