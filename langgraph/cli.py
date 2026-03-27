#!/usr/bin/env python3
#!/usr/bin/env python3
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from langchain_core.messages import HumanMessage
from workflows.rag import graph as rag_graph
from workflows.knowledge_agent import graph as agent_graph


async def run_rag(query: str):
    print(f"Running RAG workflow for: {query}\n")

    config = {"configurable": {"thread_id": "1"}}
    result = await rag_graph.ainvoke(
        {"messages": [HumanMessage(content=query)]}, config
    )

    print("\n" + "=" * 50)
    print("RESPONSE:")
    print("=" * 50)
    print(result["messages"][-1].content)


async def run_agent(query: str):
    print(f"Running Knowledge Agent for: {query}\n")

    config = {"configurable": {"thread_id": "1"}}
    result = await agent_graph.ainvoke(
        {"messages": [HumanMessage(content=query)]}, config
    )

    print("\n" + "=" * 50)
    print("RESPONSE:")
    print("=" * 50)
    print(result["messages"][-1].content)


async def run_test():
    print("Testing LangGraph workflows...\n")

    test_query = "What is Mimir knowledge base?"

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


def main():
    parser = argparse.ArgumentParser(description="Run LangGraph workflows with Mimir")
    subparsers = parser.add_subparsers(dest="command", help="Workflow to run")

    rag_parser = subparsers.add_parser("rag", help="Run RAG workflow")
    rag_parser.add_argument("query", help="Query to search")

    agent_parser = subparsers.add_parser("agent", help="Run Knowledge Agent workflow")
    agent_parser.add_argument("query", help="Query to search")

    subparsers.add_parser("test", help="Run workflow tests")

    args = parser.parse_args()

    if args.command == "rag":
        asyncio.run(run_rag(args.query))
    elif args.command == "agent":
        asyncio.run(run_agent(args.query))
    elif args.command == "test":
        asyncio.run(run_test())
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
