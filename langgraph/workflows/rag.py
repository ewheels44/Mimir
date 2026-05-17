from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from src.mimir.token_callback import create_token_callback

from .utils import create_llm, detect_project_root, get_mcp_client


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    context: list[str]
    token_usage: dict
    query_text: str  # Store the original query for metrics
    response_shape: str  # Optional JSON schema for structured output (KnowQL-inspired)
    metrics_recorded: bool  # Track if we've recorded metrics


async def retrieve(state: AgentState) -> AgentState:
    last_message = state["messages"][-1].content
    project_root = detect_project_root()
    client = get_mcp_client(project_root)

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
        return {**state, "context": context_items, "query_text": last_message, "response_shape": state.get("response_shape")}

    return {**state, "context": [], "query_text": last_message, "response_shape": state.get("response_shape")}


async def generate(state: AgentState) -> AgentState:
    # Create token callback to capture actual usage
    token_callback = create_token_callback()
    llm = create_llm(
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

    # If response_shape is provided, modify the prompt to request structured output
    response_shape = state.get("response_shape")
    if response_shape:
        system_msg += f"""

IMPORTANT: Return your answer as a JSON object matching this schema:
{response_shape}

Return ONLY the JSON object, no other text."""

    response = await llm.ainvoke([HumanMessage(content=system_msg)] + messages)

    # Store token usage in state for metrics tracking
    new_state = {**state, "messages": [AIMessage(content=response.content)]}
    token_usage = token_callback.get_usage()
    new_state["token_usage"] = token_usage
    new_state["token_usage"]["has_actual_data"] = token_callback.has_data

    # Record metrics
    try:
        from src.mimir.metrics import get_tracker

        tracker = get_tracker()
        usage = token_callback.get_usage()

        # Convert to the format metrics.py expects
        actual_tokens = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "embedding_tokens": usage.get("embedding_tokens", 0),
        }

        # Get original query from state
        query_text = state.get("query_text", "unknown")

        tracker.record_query(
            query_type="rag",
            query_text=query_text,
            actual_tokens=actual_tokens if token_callback.has_data else None,
        )
        new_state["metrics_recorded"] = True
    except Exception as e:
        print(f"[RAG Workflow] Warning: Failed to record metrics: {e}")
        new_state["metrics_recorded"] = False

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
