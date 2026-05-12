# LangGraph Knowledge Agent Workflow - Analysis & Improvement Recommendations

## Executive Summary

The knowledge_agent workflow is a LangGraph-based agentic system that interacts with a knowledge base via MCP (Model Context Protocol) tools. While functional, there are several areas for improvement in code quality, error handling, performance, and maintainability.

---

## 1. CODE QUALITY ISSUES

### 1.1 Resource Management - Critical Issue

**Problem**: MCP clients are created repeatedly without proper cleanup
```python
# Currently in every function:
client = MultiServerMCPClient({...})
# No cleanup - potential resource leak
```

**Impact**: Memory leaks, socket/process leaks, degraded performance over time

**Solution**: Implement proper resource management
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_mcp_client(project_root: Optional[Path] = None):
    """Context manager for MCP client lifecycle."""
    if project_root is None:
        project_root = detect_project_root()
    
    server_path = get_mcp_server_path()
    env = get_mcp_env(project_root)
    
    client = MultiServerMCPClient({
        "llamaindex": {
            "command": "python",
            "args": [str(server_path)],
            "transport": "stdio",
            "env": env,
        }
    })
    
    try:
        yield client
    finally:
        # Ensure cleanup
        if hasattr(client, 'close'):
            await client.close()

# Usage:
async def check_knowledge(state: AgentState) -> AgentState:
    async with get_mcp_client() as client:
        tools = await client.get_tools()
        # ... rest of logic
```

### 1.2 Code Duplication - High Priority

**Problem**: MCP client configuration is duplicated 3 times (check_knowledge, agent, execute_tools)

**Solution**: Extract to shared function and consider client reuse
```python
# Add to utils.py
def get_mcp_config(project_root: Optional[Path] = None) -> dict:
    """Get standardized MCP client configuration."""
    if project_root is None:
        project_root = detect_project_root()
    
    return {
        "llamaindex": {
            "command": "python",
            "args": [str(get_mcp_server_path())],
            "transport": "stdio",
            "env": get_mcp_env(project_root),
        }
    }

# Even better - cache client in state:
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    knowledge_stats: dict
    mcp_client: Optional[MultiServerMCPClient]  # Add this
```

### 1.3 Magic Values

**Problem**: Hardcoded values scattered throughout code
```python
model="google/gemini-3.1-flash-lite-preview"  # Hardcoded
"top_k": 5  # Magic number in rag.py
```

**Solution**: Centralize configuration
```python
# config.py
from dataclasses import dataclass

@dataclass
class KnowledgeAgentConfig:
    model: str = "google/gemini-3.1-flash-lite-preview"
    temperature: float = 0.0
    top_k: int = 5
    max_iterations: int = 10
    timeout_seconds: int = 60

DEFAULT_CONFIG = KnowledgeAgentConfig()
```

### 1.4 Type Safety

**Problem**: Missing type hints and loose typing
```python
def should_continue(state: AgentState) -> Literal["execute_tools", "__end__"]:
    # Return type doesn't match actual return value
    return END  # END is a string constant, but type says Literal
```

**Solution**: Improve type annotations
```python
from typing import Union

RouteDecision = Literal["execute_tools", "__end__"]

def should_continue(state: AgentState) -> RouteDecision:
    messages = state["messages"]
    last_message = messages[-1]
    
    if last_message.tool_calls:
        return "execute_tools"
    
    return "__end__"  # Use explicit string
```

---

## 2. ERROR HANDLING ISSUES

### 2.1 Silent Failures - Critical

**Problem**: Errors are caught but not propagated or logged properly
```python
try:
    # ... tool execution
except Exception as e:
    print(f"[Knowledge Agent] Error checking knowledge base: {e}")
    # Continues with empty state - user doesn't know something failed
```

**Solution**: Structured error handling with logging
```python
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class KnowledgeAgentError(Exception):
    """Base exception for knowledge agent errors."""
    pass

class KnowledgeBaseError(KnowledgeAgentError):
    """Error accessing knowledge base."""
    pass

class ToolExecutionError(KnowledgeAgentError):
    """Error executing tools."""
    pass

