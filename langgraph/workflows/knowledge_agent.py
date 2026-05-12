import json
from typing import Annotated, Literal, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from .utils import create_llm, detect_project_root, get_mcp_client


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    knowledge_stats: dict
    mcp_client: Optional[object]  # Store client in state for reuse


async def cleanup_client(state: AgentState):
    """Clean up MCP client if it exists in state."""
    client = state.get("mcp_client")
    if client and hasattr(client, 'close'):
        try:
            await client.close()
        except Exception as e:
            print(f"[Knowledge Agent] Error closing MCP client: {e}")


async def check_knowledge(state: AgentState) -> AgentState:
    project_root = detect_project_root()
    client = get_mcp_client(project_root)

    try:
        tools = await client.get_tools()
        stats_tool = next((t for t in tools if t.name == "stats"), None)

        if stats_tool:
            result = await stats_tool.ainvoke({})
            if isinstance(result, str):
                stats = json.loads(result)
            elif isinstance(result, list) and len(result) > 0:
                item = result[0]
                if isinstance(item, dict) and "text" in item:
                    stats = json.loads(item["text"])
                elif isinstance(item, dict):
                    stats = item
                else:
                    stats = {"has_index": False}
            elif isinstance(result, dict):
                stats = result
            else:
                stats = {"has_index": False}
            return {**state, "knowledge_stats": stats, "mcp_client": client}
    except Exception as e:
        print(f"[Knowledge Agent] Error checking knowledge base: {e}")

    return {**state, "knowledge_stats": {"has_index": False}, "mcp_client": client}


async def agent(state: AgentState) -> AgentState:
    llm = create_llm(temperature=0)

    stats = state.get("knowledge_stats", {})
    has_index = stats.get("has_index", False)

    if not has_index:
        await cleanup_client(state)
        return {
            **state,
            "messages": [
                AIMessage(
                    content="No knowledge base found. Run `python .opencode/setup.py` to create one."
                )
            ],
        }

    system_prompt = f"""You are the Knowledge Agent. You have access to a knowledge base with:
- Project root: {stats.get("project_root", "unknown")}
- Documents: {stats.get("source_files", 0)} source files
- Indexed chunks: {stats.get("document_count", 0)}

Use the search or query tools to find information. Be concise and cite sources."""

    client = state.get("mcp_client")
    if not client:
        project_root = detect_project_root()
        client = get_mcp_client(project_root)

    tools = await client.get_tools()
    llm_with_tools = llm.bind_tools(tools)

    response = await llm_with_tools.ainvoke(
        [HumanMessage(content=system_prompt)] + state["messages"]
    )

    return {**state, "messages": [response], "mcp_client": client}


async def execute_tools(state: AgentState) -> AgentState:
    last_message = state["messages"][-1]

    if not last_message.tool_calls:
        return state

    client = state.get("mcp_client")
    if not client:
        project_root = detect_project_root()
        client = get_mcp_client(project_root)

    tools = await client.get_tools()
    tools_by_name = {tool.name: tool for tool in tools}

    tool_messages = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]

        if tool_name in tools_by_name:
            try:
                tool = tools_by_name[tool_name]
                result = await tool.ainvoke(tool_args)
                if (
                    isinstance(result, list)
                    and len(result) > 0
                    and isinstance(result[0], dict)
                    and "text" in result[0]
                ):
                    content = result[0]["text"]
                else:
                    content = str(result)
                tool_messages.append(ToolMessage(content=content, tool_call_id=tool_id))
            except Exception as e:
                tool_messages.append(
                    ToolMessage(content=f"Error: {e}", tool_call_id=tool_id)
                )
        else:
            tool_messages.append(
                ToolMessage(content=f"Tool {tool_name} not found", tool_call_id=tool_id)
            )

    return {**state, "messages": tool_messages, "mcp_client": client}


def should_continue(state: AgentState) -> Literal["execute_tools", "cleanup", "__end__"]:
    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls:
        return "execute_tools"

    return "cleanup"


async def cleanup(state: AgentState) -> AgentState:
    """Cleanup node to close MCP client."""
    await cleanup_client(state)
    return state


def create_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("check", check_knowledge)
    workflow.add_node("agent", agent)
    workflow.add_node("execute_tools", execute_tools)
    workflow.add_node("cleanup", cleanup)

    workflow.set_entry_point("check")
    workflow.add_edge("check", "agent")
    workflow.add_conditional_edges(
        "agent", should_continue, {"execute_tools": "execute_tools", "cleanup": "cleanup", "__end__": END}
    )
    workflow.add_edge("execute_tools", "agent")
    workflow.add_edge("cleanup", END)

    return workflow.compile(checkpointer=MemorySaver())


graph = create_graph()
