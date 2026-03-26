"""
RAG Workflow for Mimir Knowledge Base.

A LangGraph workflow that retrieves information from the project knowledge base
using MCP tools, then synthesizes responses.
"""

from typing import Annotated, TypedDict
from pathlib import Path
import os

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_mcp_adapters.client import MultiServerMCPClient


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    context: list[str]
    should_retrieve: bool


@tool
def search_knowledge(query: str, top_k: int = 5) -> str:
    """Search the knowledge base."""
    return f"Searching for: {query}"


@tool
def query_knowledge(question: str) -> str:
    """Ask a question of the knowledge base."""
    return f"Querying: {question}"


async def detect_project_root() -> Path:
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


async def retrieve(state: AgentState) -> AgentState:
    """Retrieve relevant documents from knowledge base."""
    last_message = state["messages"][-1].content

    project_root = await detect_project_root()
    server_path = project_root / "mcp_server_llamaindex.py"

    async with MultiServerMCPClient(
        {
            "llamaindex": {
                "command": ["python", str(server_path)],
                "transport": "stdio",
                "env": {
                    "PROJECT_ROOT": str(project_root),
                    "KNOWLEDGE_DIR": str(project_root / ".knowledge" / "llamaindex"),
                    "DOCS_DIR": str(project_root / "docs"),
                },
            }
        }
    ) as client:
        tools = await client.get_tools()

        search_tool = next((t for t in tools if t.name == "search"), None)

        if search_tool:
            results = await search_tool.ainvoke({"query": last_message, "top_k": 5})
            return {**state, "context": [results], "should_retrieve": False}

    return {**state, "context": [], "should_retrieve": False}


def should_retrieve(state: AgentState) -> str:
    """Determine if we need to retrieve from knowledge base."""
    if state.get("should_retrieve", True):
        return "retrieve"
    return "generate"


async def generate(state: AgentState) -> AgentState:
    """Generate response using retrieved context."""
    llm = ChatOpenAI(model="openai/gpt-5.4-nano", temperature=0)

    context = "\n\n".join(state.get("context", []))
    messages = state["messages"]

    prompt = f"""You are the Librarian. Use the following context to answer the user's question.

Context from knowledge base:
{context}

Answer the user's question based on this context. If the context doesn't contain the answer, say so clearly."""

    response = await llm.ainvoke([HumanMessage(content=prompt)] + messages)

    return {**state, "messages": [AIMessage(content=response.content)]}


def create_graph():
    """Create the RAG workflow graph."""
    workflow = StateGraph(AgentState)

    workflow.add_node("retrieve", retrieve)
    workflow.add_node("generate", generate)

    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)

    return workflow.compile(checkpointer=MemorySaver())


graph = create_graph()