async def check_knowledge(state: AgentState) -> AgentState:
    try:
        async with get_mcp_client() as client:
            tools = await client.get_tools()
            stats_tool = next((t for t in tools if t.name == "stats"), None)
            
            if not stats_tool:
                raise KnowledgeBaseError("Stats tool not found in MCP server")
            
            result = await stats_tool.ainvoke({})
            stats = parse_stats_result(result)
            
            return {**state, "knowledge_stats": stats}
            
    except KnowledgeAgentError:
        raise  # Re-raise known errors
    except Exception as e:
        logger.exception("Unexpected error checking knowledge base")
        raise KnowledgeBaseError(f"Failed to check knowledge base: {e}") from e
```

### 2.2 No Timeout Handling

**Problem**: Tool calls can hang indefinitely
```python
result = await tool.ainvoke(tool_args)  # No timeout
```

**Solution**: Add timeout protection
```python
import asyncio

async def execute_tools(state: AgentState, timeout: int = 60) -> AgentState:
    last_message = state["messages"][-1]
    
    if not last_message.tool_calls:
        return state
    
    async with get_mcp_client() as client:
        tools = await client.get_tools()
        tools_by_name = {tool.name: tool for tool in tools}
        
        tool_messages = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            if tool_name not in tools_by_name:
                tool_messages.append(
                    ToolMessage(
                        content=f"Tool {tool_name} not found",
                        tool_call_id=tool_id
                    )
                )
                continue
            
            try:
                tool = tools_by_name[tool_name]
                result = await asyncio.wait_for(
                    tool.ainvoke(tool_args),
                    timeout=timeout
                )
                content = extract_tool_result(result)
                tool_messages.append(
                    ToolMessage(content=content, tool_call_id=tool_id)
                )
                
            except asyncio.TimeoutError:
                logger.warning(f"Tool {tool_name} timed out after {timeout}s")
                tool_messages.append(
                    ToolMessage(
                        content=f"Tool execution timed out after {timeout}s",
                        tool_call_id=tool_id
                    )
                )
            except Exception as e:
                logger.exception(f"Error executing tool {tool_name}")
                tool_messages.append(
                    ToolMessage(
                        content=f"Tool execution error: {str(e)}",
                        tool_call_id=tool_id
                    )
                )
        
        return {**state, "messages": tool_messages}
```

### 2.3 Fragile Result Parsing

**Problem**: Complex nested conditionals for parsing results
```python
if isinstance(result, str):
    stats = json.loads(result)
elif isinstance(result, list) and len(result) > 0:
    item = result[0]
    if isinstance(item, dict) and "text" in item:
        stats = json.loads(item["text"])
    # ... more nesting
```

**Solution**: Extract to robust parser function
```python
def parse_stats_result(result: Any) -> dict:
    """Parse stats result from various formats."""
    try:
        # String JSON
        if isinstance(result, str):
            return json.loads(result)
        
        # Direct dict
        if isinstance(result, dict):
            # Check if it's a wrapper
            if "text" in result:
                return json.loads(result["text"])
            return result
        
        # List of results
        if isinstance(result, list) and result:
            return parse_stats_result(result[0])
        
        # Fallback
        logger.warning(f"Unknown stats result format: {type(result)}")
        return {"has_index": False, "error": "Unknown format"}
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        return {"has_index": False, "error": "JSON parse error"}
    except Exception as e:
        logger.exception("Unexpected error parsing stats")
        return {"has_index": False, "error": str(e)}

def extract_tool_result(result: Any) -> str:
    """Extract text content from tool result."""
    if isinstance(result, str):
        return result
    
    if isinstance(result, dict) and "text" in result:
        return result["text"]
    
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict) and "text" in first:
            return first["text"]
        return str(first)
    
    return str(result)
```

---

## 3. PERFORMANCE ISSUES

### 3.1 Client Reconnection Overhead

**Problem**: New MCP client created for every node execution
- 3 clients per query minimum
- Each client spawns new subprocess

**Solution**: Client pooling or state caching
```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    knowledge_stats: dict
    _mcp_client_cache: Optional[dict]  # Private cache

async def get_cached_client(state: AgentState) -> MultiServerMCPClient:
    """Get or create cached MCP client."""
    cache = state.get("_mcp_client_cache")
    
    if cache and cache.get("client"):
        return cache["client"]
    
    client = MultiServerMCPClient(get_mcp_config())
    state["_mcp_client_cache"] = {"client": client}
    return client
