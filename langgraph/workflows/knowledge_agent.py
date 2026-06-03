from typing import Annotated, Literal, Optional, TypedDict

import logging
from pathlib import Path
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from .bridge_client import get_tools as bridge_get_tools
from .utils import create_llm, detect_project_root

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    knowledge_stats: dict
    tool_call_count: int  # Track number of tool call rounds


async def cleanup_client(state: AgentState):
    """Clean up MCP client if it exists in state."""
    # ToolsAdapter doesn't need cleanup (no persistent connections)
    logger.debug("[KNOWLEDGE_AGENT] cleanup_client called")
    pass


async def check_knowledge(state: AgentState) -> AgentState:
    """Check knowledge base availability and stats using direct API."""
    logger.info("[KNOWLEDGE_AGENT] Checking knowledge base availability...")
    # Reset tool call counter
    state = {**state, "tool_call_count": 0}
    try:
        # Use the bridge_client's server singleton so shared across workflow
        from .bridge_client import _get_server as _get_bridge_server

        server = _get_bridge_server()
        from mimir.config import get_config

        config = get_config()

        # Quick existence check without loading full index
        knowledge_dir = config.knowledge_dir
        has_index = (knowledge_dir / "index_store.json").exists()
        logger.debug("[KNOWLEDGE_AGENT] has_index=%s, knowledge_dir=%s", has_index, knowledge_dir)

        stats = {
            "project_root": str(config.project_root),
            "knowledge_dir": str(config.knowledge_dir),
            "docs_dir": str(config.docs_dir),
            "code_dirs": [str(d) for d in config.code_dirs],
            "has_index": has_index,
        }

        if has_index:
            try:
                full_stats = server.get_stats()
                stats["document_count"] = full_stats.get("document_count", "unknown")
                logger.info("[KNOWLEDGE_AGENT] Knowledge base has %d documents", 
                            full_stats.get("document_count", 0))
            except Exception as e:
                logger.warning("[KNOWLEDGE_AGENT] Could not get full stats: %s", e)
                stats["document_count"] = "unknown"

        total_source_files = 0
        # Count files respecting exclude_patterns
        import fnmatch
        exclude_patterns = config.exclude_patterns
        
        def should_exclude(path: Path) -> bool:
            """Check if path matches any exclude pattern."""
            path_str = str(path)
            # Check if any part of the path matches the pattern
            for pattern in exclude_patterns:
                # Check against full path
                if fnmatch.fnmatch(path_str, pattern):
                    return True
                # Check against each path component
                for part in path.parts:
                    if fnmatch.fnmatch(part, pattern):
                        return True
                # Check against filename
                if fnmatch.fnmatch(path.name, pattern):
                    return True
            return False
        
        if config.docs_dir.exists():
            total_source_files += len([f for f in config.docs_dir.rglob("*") if f.is_file() and not should_exclude(f)])
        for code_dir in config.code_dirs:
            if code_dir.exists():
                total_source_files += len([f for f in code_dir.rglob("*") if f.is_file() and not should_exclude(f)])
        stats["source_files"] = total_source_files
        logger.debug("[KNOWLEDGE_AGENT] Source files: %d", total_source_files)

        return {**state, "knowledge_stats": stats}
    except Exception as e:
        logger.error("[KNOWLEDGE_AGENT] Error checking knowledge base: %s", e)

    return {**state, "knowledge_stats": {"has_index": False}}


async def agent(state: AgentState) -> AgentState:
    logger.info("[KNOWLEDGE_AGENT] Agent invoked, generating response...")
    llm = create_llm(temperature=0)

    stats = state.get("knowledge_stats", {})
    has_index = stats.get("has_index", False)
    logger.debug("[KNOWLEDGE_AGENT] has_index=%s, docs=%s", 
                 has_index, stats.get("source_files", 0))

    if not has_index:
        logger.warning("[KNOWLEDGE_AGENT] No knowledge base - returning error message")
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
- Knowledge base path: {stats.get("knowledge_dir", "unknown")}
- Indexed chunks: {stats.get("document_count", 0)}
- Source files (raw): {stats.get("source_files", 0)}

