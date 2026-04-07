"""Session diff workflow.

Compares the current knowledge base state to a previous session,
showing what was learned, what changed, and what to focus on next.

Usage:
    python langgraph/cli.py session-diff
    python langgraph/cli.py session-diff --days 1
"""

from typing import Annotated, TypedDict, Optional
from pathlib import Path
from datetime import datetime, timedelta
import json

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from .utils import create_llm, detect_project_root, get_mcp_client
from src.mimir.token_callback import create_token_callback


class SessionDiffState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    days: int
    current_stats: dict
    recent_queries: list
    diff_report: str


async def gather_current_state(state: SessionDiffState) -> SessionDiffState:
    """Gather current knowledge base state."""
    project_root = detect_project_root()
    client = get_mcp_client(project_root)
    tools = await client.get_tools()

    current_stats = {}
    recent_queries = []

    # Get stats
    stats_tool = next((t for t in tools if t.name == "stats"), None)
    if stats_tool:
        result = await stats_tool.ainvoke({})
        if isinstance(result, dict):
            current_stats = result
        elif isinstance(result, str):
            try:
                current_stats = json.loads(result)
            except json.JSONDecodeError:
                current_stats = {"raw": result}

    # Get recent metrics
    try:
        from src.mimir.metrics import get_tracker

        tracker = get_tracker(project_root)
        summary = tracker.get_summary(days=state.get("days", 1))
        recent_queries = summary.get("by_type", {})
    except Exception:
        pass

    return {
        **state,
        "current_stats": current_stats,
        "recent_queries": recent_queries,
    }


async def generate_diff_report(state: SessionDiffState) -> SessionDiffState:
    """Generate a session diff report."""
    token_callback = create_token_callback()
    llm = create_llm(temperature=0, callbacks=[token_callback])

    stats = state.get("current_stats", {})
    queries = state.get("recent_queries", {})
    days = state.get("days", 1)

    prompt = f"""You are analyzing what an FDE learned in their recent work sessions.

Knowledge Base Stats:
{json.dumps(stats, indent=2)}

Recent Query Activity (last {days} days):
{json.dumps(queries, indent=2)}

Generate a session diff report with these sections:

## Session Diff: Last {days} Day(s)

### 1. Knowledge Base Status
- How many documents are indexed?
- What's the coverage? (docs vs code)
- Is the index fresh or stale?

### 2. Activity Summary
- What types of queries were run?
- What was the cost?
- What patterns emerge from the query history?

### 3. What You Learned
Based on the stats and query patterns, what topics were explored?
What areas of the codebase were investigated?

### 4. What Changed
If there were recent indexing runs, what's new?
What files were added or modified?

### 5. Focus Areas for Next Session
Based on what you see, what should the FDE focus on next?
What gaps remain in the knowledge base?

### 6. Recommendations
- Should the index be refreshed?
- Are there missing code directories?
- What would make the next session more productive?

Be concise and actionable. This is a quick briefing, not a deep analysis."""

    response = await llm.ainvoke([HumanMessage(content=prompt)])

    return {
        **state,
        "messages": [AIMessage(content=response.content)],
        "diff_report": response.content,
    }


def create_graph():
    workflow = StateGraph(SessionDiffState)

    workflow.add_node("gather", gather_current_state)
    workflow.add_node("diff", generate_diff_report)

    workflow.set_entry_point("gather")
    workflow.add_edge("gather", "diff")
    workflow.add_edge("diff", END)

    return workflow.compile(checkpointer=MemorySaver())


graph = create_graph()