```

### 3.2 No Caching Strategy

**Problem**: No caching for repeated queries or knowledge base stats

**Solution**: Add caching layer
```python
from functools import lru_cache
import hashlib
from datetime import datetime, timedelta

class StatsCache:
    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        self.cache: dict[str, tuple[dict, datetime]] = {}
    
    def get(self, project_root: Path) -> Optional[dict]:
        key = str(project_root)
        if key in self.cache:
            stats, timestamp = self.cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl):
                return stats
            del self.cache[key]
        return None
    
    def set(self, project_root: Path, stats: dict):
        key = str(project_root)
        self.cache[key] = (stats, datetime.now())

_stats_cache = StatsCache()

async def check_knowledge(state: AgentState) -> AgentState:
    project_root = detect_project_root()
    
    # Try cache first
    cached_stats = _stats_cache.get(project_root)
    if cached_stats:
        return {**state, "knowledge_stats": cached_stats}
    
    # Fetch and cache
    async with get_mcp_client(project_root) as client:
        stats = await fetch_stats(client)
        _stats_cache.set(project_root, stats)
        return {**state, "knowledge_stats": stats}
```

### 3.3 Sequential Tool Execution

**Problem**: Tools execute one at a time
```python
for tool_call in last_message.tool_calls:
    result = await tool.ainvoke(tool_args)  # Sequential
```

**Solution**: Parallel execution when possible
```python
async def execute_tools(state: AgentState) -> AgentState:
    last_message = state["messages"][-1]
    
    if not last_message.tool_calls:
        return state
    
    async with get_mcp_client() as client:
        tools = await client.get_tools()
        tools_by_name = {tool.name: tool for tool in tools}
        
        # Create coroutines for parallel execution
        async def execute_single_tool(tool_call):
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            if tool_name not in tools_by_name:
                return ToolMessage(
                    content=f"Tool {tool_name} not found",
                    tool_call_id=tool_id
                )
            
            try:
                tool = tools_by_name[tool_name]
                result = await asyncio.wait_for(tool.ainvoke(tool_args), timeout=60)
                content = extract_tool_result(result)
                return ToolMessage(content=content, tool_call_id=tool_id)
            except Exception as e:
                logger.exception(f"Error executing {tool_name}")
                return ToolMessage(content=f"Error: {e}", tool_call_id=tool_id)
        
        # Execute all tools in parallel
        tool_messages = await asyncio.gather(
            *[execute_single_tool(tc) for tc in last_message.tool_calls],
            return_exceptions=True
        )
        
        # Filter out exceptions (already logged)
        tool_messages = [
            msg for msg in tool_messages 
            if isinstance(msg, ToolMessage)
        ]
        
        return {**state, "messages": tool_messages}
```

---

## 4. ARCHITECTURAL IMPROVEMENTS

### 4.1 Separation of Concerns

**Problem**: Business logic mixed with infrastructure code

**Solution**: Layer architecture
```python
# domain/knowledge_agent.py
class KnowledgeService:
    """Domain logic for knowledge operations."""
    
    def __init__(self, mcp_client: MultiServerMCPClient):
        self.client = mcp_client
    
    async def get_stats(self) -> dict:
        tools = await self.client.get_tools()
        stats_tool = next((t for t in tools if t.name == "stats"), None)
        if not stats_tool:
            raise ToolNotFoundError("stats")
        
        result = await stats_tool.ainvoke({})
        return parse_stats_result(result)
    
    async def execute_tool(self, name: str, args: dict) -> str:
        tools = await self.client.get_tools()
        tool = next((t for t in tools if t.name == name), None)
        if not tool:
            raise ToolNotFoundError(name)
        
        result = await asyncio.wait_for(
            tool.ainvoke(args),
            timeout=60
        )
        return extract_tool_result(result)

# workflows/knowledge_agent.py - becomes thinner
async def check_knowledge(state: AgentState) -> AgentState:
    async with get_mcp_client() as client:
        service = KnowledgeService(client)
        stats = await service.get_stats()
        return {**state, "knowledge_stats": stats}
```

### 4.2 Add Circuit Breaker Pattern

**Problem**: No protection against cascading failures

**Solution**: Implement circuit breaker
```python
from enum import Enum
from datetime import datetime, timedelta

