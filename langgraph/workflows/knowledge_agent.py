"""
Knowledge Agent Workflow for Mimir.

An agentic workflow that can decide whether to search, query, or respond
directly based on the user's question.
"""

from typing import Annotated, TypedDict, Literal
from pathlib import Path
import os
import json

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_mcp_adapters.client import MultiServerMCPClient


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    knowledge_stats: dict


def detect_project_root() -> Path:
    """Detect project root."""
    for env_var in ["PROJECT_ROOT", "WORKSPACE_FOLDER"]:
        if path := os.environ.get(env_var):
            return Path(path).resolve()

    cwd = Path.cwd().resolve()
    markers = ["opencode.json", ".opencode", ".git"]

    current = cwd
    while current != current.parent:
        if any((current / marker).exists() for marker in markers):
            return current
        current = current.parent

    return cwd


async def check_knowledge(state: AgentState) -> AgentState:
    """Check knowledge base stats before querying."""
    project_root = detect_project_root()
    server_path = project_root / "mcp_server_llamaindex.py"

    try:
        async with MultiServerMCPClient(
            {
                "llamaindex": {
                    "command": ["python", str(server_path)],
                    "transport": "stdio",
                    "env": {"PROJECT_ROOT": str(project_root)},
                }
            }
        ) as client:
            tools = await client.get_tools()
            stats_tool = next((t for t in tools if t.name == "stats"), None)

            if stats_tool:
                result = await stats_tool.ainvoke({})
                stats = json.loads(result)
                return {**state, "knowledge_stats": stats}
    except Exception:
        pass

    return {**state, "knowledge_stats": {"has_index": False}}


async def agent(state: AgentState) -> AgentState:
    """The knowledge agent that decides what to do."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    stats = state.get("knowledge_stats", {})
    has_index = stats.get("has_index", False)

    if not has_index:
        return {
            **state,
            "messages": [
                AIMessage(
                    content="No knowledge base found. Run `python mcp_server_llamaindex.py --index` to create one."
                )
            ],
        }

    system_prompt = f"""You are the Knowledge Agent. You have access to a knowledge base with:
- Project root: {stats.get("project_root", "unknown")}
- Documents: {stats.get("source_files", 0)} source files
- Indexed chunks: {stats.get("document_count", 0)}

Use the search or query tools to find information. Be concise and cite sources."""

    project_root = detect_project_root()
    server_path = project_root / "mcp_server_llamaindex.py"

    async with MultiServerMCPClient(
        {
            "llamaindex": {
                "command": ["python", str(server_path)],
                "transport": "stdio",
                "env": {"PROJECT_ROOT": str(project_root)},
            }
        }
    ) as client:
        tools = await client.get_tools()
        llm_with_tools = llm.bind_tools(tools)

        response = await llm_with_tools.ainvoke(
            [HumanMessage(content=system_prompt)] + state["messages"]
        )

        return {**state, "messages": [response]}


def should_continue(state: AgentState) -> Literal["agent", "__end__"]:
    """Determine if we should continue or end."""
    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls:
        return "agent"

    return END


def create_graph():
    """Create the knowledge agent workflow."""
    workflow = StateGraph(AgentState)

    workflow.add_node("check", check_knowledge)
    workflow.add_node("agent", agent)

    workflow.set_entry_point("check")
    workflow.add_edge("check", "agent")
    workflow.add_conditional_edges(
        "agent", should_continue, {"agent": "agent", "__end__": END}
    )

    return workflow.compile(checkpointer=MemorySaver())


graph = create_graph()