Use the tools to find information. Be concise and cite sources.

IMPORTANT INSTRUCTIONS:
1. If a tool returns "not mentioned", "not found", or indicates the information is not in the knowledge base, DO NOT try another similar tool. Instead, clearly state: "The knowledge base does not contain information about [topic]."
2. If both search and query tools return irrelevant or no results, STOP calling tools and report that the information is not available.
3. Do NOT hallucinate or fabricate answers. Only use information returned by the tools.
4. Maximum tool call rounds: 3. After that, provide the best answer with available information.
5. When you have sufficient information to answer, respond directly WITHOUT calling more tools.

TOOL USAGE GUIDE:
- Use `read_file` to read specific files (README.md, config files, etc.) - most reliable for known filenames
- Use `query` for direct questions (returns synthesized answers)
- Use `search` for finding specific code/documentation snippets
- Use `stats` to check knowledge base statistics (no need to search after this)"""
    logger.debug("[KNOWLEDGE_AGENT] System prompt length: %d chars", len(system_prompt))

    tools = bridge_get_tools()
    logger.debug("[KNOWLEDGE_AGENT] Available tools: %s", [t.name for t in tools])
    llm_with_tools = llm.bind_tools(tools)

    response = await llm_with_tools.ainvoke(
        [HumanMessage(content=system_prompt)] + state["messages"]
    )
    logger.info("[KNOWLEDGE_AGENT] Response generated (content length: %d)", 
                 len(response.content) if hasattr(response, 'content') else 0)

    return {**state, "messages": [response]}


async def execute_tools(state: AgentState) -> AgentState:
    last_message = state["messages"][-1]
    logger.info("[KNOWLEDGE_AGENT] Executing tools...")

    if not last_message.tool_calls:
        logger.debug("[KNOWLEDGE_AGENT] No tool calls found")
        return state

    tools = bridge_get_tools()
    tools_by_name = {tool.name: tool for tool in tools}
    logger.debug("[KNOWLEDGE_AGENT] Available tools: %s", [t.name for t in tools])

    tool_messages = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]
        logger.debug("[KNOWLEDGE_AGENT] Calling tool: %s with args: %s", tool_name, tool_args)

        if tool_name in tools_by_name:
            try:
                tool = tools_by_name[tool_name]
                result = await tool.ainvoke(tool_args)
                logger.debug("[KNOWLEDGE_AGENT] Tool %s returned: %s...", tool_name, str(result)[:100])
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
                logger.error("[KNOWLEDGE_AGENT] Tool %s failed: %s", tool_name, e)
                tool_messages.append(
                    ToolMessage(content=f"Error: {e}", tool_call_id=tool_id)
                )
        else:
            logger.warning("[KNOWLEDGE_AGENT] Tool %s not found!", tool_name)
            tool_messages.append(
                ToolMessage(content=f"Tool {tool_name} not found", tool_call_id=tool_id)
            )

    logger.info("[KNOWLEDGE_AGENT] Executed %d tool call(s)", len(tool_messages))
    # Increment tool call counter (return new state to avoid mutation issues)
    return {
        **state,
        "tool_call_count": state.get("tool_call_count", 0) + 1,
        "messages": tool_messages,
    }


def should_continue(state: AgentState) -> Literal["execute_tools", "__end__"]:
    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls:
        # Check if we've exceeded max tool call rounds
        tool_call_count = state.get("tool_call_count", 0)
        if tool_call_count >= 3:
            logger.warning(
                "[KNOWLEDGE_AGENT] Max tool call rounds (3) reached, stopping."
            )
            return "__end__"
        return "execute_tools"

    return "__end__"


def create_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("check", check_knowledge)
    workflow.add_node("agent", agent)
    workflow.add_node("execute_tools", execute_tools)

    workflow.set_entry_point("check")
    workflow.add_edge("check", "agent")
    workflow.add_conditional_edges(
        "agent", should_continue, {"execute_tools": "execute_tools", "__end__": END}
    )
    workflow.add_edge("execute_tools", "agent")

    return workflow.compile(checkpointer=MemorySaver())


graph = create_graph()