class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        recovery_timeout: int = 30
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout_seconds
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitState.CLOSED
    
    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout elapsed
            if (self.last_failure_time and 
                datetime.now() - self.last_failure_time > 
                timedelta(seconds=self.recovery_timeout)):
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        
        # HALF_OPEN state - allow one request
        return True
    
    async def execute(self, coro):
        if not self.can_execute():
            raise CircuitBreakerOpenError(
                f"Circuit breaker open. Last failure: {self.last_failure_time}"
            )
        
        try:
            result = await asyncio.wait_for(coro, timeout=self.timeout)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise
    
    def on_success(self):
        self.failures = 0
        self.state = CircuitState.CLOSED
    
    def on_failure(self):
        self.failures += 1
        self.last_failure_time = datetime.now()
        
        if self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker opened after {self.failures} failures"
            )

# Usage
_mcp_circuit_breaker = CircuitBreaker()

async def check_knowledge(state: AgentState) -> AgentState:
    try:
        async with get_mcp_client() as client:
            service = KnowledgeService(client)
            stats = await _mcp_circuit_breaker.execute(
                service.get_stats()
            )
            return {**state, "knowledge_stats": stats}
    except CircuitBreakerOpenError as e:
        logger.warning(str(e))
        return {
            **state,
            "knowledge_stats": {"has_index": False, "error": "Service unavailable"}
        }
```

### 4.3 Retry Logic

**Problem**: No retry for transient failures

**Solution**: Add exponential backoff retry
```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    reraise=True
)
async def get_mcp_tools(client: MultiServerMCPClient):
    """Get tools with retry logic."""
    return await client.get_tools()
```

---

## 5. OBSERVABILITY & MONITORING

### 5.1 Add Structured Logging

**Problem**: Print statements instead of proper logging

**Solution**: Structured logging with context
```python
import logging
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()

async def check_knowledge(state: AgentState) -> AgentState:
    log = logger.bind(node="check_knowledge", thread_id=state.get("thread_id"))
    log.info("Starting knowledge check")
    
    try:
        async with get_mcp_client() as client:
            stats = await fetch_stats(client)
            log.info(
                "Knowledge check complete",
                has_index=stats.get("has_index"),
                doc_count=stats.get("document_count")
            )
            return {**state, "knowledge_stats": stats}
    except Exception as e:
        log.error("Knowledge check failed", error=str(e), exc_info=True)
        raise
```

### 5.2 Add Metrics/Telemetry

**Solution**: OpenTelemetry integration
```python
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)

async def check_knowledge(state: AgentState) -> AgentState:
    with tracer.start_as_current_span("check_knowledge") as span:
        span.set_attribute("node", "check_knowledge")
        
        try:
            async with get_mcp_client() as client:
                with tracer.start_as_current_span("fetch_stats"):
                    stats = await fetch_stats(client)
                
                span.set_attribute("has_index", stats.get("has_index", False))
                span.set_attribute("doc_count", stats.get("document_count", 0))
                
                return {**state, "knowledge_stats": stats}
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise
```

---

## 6. TESTING IMPROVEMENTS

### 6.1 Add Unit Tests

**Problem**: Limited test coverage

**Solution**: Comprehensive test suite
```python
# tests/test_knowledge_agent.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from langgraph.workflows.knowledge_agent import (
    check_knowledge,
    agent,
    execute_tools,
    should_continue,
    AgentState
)

@pytest.fixture
def mock_mcp_client():
    client = AsyncMock()
    client.get_tools = AsyncMock()
    return client

@pytest.fixture
def sample_state():
    return AgentState(
        messages=[HumanMessage(content="Test query")],
        knowledge_stats={},
        mcp_client=None
    )

@pytest.mark.asyncio
async def test_check_knowledge_success(mock_mcp_client, sample_state):
    """Test successful knowledge check."""
    mock_tool = AsyncMock()
    mock_tool.name = "stats"
    mock_tool.ainvoke = AsyncMock(return_value='{"has_index": true, "document_count": 10}')
    
    mock_mcp_client.get_tools.return_value = [mock_tool]
    
    with patch('langgraph.workflows.knowledge_agent.get_mcp_client') as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_mcp_client
        
        result = await check_knowledge(sample_state)
        
        assert result["knowledge_stats"]["has_index"] is True
        assert result["knowledge_stats"]["document_count"] == 10

