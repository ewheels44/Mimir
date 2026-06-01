"""Customer call preparation workflow.

Generates a structured briefing for an FDE preparing for a customer call.
Searches the knowledge base for relevant code, patterns, and integration points.

Usage:
    python langgraph/cli.py prep "video latency issues"
    python langgraph/cli.py prep "payment integration" --customer acme-corp
"""

import logging
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from src.mimir.token_callback import create_token_callback

from .utils import create_llm, detect_project_root, get_mcp_client

logger = logging.getLogger(__name__)


class PrepState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    topic: str
    customer: str
    context: list[str]
    briefing: str


async def search_codebase(state: PrepState) -> PrepState:
    """Search the knowledge base for code relevant to the topic."""
    topic = state["topic"]
    customer = state.get("customer", "")
    logger.info("[CALL_PREP] Searching codebase for topic: '%s' (customer: %s)", topic, customer)

    project_root = detect_project_root()
    client = get_mcp_client(project_root)
    tools = await client.get_tools()
    logger.debug("[CALL_PREP] MCP client tools: %s", [t.name for t in tools])

    context_items = []

    # Search for the topic
    search_tool = next((t for t in tools if t.name == "search"), None)
    if search_tool:
        logger.debug("[CALL_PREP] Running search tool with top_k=8")
        results = await search_tool.ainvoke({"query": topic, "top_k": 8})
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict) and "text" in item:
                    context_items.append(item["text"])
                else:
                    context_items.append(str(item))
        else:
            context_items.append(str(results))
        logger.info("[CALL_PREP] Search returned %d context items", len(context_items))
    else:
        logger.warning("[CALL_PREP] No search tool found!")

    # Also search for integration patterns
    query_tool = next((t for t in tools if t.name == "query"), None)
    if query_tool:
        integration_query = f"How to integrate {topic} in this codebase? What are the key files and patterns?"
        logger.debug("[CALL_PREP] Running query tool: '%s'", integration_query)
        result = await query_tool.ainvoke({"question": integration_query})
        if result:
            context_items.append(f"Integration analysis:\n{result}")
            logger.debug("[CALL_PREP] Query tool returned result")

    logger.info("[CALL_PREP] Total context items collected: %d", len(context_items))
    return {**state, "context": context_items}


async def generate_briefing(state: PrepState) -> PrepState:
    """Generate a structured call briefing from the context."""
    logger.info("[CALL_PREP] Generating call briefing...")
    token_callback = create_token_callback()
    llm = create_llm(temperature=0, callbacks=[token_callback])

    topic = state["topic"]
    customer = state.get("customer", "the customer")
    context = "\n\n---\n\n".join(state.get("context", []))
    logger.debug("[CALL_PREP] Topic: '%s', Customer: %s, Context: %d chars", 
                 topic, customer, len(context))

    prompt = f"""You are an FDE (Forward Deployed Engineer) preparing for a customer call.

Topic: {topic}
Customer: {customer}

Based on the following codebase context, generate a structured call briefing.

Context from knowledge base:
{context}

Generate a briefing with these sections:

## Call Prep: {topic}

### 1. Relevant Code Sections
List the key files and functions related to this topic. For each, note what it does and why it matters for the call.

### 2. Known Patterns
What patterns does this codebase use for this type of functionality? What's the established approach?

### 3. Questions to Ask the Customer
Based on what you see in the code, what clarifying questions should you ask? Think about:
- What's unclear about their requirements?
- What assumptions might be wrong?
- What edge cases should you discuss?

### 4. Common Pitfalls
Based on the codebase patterns, what could go wrong? What are the integration risks?

### 5. Proposed Approach
Given what you know, what would you recommend? Keep it high-level — this is prep, not implementation.

### 6. Things to Verify
What should you check during the call? What demos or proofs of concept would be valuable?

Be specific. Reference actual file names and function names from the context. This briefing should let you walk into the call confident and prepared."""

    logger.debug("[CALL_PREP] Prompt length: %d chars", len(prompt))
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    logger.info("[CALL_PREP] Briefing generated: %d chars", 
                 len(response.content) if hasattr(response, 'content') else 0)

    return {
        **state,
        "messages": [AIMessage(content=response.content)],
        "briefing": response.content,
    }


def create_graph():
    logger.info("[CALL_PREP] Creating call prep workflow graph...")
    workflow = StateGraph(PrepState)

    workflow.add_node("search", search_codebase)
    workflow.add_node("brief", generate_briefing)

    workflow.set_entry_point("search")
    workflow.add_edge("search", "brief")
    workflow.add_edge("brief", END)

    graph = workflow.compile(checkpointer=MemorySaver())
    logger.info("[CALL_PREP] Graph compiled successfully")
    return graph


graph = create_graph()
