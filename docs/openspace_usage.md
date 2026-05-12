Level 1: Smoke test the bridge directly
Fastest way to verify Mimir's index + bridge + content filter all work:
cd ~/Documents/Mimir && .venv/bin/python -c "
from pathlib import Path
from src.mimir.openspace_bridge import MimirOpenSpaceBridge
import json
bridge = MimirOpenSpaceBridge(project_root=Path('.'))
# Health check
print('=== Health ===')
print(json.dumps(bridge.health_check(), indent=2))
# Test enrichment
print('\n=== Enrich: MCP server ===')
r = bridge.enrich_task('How does the MCP server handle tool registration?')
print(json.dumps(r.to_dict(), indent=2))
print('\n=== Enrich: LangGraph workflows ===')
r = bridge.enrich_task('What LangGraph workflows exist and how do they work?')
print(json.dumps(r.to_dict(), indent=2))
"
You should see success: true, result_count > 0, and actual context chunks from your docs/code.
Level 2: Test via MCP tools
Once OpenCode restarts, you can ask me directly:
- "Check openspace_health" — I'll call the health tool and show you the bridge status
- "Search Mimir for how the RAG workflow works" — I'll call enrich_task and show you what comes back
This validates the MCP wiring without involving OpenSpace.
Level 3: Full integration loop
This is where it gets interesting. Give OpenSpace a task that benefits from project context:
1. Restart OpenCode so it picks up the new config
2. Ask me something like:
> "Use OpenSpace to analyze the LangGraph knowledge_agent workflow and suggest improvements"
What should happen:
- OpenSpace's execute_task fires
- The mimir-knowledge skill triggers → calls enrich_task 
- Mimir returns context about the knowledge_agent code
- OpenSpace's agent uses that context instead of reasoning from scratch
- You get project-aware suggestions, not generic ones
Level 4: Real usage
After validating the loop works, start using it naturally:
- Before building features: "Use OpenSpace to add caching to the search endpoint" — it'll pull Mimir's context about your existing search code
- After failures: "That didn't work, try again with Mimir context" — explicit re-enrichment
- Complex tasks: "Use OpenSpace to refactor the indexing pipeline" — multi-file changes benefit most from project context