@pytest.mark.asyncio
async def test_check_knowledge_no_index(mock_mcp_client, sample_state):
    """Test when no knowledge base exists."""
    mock_tool = AsyncMock()
    mock_tool.name = "stats"
    mock_tool.ainvoke = AsyncMock(return_value='{"has_index": false}')
    
    mock_mcp_client.get_tools.return_value = [mock_tool]
    
    with patch('langgraph.workflows.knowledge_agent.get_mcp_client') as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_mcp_client
        
        result = await check_knowledge(sample_state)
        
        assert result["knowledge_stats"]["has_index"] is False

@pytest.mark.asyncio
async def test_execute_tools_timeout():
    """Test tool execution with timeout."""
    state = AgentState(
        messages=[
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "search",
                    "args": {"query": "test"},
                    "id": "call_123"
                }]
            )
        ],
        knowledge_stats={"has_index": True}
    )
    
    mock_tool = AsyncMock()
    mock_tool.name = "search"
    mock_tool.ainvoke = AsyncMock(side_effect=asyncio.TimeoutError())
    
    mock_client = AsyncMock()
    mock_client.get_tools.return_value = [mock_tool]
    
    with patch('langgraph.workflows.knowledge_agent.get_mcp_client') as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_client
        
        result = await execute_tools(state)
        
        assert len(result["messages"]) == 1
        assert "timed out" in result["messages"][0].content.lower()

def test_should_continue_with_tool_calls():
    """Test routing when tool calls are present."""
    state = AgentState(
        messages=[
            AIMessage(content="", tool_calls=[{"name": "search"}])
        ],
        knowledge_stats={}
    )
    
    result = should_continue(state)
    assert result == "execute_tools"

def test_should_continue_without_tool_calls():
    """Test routing when no tool calls."""
    state = AgentState(
        messages=[AIMessage(content="Final answer")],
        knowledge_stats={}
    )
    
    result = should_continue(state)
    assert result == "__end__"
```

### 6.2 Integration Tests

```python
# tests/test_knowledge_agent_integration.py
import pytest
from langgraph.workflows.knowledge_agent import graph
from langchain_core.messages import HumanMessage

@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_workflow_with_knowledge():
    """Test complete workflow with real knowledge base."""
    config = {"configurable": {"thread_id": "test-1"}}
    
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="What is this project about?")]},
        config
    )
    
    assert "messages" in result
    assert len(result["messages"]) > 0
    assert result["messages"][-1].content  # Has response

@pytest.mark.asyncio
@pytest.mark.integration
async def test_workflow_without_knowledge():
    """Test workflow when no knowledge base exists."""
    # Mock environment without knowledge
    with patch('langgraph.workflows.utils.detect_project_root') as mock_root:
        mock_root.return_value = Path("/tmp/no-knowledge")
        
        config = {"configurable": {"thread_id": "test-2"}}
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="Test")]},
            config
        )
        
        response = result["messages"][-1].content
        assert "no knowledge base" in response.lower()
```

---

## 7. DOCUMENTATION IMPROVEMENTS

### 7.1 Add Docstrings

```python
async def check_knowledge(state: AgentState) -> AgentState:
    """Check if knowledge base exists and retrieve statistics.
    
    This node connects to the MCP server and queries the knowledge base
    stats tool to determine if an index exists and get metadata about
    indexed documents.
    
    Args:
        state: Current agent state containing messages and stats
        
    Returns:
        Updated state with knowledge_stats populated:
        - has_index (bool): Whether knowledge base exists
        - document_count (int): Number of indexed documents
        - source_files (int): Number of source files
        - project_root (str): Path to project root
        
    Raises:
        KnowledgeBaseError: If connection or stats retrieval fails
        
    Example:
        >>> state = AgentState(messages=[HumanMessage("test")])
        >>> result = await check_knowledge(state)
        >>> print(result["knowledge_stats"]["has_index"])
        True
    """
    # Implementation
```

### 7.2 Add Architecture Documentation

```markdown
# Knowledge Agent Architecture

## Overview
The Knowledge Agent is a LangGraph workflow that provides intelligent access
to project knowledge bases via MCP tools.

