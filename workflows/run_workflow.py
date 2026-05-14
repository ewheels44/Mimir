#!/usr/bin/env python3
"""
Example usage of LangGraph workflows with Mimir knowledge base.

Run this from any project with a Mimir knowledge base:
    python examples/run_workflow.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage
from langgraph.workflows.rag import graph as rag_graph
from langgraph.workflows.knowledge_agent import graph as agent_graph


async def example_rag():
    print("=" * 60)
    print("EXAMPLE 1: RAG Workflow")
    print("=" * 60)
    print("Retrieves documents from knowledge base, then generates answer.\n")

    config = {"configurable": {"thread_id": "rag-example"}}
    result = await rag_graph.ainvoke(
        {"messages": [HumanMessage(content="How does Mimir knowledge base work?")]},
        config,
    )

    print("Answer:")
    print(result["messages"][-1].content)
    print()


async def example_agent():
    print("=" * 60)
    print("EXAMPLE 2: Knowledge Agent Workflow")
    print("=" * 60)
    print("Agentic workflow that decides to search/query/respond.\n")

    config = {"configurable": {"thread_id": "agent-example"}}
    result = await agent_graph.ainvoke(
        {
            "messages": [
                HumanMessage(content="What files are indexed in my knowledge base?")
            ]
        },
        config,
    )

    print("Answer:")
    print(result["messages"][-1].content)
    print()


async def main():
    print("\nMimir LangGraph Workflow Examples")
    print("Make sure you have indexed your project first!")
    print("  python .opencode/setup.py\n")

    try:
        await example_rag()
        await example_agent()
    except Exception as e:
        print(f"Error: {e}")
        print("\nTroubleshooting:")
        print("1. Ensure you've run: python .opencode/setup.py")
        print("2. Check OPENROUTER_API_KEY is set")
        print("3. Verify langgraph dependencies are installed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
