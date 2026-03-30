from typing import Annotated, TypedDict
from pathlib import Path

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_mcp_adapters.client import MultiServerMCPClient

from .utils import create_llm, get_mcp_server_path, get_mcp_env, detect_project_root
from src.mimir.token_callback import create_token_callback, TokenUsageCallbackHandler


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    context: list[str]
    token_usage: dict


async def retrieve(state: AgentState) -> AgentState:
    last_message = state["messages"][-1].content
    project_root = detect_project_root()
    server_path = get_mcp_server_path()
    env = get_mcp_env(project_root)

    client = MultiServerMCPClient(
        {
            "llamaindex": {
                "command": "python",
                "args": [str(server_path)],
                "transport": "stdio",
                "env": env,
            }
        }
    )
    tools = await client.get_tools()
    search_tool = next((t for t in tools if t.name == "search"), None)

    if search_tool:
        results = await search_tool.ainvoke({"query": last_message, "top_k": 5})
        context_items = []
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict) and "text" in item:
                    context_items.append(item["text"])
                else:
                    context_items.append(str(item))
        else:
            context_items.append(str(results))
        return {**state, "context": context_items}

    return {**state, "context": []}


async def generate(state: AgentState) -> AgentState:
    # Create token callback to capture actual usage
    token_callback = create_token_callback()
    llm = create_llm(
        model="google/gemini-3.1-flash-lite-preview",
        temperature=0,
        callbacks=[token_callback],
    )

    raw_context = state.get("context", [])
    context_items = [
        str(item) if not isinstance(item, str) else item for item in raw_context
    ]
    context = "\n\n".join(context_items)
    messages = state["messages"]

    system_msg = f"""You are the Librarian. Use the following context to answer the user's question.

Context from knowledge base:
{context}

Answer based on this context. If the context doesn't contain the answer, say so clearly."""

    response = await llm.ainvoke([HumanMessage(content=system_msg)] + messages)

    # Store token usage in state for metrics tracking
    new_state = {**state, "messages": [AIMessage(content=response.content)]}
    new_state["token_usage"] = token_callback.get_usage()
    new_state["token_usage"]["has_actual_data"] = token_callback.has_data

    return new_state


def create_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("retrieve", retrieve)
    workflow.add_node("generate", generate)

    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)

    return workflow.compile(checkpointer=MemorySaver())


graph = create_graph()