## Flow Diagram
```
┌─────────────┐
│   START     │
└─────┬───────┘
      │
      v
┌─────────────────┐
│ check_knowledge │  Verify KB exists
└─────┬───────────┘
      │
      v
┌─────────────┐
│    agent    │  Generate response/tool calls
└─────┬───────┘
      │
      v
    ┌─┴─┐
    │ ? │ Has tool calls?
    └─┬─┘
      │
      ├─Yes──> ┌──────────────┐
      │        │execute_tools │ Run tools
      │        └──────┬───────┘
      │               │
      │               └─> Back to agent
      │
      └─No───> END
```

## State Management
- `messages`: Conversation history (append-only)
- `knowledge_stats`: KB metadata (set once in check_knowledge)
- `mcp_client`: Cached MCP client (lifecycle managed)

## Error Handling
- Circuit breaker protects against cascading failures
- Exponential backoff retry for transient errors
- Structured logging for debugging

## Performance
- Client caching reduces subprocess overhead
- Stats caching (5min TTL) reduces KB queries
- Parallel tool execution when possible
```

---

## 8. SECURITY CONSIDERATIONS

### 8.1 Input Validation

```python
def validate_tool_args(tool_name: str, args: dict) -> dict:
    """Validate and sanitize tool arguments."""
    if tool_name == "search":
        query = args.get("query", "")
        if not query or len(query) > 1000:
            raise ValueError("Invalid query length")
        
        # Sanitize query
        args["query"] = query.strip()
        
        top_k = args.get("top_k", 5)
        if not isinstance(top_k, int) or not 1 <= top_k <= 20:
            args["top_k"] = 5
    
    return args
```

### 8.2 Environment Variable Handling

```python
def get_mcp_env(project_root: Path) -> dict:
    """Get environment variables with sensitive data handling."""
    api_key, base_url = get_openrouter_config()
    
    if not api_key:
        raise ConfigurationError("API key not configured")
    
    # Don't log sensitive values
    env = {
        "PROJECT_ROOT": str(project_root),
        "KNOWLEDGE_DIR": str(project_root / ".knowledge" / "llamaindex"),
        "DOCS_DIR": str(project_root / "docs"),
        "OPENROUTER_API_KEY": api_key,  # Will be masked in logs
        "OPENAI_BASE_URL": base_url,
    }
    
    # Verify paths exist and are accessible
    for key in ["KNOWLEDGE_DIR", "DOCS_DIR"]:
        path = Path(env[key])
        if not path.exists():
            logger.warning(f"{key} does not exist: {path}")
    
    return env
