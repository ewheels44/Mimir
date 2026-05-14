# Mimir Jcode Notifications

## Overview

When Jcode calls Mimir tools via MCP, the user is now notified that Mimir is being used. This is accomplished using FastMCP's Context injection which provides access to logging methods that send notifications to the MCP client (Jcode).

## How It Works

### Server-Side (mcp_server_llamaindex.py)

1. **Context Injection**: Each MCP tool now accepts an optional `ctx: Context = None` parameter
   - FastMCP automatically injects the Context object when the tool is called
   - The Context object provides methods like `ctx.info()`, `ctx.debug()`, `ctx.warning()`, etc.

2. **Notification Function**: A helper function `_notify_jcode_usage(ctx, tool_name)` is called at the start of each tool
   - Sends an info-level log message to the client
   - Message format: `"Mimir is being used by Jcode [from {client_id}] - Tool: {tool_name}"`
   - Includes client_id if available from the Context

3. **Error Handling**: Notification errors are caught and ignored so they don't break tool execution

### Client-Side (Jcode)

Jcode receives the log notification via the MCP protocol's `notifications/message` method. The message appears in the Jcode UI, notifying the user that Mimir tools are being used.

## Modified Tools

The following MCP tools now send notifications when called:

- `search` - Search the project knowledge base
- `query` - Ask a question about the project
- `reindex` - Rebuild the knowledge base
- `remove_file` - Remove a file from the index
- `stats` - Get knowledge base statistics
- `rag_workflow` - Structured retrieve→generate pipeline
- `knowledge_agent` - Multi-step agentic research
- `enrich_task` - Search for project context relevant to a task
- `openspace_health` - Check OpenSpace bridge health
- `sdk_cache_get` - Get SDK documentation from cache
- `sdk_cache_list` - List cached SDK documentation
- `health_check` - Check Mimir server health
- `graph_query` - Find shortest path between modules
- `graph_neighbors` - Find connected modules/entities
- `graph_stats` - Get knowledge graph statistics

## Technical Details

### Code Changes

In `mcp_server_llamaindex.py`:

1. **Import added**:
   ```python
   from mcp.server.fastmcp import FastMCP, Context
   ```

2. **Notification helper**:
   ```python
   async def _notify_jcode_usage(ctx: Context, tool_name: str) -> None:
       """Send a notification to Jcode client when Mimir tools are used."""
       try:
           client_info = ""
           if hasattr(ctx, 'client_id') and ctx.client_id:
               client_info = f" from {ctx.client_id}"
           
           await ctx.info(
               f"Mimir is being used by Jcode{client_info} - Tool: {tool_name}"
           )
       except Exception:
           pass
   ```

3. **Tool signature change** (example):
   ```python
   # Before
   async def search(query: str, top_k: int = 5) -> str:
   
   # After
   async def search(query: str, top_k: int = 5, ctx: Context = None) -> str:
   ```

4. **Notification call** (at start of each tool):
   ```python
   await _notify_jcode_usage(ctx, "search")
   ```

## Benefits

1. **User Awareness**: Users know when Mimir is being used vs. regular Jcode operations
2. **Debugging**: Helps debug which tools are being called and when
3. **Transparency**: Clear indication that external knowledge is being accessed
4. **Non-Intrusive**: Uses standard MCP logging notifications, doesn't block execution

## Future Enhancements

- Include more metadata in notifications (e.g., query text, result count)
- Add option to disable notifications via environment variable
- Track tool usage statistics
- Send progress notifications for long-running operations (reindex, rag_workflow)
