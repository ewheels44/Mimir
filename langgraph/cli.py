#!/usr/bin/env python3
import argparse
import asyncio
import sys
import time
from pathlib import Path

# Add project root to path so 'from src.mimir...' works
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / "src"))

from src.mimir.logging_config import setup_logging

from langchain_core.messages import HumanMessage
from workflows.call_prep import graph as prep_graph
from workflows.knowledge_agent import graph as agent_graph
from workflows.rag import graph as rag_graph
from workflows.session_diff import graph as diff_graph

from src.mimir.metrics import format_report, get_tracker

# Setup logging
setup_logging()


async def run_rag(query: str):
    print(f"Running RAG workflow for: {query}\n")

    start_time = time.time()
    config = {"configurable": {"thread_id": "1"}}
    result = await rag_graph.ainvoke(
        {"messages": [HumanMessage(content=query)]}, config
    )
    duration_ms = int((time.time() - start_time) * 1000)

    response = result["messages"][-1].content
    context = result.get("context", [])

    print("\n" + "=" * 50)
    print("RESPONSE:")
    print("=" * 50)
    print(response)

    # Extract actual token usage if available from the workflow state
    token_usage = result.get("token_usage", {})
    has_actual_data = token_usage.get("has_actual_data", False)

    # Track metrics
    tracker = get_tracker()

    if has_actual_data and token_usage.get("total_tokens", 0) > 0:
        # Use actual token data from the callback
        tracker.record_query(
            query_type="rag",
            query_text=query,
            docs_retrieved=len(context),
            duration_ms=duration_ms,
            actual_tokens=token_usage,
        )
        print(
            f"\n[Metrics] Recorded with actual tokens: {token_usage['total_tokens']} total"
        )
    else:
        # Fall back to estimates
        tracker.record_query(
            query_type="rag",
            query_text=query,
            docs_retrieved=len(context),
            duration_ms=duration_ms,
        )
        print("\n[Metrics] Recorded with estimated tokens")


async def run_agent(query: str):
    print(f"Running Knowledge Agent for: {query}\n")

    start_time = time.time()
    config = {"configurable": {"thread_id": "1"}}
    result = await agent_graph.ainvoke(
        {"messages": [HumanMessage(content=query)]}, config
    )
    duration_ms = int((time.time() - start_time) * 1000)

    response = result["messages"][-1].content

    print("\n" + "=" * 50)
    print("RESPONSE:")
    print("=" * 50)
    print(response)

    # Track metrics - agent uses estimates for now
    tracker = get_tracker()
    tracker.record_query(
        query_type="agent",
        query_text=query,
        duration_ms=duration_ms,
    )


async def run_prep(query: str, customer: str = ""):
    """Generate a customer call briefing."""
    print(f"Preparing call briefing for: {query}\n")
    if customer:
        print(f"Customer: {customer}\n")

    start_time = time.time()
    config = {"configurable": {"thread_id": f"prep-{int(start_time)}"}}
    result = await prep_graph.ainvoke(
        {
            "messages": [HumanMessage(content=query)],
            "topic": query,
            "customer": customer,
            "context": [],
            "briefing": "",
        },
        config,
    )
    duration_ms = int((time.time() - start_time) * 1000)

    briefing = result.get("briefing", result["messages"][-1].content)

    print("\n" + "=" * 60)
    print("CALL BRIEFING:")
    print("=" * 60)
    print(briefing)

    # Track metrics
    tracker = get_tracker()
    tracker.record_query(
        query_type="prep",
        query_text=query,
        duration_ms=duration_ms,
    )


async def run_session_diff(days: int = 1):
    """Generate a session diff report."""
    print(f"Generating session diff for last {days} day(s)...\n")

    start_time = time.time()
    config = {"configurable": {"thread_id": f"diff-{int(start_time)}"}}
    result = await diff_graph.ainvoke(
        {
            "messages": [HumanMessage(content="Generate session diff")],
            "days": days,
            "current_stats": {},
            "recent_queries": [],
            "diff_report": "",
        },
        config,
    )
    duration_ms = int((time.time() - start_time) * 1000)

    report = result.get("diff_report", result["messages"][-1].content)

    print("\n" + "=" * 60)
    print("SESSION DIFF:")
    print("=" * 60)
    print(report)

    # Track metrics
    tracker = get_tracker()
    tracker.record_query(
        query_type="session_diff",
        query_text=f"session_diff:{days}d",
        duration_ms=duration_ms,
    )


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


def run_metrics(days: int = 30):
    """Show cost metrics report."""
    print(format_report(days))


def main():
    parser = argparse.ArgumentParser(description="Run LangGraph workflows with Mimir")
    subparsers = parser.add_subparsers(dest="command", help="Workflow to run")

    rag_parser = subparsers.add_parser("rag", help="Run RAG workflow")
    rag_parser.add_argument("query", help="Query to search")

    agent_parser = subparsers.add_parser("agent", help="Run Knowledge Agent workflow")
    agent_parser.add_argument("query", help="Query to search")

    subparsers.add_parser("test", help="Run workflow tests")

    # Add metrics subcommand
    metrics_parser = subparsers.add_parser("metrics", help="Show cost metrics report")
    metrics_parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to include in report (default: 30)",
    )

    # Call prep subcommand
    prep_parser = subparsers.add_parser("prep", help="Generate customer call briefing")
    prep_parser.add_argument("topic", help="Call topic (e.g., 'video latency issues')")
    prep_parser.add_argument("--customer", default="", help="Customer name")

    # Session diff subcommand
    diff_parser = subparsers.add_parser(
        "session-diff", help="Compare current state to previous session"
    )
    diff_parser.add_argument(
        "--days", type=int, default=1, help="Days to look back (default: 1)"
    )

    args = parser.parse_args()

    if args.command == "rag":
        asyncio.run(run_rag(args.query))
    elif args.command == "agent":
        asyncio.run(run_agent(args.query))
    elif args.command == "test":
        asyncio.run(run_test())
    elif args.command == "metrics":
        run_metrics(args.days)
    elif args.command == "prep":
        asyncio.run(run_prep(args.topic, args.customer))
    elif args.command == "session-diff":
        asyncio.run(run_session_diff(args.days))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