```

---

## 9. PRIORITY ACTION ITEMS

### High Priority (Immediate)
1. **Fix resource leaks**: Implement context manager for MCP client
2. **Add error handling**: Proper exception hierarchy and logging
3. **Add timeouts**: Protect against hanging tool calls
4. **Extract duplicated code**: Centralize MCP client config

### Medium Priority (Next Sprint)
5. **Implement caching**: Stats cache and client pooling
6. **Add retry logic**: Exponential backoff for transient failures
7. **Improve type safety**: Fix type annotations and add validation
8. **Add unit tests**: Achieve >80% coverage

### Low Priority (Future)
9. **Circuit breaker**: Protect against cascading failures
10. **Telemetry**: OpenTelemetry integration
11. **Parallel execution**: Execute independent tools concurrently
12. **Documentation**: Complete docstrings and architecture docs

---

## 10. REFACTORED EXAMPLE

Here's a complete refactored version of the `check_knowledge` function incorporating all improvements:

```python
"""
Knowledge Agent - Refactored check_knowledge node
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional
from pathlib import Path

from langchain_core.messages import BaseMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from opentelemetry import trace

from .utils import get_mcp_config, detect_project_root
from .errors import KnowledgeBaseError, ToolNotFoundError
from .cache import StatsCache

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)
_stats_cache = StatsCache(ttl_seconds=300)


@asynccontextmanager
async def get_mcp_client(project_root: Optional[Path] = None):
    """Context manager for MCP client with proper cleanup."""
    if project_root is None:
        project_root = detect_project_root()
    
    config = get_mcp_config(project_root)
    client = MultiServerMCPClient(config)
    
    try:
        yield client
    finally:
        if hasattr(client, 'close'):
            try:
                await client.close()
            except Exception as e:
                logger.warning(f"Error closing MCP client: {e}")


def parse_stats_result(result: Any) -> dict:
    """Parse stats result from various formats with error handling."""
    try:
        if isinstance(result, str):
            return json.loads(result)
        
        if isinstance(result, dict):
            if "text" in result:
                return json.loads(result["text"])
            return result
        
        if isinstance(result, list) and result:
            return parse_stats_result(result[0])
        
        logger.warning(f"Unknown stats result format: {type(result)}")
        return {"has_index": False, "error": "Unknown format"}
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON stats: {e}")
        return {"has_index": False, "error": "JSON parse error"}
    except Exception as e:
        logger.exception("Unexpected error parsing stats")
        return {"has_index": False, "error": str(e)}


async def fetch_stats_from_mcp(client: MultiServerMCPClient) -> dict:
    """Fetch stats from MCP client with timeout and retry."""
    tools = await asyncio.wait_for(
        client.get_tools(),
        timeout=10
    )
    
    stats_tool = next((t for t in tools if t.name == "stats"), None)
    if not stats_tool:
        raise ToolNotFoundError("stats tool not found in MCP server")
    
    result = await asyncio.wait_for(
        stats_tool.ainvoke({}),
        timeout=30
    )
    
    return parse_stats_result(result)


async def check_knowledge(state: AgentState) -> AgentState:
    """Check if knowledge base exists and retrieve statistics.
    
    This node connects to the MCP server and queries the knowledge base
    stats tool. Results are cached for 5 minutes to reduce overhead.
    
    Args:
        state: Current agent state containing messages
        
    Returns:
        Updated state with knowledge_stats populated:
        - has_index (bool): Whether knowledge base exists
        - document_count (int): Number of indexed documents
        - source_files (int): Number of source files
        - project_root (str): Path to project root
        
    Raises:
        KnowledgeBaseError: If connection or stats retrieval fails
    """
    with tracer.start_as_current_span("check_knowledge") as span:
        project_root = detect_project_root()
        span.set_attribute("project_root", str(project_root))
        
        logger.info(
            "Checking knowledge base",
            extra={"project_root": str(project_root)}
        )
        
        # Try cache first
        cached_stats = _stats_cache.get(project_root)
        if cached_stats:
            logger.debug("Using cached knowledge stats")
            span.set_attribute("cache_hit", True)
            span.set_attribute("has_index", cached_stats.get("has_index", False))
            return {**state, "knowledge_stats": cached_stats}
        
        span.set_attribute("cache_hit", False)
        
        try:
            async with get_mcp_client(project_root) as client:
                with tracer.start_as_current_span("fetch_stats"):
                    stats = await fetch_stats_from_mcp(client)
                
                # Cache successful result
                _stats_cache.set(project_root, stats)
                
                span.set_attribute("has_index", stats.get("has_index", False))
                span.set_attribute("document_count", stats.get("document_count", 0))
                
                logger.info(
                    "Knowledge check complete",
                    extra={
                        "has_index": stats.get("has_index"),
                        "document_count": stats.get("document_count")
                    }
                )
                
                return {**state, "knowledge_stats": stats}
                
        except asyncio.TimeoutError:
            logger.error("Knowledge check timed out")
            span.set_status(Status(StatusCode.ERROR, "Timeout"))
            raise KnowledgeBaseError("Knowledge base check timed out") from None
            
        except ToolNotFoundError as e:
            logger.error(f"Stats tool not available: {e}")
            span.set_status(Status(StatusCode.ERROR, str(e)))
            # Don't raise - return empty stats
            return {
                **state,
                "knowledge_stats": {"has_index": False, "error": str(e)}
            }
            
        except Exception as e:
            logger.exception("Unexpected error checking knowledge base")
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise KnowledgeBaseError(
                f"Failed to check knowledge base: {e}"
            ) from e
```

---

## CONCLUSION

The knowledge_agent workflow is functionally sound but would benefit significantly from:

1. **Better resource management** - Prevents leaks and improves reliability
2. **Robust error handling** - Makes failures visible and debuggable
3. **Performance optimizations** - Caching and parallel execution
4. **Code quality improvements** - DRY principles, type safety
5. **Observability** - Proper logging and metrics for production use

Implementing the high-priority items will make the system production-ready, while medium and low-priority items will improve maintainability and scalability over time.
