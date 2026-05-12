// ─── Architecture Explainer — Code Examples & Dependency Traces ──────────────

export interface CodeExample {
  file: string;
  line: number;
  title: string;
  code: string;
  explanation: string;
  plainExplanation: string;
}

export interface DependencyTrace {
  from: string;
  to: string;
  type: 'imports' | 'calls' | 'extends' | 'implements';
  line: number;
}

export interface ArchitectureLayer {
  id: string;
  tier: number;
  label: string;
  subtitle: string;
  icon: string;
  color: string;
  overview: string;
  plainOverview: string;
  modules: {
    title: string;
    file: string;
    line?: number;
    description: string;
    plainDescription: string;
    keyExports: string[];
    codeExamples: CodeExample[];
    dependencyTraces: DependencyTrace[];
  }[];
  sequence: {
    step: number;
    module: string;
    action: string;
    plainAction: string;
    inputs: string[];
    outputs: string[];
  }[];
}

// ─── Layer 1: User & Client ───────────────────────────────────────────────────

export const layerUserClient: ArchitectureLayer = {
  id: 'user-client',
  tier: 1,
  label: 'User & Client Layer',
  subtitle: 'Where requests enter the system',
  icon: '💬',
  color: '#6366f1',
  overview: 'Users ask questions via MCP-compatible clients (OpenCode, Claude Desktop). The client sends structured tool calls to the Mimir MCP server, which routes them to appropriate handlers.',
  plainOverview: 'You type a question in normal English. Your AI tool (like Claude or Cursor) sends it to Mimir through a standard protocol called MCP.',
  modules: [
    {
      title: 'MCP Client',
      file: 'external (Claude/Cursor/OpenCode)',
      description: 'The Model Context Protocol client formats user requests as structured tool calls and sends them to the Mimir MCP server over stdio or SSE.',
      plainDescription: 'This is the "messenger" — it takes your question and sends it to Mimir in a language Mimir understands.',
      keyExports: ['tool_call', 'tool_result', 'session management'],
      codeExamples: [
        {
          file: 'mcp_server_llamaindex.py',
          line: 485,
          title: 'MCP Tool Registration Pattern',
          code: [
            '@mcp.tool()',
            'async def search(query: str, top_k: int = 5) -> str:',
            '    """Search the project knowledge base."""',
            '    return await _with_timeout(',
            '        asyncio.to_thread(server.search, query, top_k)',
            '    )',
          ].join('\n'),
          explanation: 'Each MCP tool is an async function decorated with @mcp.tool(). FastMCP auto-registers these under the "mimir-knowledge" namespace. The server name prefix creates full tool names like "mimir-knowledge_search".',
          plainExplanation: 'Mimir registers its tools with names like "mimir-knowledge_search". Your AI client calls that tool by name, passing the question text, and gets back the results.',
        },
      ],
      dependencyTraces: [
        { from: 'mcp_server_llamaindex.py', to: 'config.py', type: 'imports', line: 97 },
        { from: 'mcp_server_llamaindex.py', to: 'indexing.py', type: 'imports', line: 182 },
        { from: 'mcp_server_llamaindex.py', to: 'openspace_bridge.py', type: 'imports', line: 566 },
      ],
    },
  ],
  sequence: [
    {
      step: 1,
      module: 'MCP Client',
      action: 'Send tool_call("mimir-knowledge_search", {query})',
      plainAction: 'Your AI sends the question to Mimir',
      inputs: ['user question text'],
      outputs: ['search results text'],
    },
  ],
};

// ─── Layer 2: Orchestration ──────────────────────────────────────────────────

export const layerOrchestration: ArchitectureLayer = {
  id: 'orchestration',
  tier: 2,
  label: 'Orchestration Layer',
  subtitle: 'Deciding how to answer — RAG, agent loop, or direct search',
  icon: '🔀',
  color: '#f59e0b',
  overview: 'The MCP server dispatches to different workflows based on the tool called. Simple queries use search() for keyword + vector hybrid retrieval. Complex questions route through knowledge_agent(), which uses LangGraph to orchestrate multi-step reasoning loops.',
  plainOverview: 'Mimir decides: "Should I do a quick search, or do I need to think about this step by step?" Simple questions get instant answers. Hard ones go through a reasoning loop.',
  modules: [
    {
      title: 'Knowledge Agent (LangGraph)',
      file: 'langgraph/workflows/knowledge_agent.py',
      description: 'A multi-step agent workflow built on LangGraph. It iteratively decides which tool to call (graph_neighbors, search, file_reader), observes results, and loops until confident enough to synthesize an answer.',
      plainDescription: 'The agent is like a detective — it gathers clues one at a time, checks if it has enough info, and keeps investigating until it can give you a complete answer.',
      keyExports: ['graph', 'ainvoke', 'State', 'Command'],
      codeExamples: [
        {
          file: 'langgraph/workflows/knowledge_agent.py',
          line: 1,
          title: 'Agent State Definition',
          code: [
            'class State:',
            '    messages: Annotated[list, add_messages]',
            '    query: str',
            '    tool_calls: list = []',
            '    results: list = []',
            '    loop_count: int = 0',
          ].join('\n'),
          explanation: 'LangGraph uses a typed state object that flows through the graph nodes. Each node can read and modify the state. The add_messages annotation tells LangGraph to append rather than replace.',
          plainExplanation: 'The agent keeps a "notebook" (state) where it writes down what it knows, what tools it used, and what answers it found. Each loop adds more information.',
        },
        {
          file: 'langgraph/workflows/knowledge_agent.py',
          line: 1,
          title: 'Tool-Calling Node',
          code: [
            'async def execute_tool(state: State, config):',
            '    tool = state.tool_calls[-1]',
            '    mcp_client = MCPClientWrapper()',
            '    result = await mcp_client.call(tool["name"], **tool["args"])',
            '    return {"results": [result]}',
          ].join('\n'),
          explanation: 'The agent selects a tool from the MCP server and calls it with arguments. Results are appended to the conversation state. This enables multi-hop exploration: call tool -> observe -> decide next tool.',
          plainExplanation: 'The detective picks a tool from their kit (like "look up file connections"), uses it, and writes the findings in the notebook.',
        },
      ],
      dependencyTraces: [
        { from: 'knowledge_agent.py', to: 'mcp_server_llamaindex.py', type: 'calls', line: 1 },
        { from: 'knowledge_agent.py', to: 'knowledge_graph.py', type: 'calls', line: 1 },
        { from: 'knowledge_agent.py', to: 'indexing.py', type: 'calls', line: 1 },
      ],
    },
    {
      title: 'RAG Workflow (LangGraph)',
      file: 'langgraph/workflows/rag.py',
      description: 'A simpler LangGraph workflow for single-turn RAG. Embeds the query, retrieves top-k chunks, assembles context with source attribution, and generates a response via an LLM.',
      plainDescription: 'For straightforward questions, this path does one pass: understand the question, find the best matches, and write an answer with citations.',
      keyExports: ['graph', 'ainvoke'],
      codeExamples: [
        {
          file: 'langgraph/workflows/rag.py',
          line: 1,
          title: 'RAG Graph State',
          code: [
            'class RAGState:',
            '    query: str',
            '    query_embedding: list[float]',
            '    retrieved_chunks: list[Document]',
            '    context: str',
            '    answer: str',
          ].join('\n'),
          explanation: 'The RAG state tracks each step of the pipeline: original query, its embedding, retrieved chunks, assembled context, and final answer. Each graph node operates on this shared state.',
          plainExplanation: 'The RAG workflow tracks its progress through stages: question -> numbers -> find matches -> build context -> write answer.',
        },
      ],
      dependencyTraces: [
        { from: 'rag.py', to: 'mcp_server_llamaindex.py', type: 'calls', line: 1 },
        { from: 'rag.py', to: 'config.py', type: 'imports', line: 1 },
      ],
    },
  ],
  sequence: [
    {
      step: 1,
      module: 'LangGraph Router',
      action: 'Classify query type -> route to RAG, Agent, or Search',
      plainAction: 'Mimir figures out how complex the question is',
      inputs: ['user query'],
      outputs: ['workflow choice'],
    },
    {
      step: 2,
      module: 'RAG Pipeline',
      action: 'Embed -> Search -> Assemble -> Generate',
      plainAction: 'Quick path: turn question into numbers, find matches, write answer',
      inputs: ['query text'],
      outputs: ['LLM response with citations'],
    },
    {
      step: 3,
      module: 'Knowledge Agent',
      action: 'Loop: think -> call tool -> observe -> repeat',
      plainAction: 'Complex path: the AI thinks, picks a tool, gets results, thinks again',
      inputs: ['complex query'],
      outputs: ['synthesized answer after N loops'],
    },
  ],
};

// ─── Layer 3: Retrieval ──────────────────────────────────────────────────────

export const layerRetrieval: ArchitectureLayer = {
  id: 'retrieval',
  tier: 3,
  label: 'Retrieval Layer',
  subtitle: 'Converting text to vectors, searching, and filtering results',
  icon: '🧮',
  color: '#3b82f6',
  overview: 'Text is converted to 1536-dimensional vectors using OpenAI text-embedding-3-small. The vector store (LlamaIndex) performs cosine similarity search. A content filter scans every result for API keys, IPs, and sensitive filenames before anything reaches the LLM.',
  plainOverview: 'Mimir turns your text and documents into coordinate numbers, finds the closest matches on a meaning-map, then checks everything for secrets before showing it to the AI.',
  modules: [
    {
      title: 'Embedding Engine',
      file: 'config.py',
      line: 43,
      description: 'Configurable embedding model (default: text-embedding-3-small). All documents and queries use the same model so their vectors land in the same semantic space.',
      plainDescription: 'This is the "translator" that converts text into number coordinates. Using the same translator for questions and documents ensures they can be compared.',
      keyExports: ['EMBEDDING_MODEL', 'get_config().embedding_model'],
      codeExamples: [
        {
          file: 'config.py',
          line: 43,
          title: 'Default Embedding Model',
          code: [
            'DEFAULTS = {',
            '    "embedding_model": "text-embedding-3-large",',
            '    ...',
            '}',
            '',
            '# Resolution order:',
            '# 1. env var EMBEDDING_MODEL',
            '# 2. .mimir/config.json "embedding_model"',
            '# 3. DEFAULTS',
          ].join('\n'),
          explanation: 'Embedding model is resolved from env var -> config file -> defaults. text-embedding-3-small offers best cost/quality for RAG. All vectors are L2-normalized for cosine similarity.',
          plainExplanation: 'Mimir uses "text-embedding-3-small" by default — a fast, cheap AI model that turns text into 1,536 numbers. You can switch models via environment variables.',
        },
        {
          file: 'mcp_server_llamaindex.py',
          line: 143,
          title: 'Embedding Setup in MCP Server',
          code: [
            'embed_kwargs = {',
            '    "model": self.config.embedding_model,',
            '    "api_key": self.config.api_key,',
            '}',
            'if self.config.api_base:',
            '    embed_kwargs["api_base"] = self.config.api_base',
            'Settings.embed_model = OpenAIEmbedding(**embed_kwargs)',
          ].join('\n'),
          explanation: 'The MCP server configures LlamaIndex to use the embedding model from config. API base URL is set for OpenRouter or self-hosted OpenAI-compatible endpoints.',
          plainExplanation: 'When Mimir starts, it tells the AI library which embedding model to use and where to send API calls.',
        },
      ],
      dependencyTraces: [
        { from: 'config.py', to: 'mcp_server_llamaindex.py', type: 'imports', line: 97 },
        { from: 'mcp_server_llamaindex.py', to: 'openspace_bridge.py', type: 'imports', line: 418 },
        { from: 'openspace_bridge.py', to: 'config.py', type: 'imports', line: 83 },
      ],
    },
    {
      title: 'Vector Store (LlamaIndex)',
      file: 'mcp_server_llamaindex.py',
      line: 207,
      description: 'Hybrid retrieval combining vector similarity (cosine) with BM25 keyword search. Returns top-k chunks with scores. Persistent on disk via index_store.json.',
      plainDescription: 'The filing cabinet. Documents are stored as number-coordinates. When you ask a question, Mimir finds the nearest documents on the meaning-map.',
      keyExports: ['search()', 'query()', 'get_index()'],
      codeExamples: [
        {
          file: 'mcp_server_llamaindex.py',
          line: 207,
          title: 'Hybrid Search Implementation',
          code: [
            'vector_retriever = index.as_retriever(similarity_top_k=top_k * 2)',
            'bm25_retriever = BM25Retriever.from_defaults(',
            '    index=index, similarity_top_k=top_k',
            ')',
            'vector_nodes = vector_retriever.retrieve(query)',
            'bm25_nodes = bm25_retriever.retrieve(query)',
            '# Merge and deduplicate',
            'seen_ids: set[str] = set()',
            'for node in vector_nodes + bm25_nodes:',
            '    if node.node_id not in seen_ids:',
            '        seen_ids.add(node.node_id)',
            '        nodes.append(node)',
          ].join('\n'),
          explanation: 'Mimir runs both vector and keyword searches in parallel, then merges results. Vector search finds semantically similar content; BM25 finds exact keyword matches. Deduplication ensures no chunk appears twice.',
          plainExplanation: 'Mimir searches in two ways at once: by meaning (vectors) and by exact words (keyword). It combines both lists and removes duplicates.',
        },
      ],
      dependencyTraces: [
        { from: 'mcp_server_llamaindex.py', to: 'indexing.py', type: 'imports', line: 182 },
        { from: 'mcp_server_llamaindex.py', to: 'config.py', type: 'imports', line: 97 },
        { from: 'indexing.py', to: 'config.py', type: 'imports', line: 1 },
      ],
    },
    {
      title: 'Content Filter',
      file: 'openspace_bridge.py',
      line: 241,
      description: 'Scans every retrieved chunk for sensitive data: API keys, private IPs, credentials, and blocked filenames. Matches are redacted with [REDACTED]; blocked files are excluded entirely.',
      plainDescription: 'A security guard that checks every piece of information before it leaves Mimir. Passwords and secret keys get replaced with [REDACTED].',
      keyExports: ['_is_sensitive()', '_filter_sensitive()', '_is_blocked_filename()'],
      codeExamples: [
        {
          file: 'openspace_bridge.py',
          line: 241,
          title: 'Sensitive Pattern Detection',
          code: [
            '_SENSITIVE_PATTERNS = [',
            '    re.compile(r"(?i)(api[_-]?key|secret[_-]?key|password|token)\\\\s*[:=]\\\\s*[\'\\"]?\\\\S+"),',
            '    re.compile(r"(?i)https?://(?:localhost|127\\\\.0\\\\.0\\\\.1|0\\\\.0\\\\.0\\\\.0|10\\\\.\\\\d+\\\\.\\\\d+\\\\.\\\\d+)"),',
            '    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),',
            ']',
            '',
            '_BLOCKED_FILENAMES = {',
            '    ".env", ".env.local", ".env.production",',
            '    "credentials.json", "secrets.json", "auth.json",',
            '    "id_rsa", "id_ed25519", "*.pem",',
            '}',
          ].join('\n'),
          explanation: 'Five regex patterns catch API keys, passwords, private IPs, internal hostnames, and private keys. Separately, a set of blocked filenames is checked -- .env files, credential stores, and SSH keys are never sent to external LLMs.',
          plainExplanation: 'Mimir looks for things that look like passwords, secret keys, or private files. If it finds any, it replaces them with [REDACTED] before the AI ever sees them.',
        },
      ],
      dependencyTraces: [
        { from: 'openspace_bridge.py', to: 'config.py', type: 'imports', line: 83 },
        { from: 'mcp_server_llamaindex.py', to: 'openspace_bridge.py', type: 'imports', line: 566 },
      ],
    },
  ],
  sequence: [
    {
      step: 1,
      module: 'Embedding Engine',
      action: 'Convert text -> 1536-dim vector',
      plainAction: 'Turn words into number coordinates',
      inputs: ['text string'],
      outputs: ['1536-dim vector'],
    },
    {
      step: 2,
      module: 'Vector Store',
      action: 'cosine_similarity(query_vec, all_doc_vecs) -> top-k',
      plainAction: 'Find the closest document coordinates',
      inputs: ['query vector', 'document vectors'],
      outputs: ['top-k chunks with scores'],
    },
    {
      step: 3,
      module: 'Content Filter',
      action: 'Scan for secrets -> redact or block',
      plainAction: 'Remove anything sensitive',
      inputs: ['search results'],
      outputs: ['safe results'],
    },
  ],
};

// ─── Layer 4: Infrastructure ─────────────────────────────────────────────────

export const layerInfrastructure: ArchitectureLayer = {
  id: 'infrastructure',
  tier: 4,
  label: 'Infrastructure Layer',
  subtitle: 'Change detection, index persistence, and knowledge graph extraction',
  icon: '📂',
  color: '#10b981',
  overview: 'The File Watcher uses watchdog with debouncing (2s) to detect changes. SHA-256 hashing (not timestamps) determines which files changed. The Manifest DB tracks all indexed files and their hashes. The Knowledge Graph extractor uses Python AST and tree-sitter to build a dependency graph.',
  plainOverview: 'Behind the scenes, Mimir watches your files for changes using smart fingerprints, keeps a ledger of what it has indexed, and builds a map of how your code connects together.',
  modules: [
    {
      title: 'File Watcher',
      file: 'watcher.py',
      description: 'Watchdog-based file system monitor with debounced re-indexing (2s debounce). Triggers both vector index updates and knowledge graph updates when files change.',
      plainDescription: 'Like a security camera for your project folder — when a file changes, it triggers Mimir to update its index.',
      keyExports: ['MimirFileWatcher', 'start()', 'stop()', 'status()'],
      codeExamples: [
        {
          file: 'watcher.py',
          line: 59,
          title: 'Debounced File Change Handler',
          code: [
            'class _DebounceHandler(FileSystemEventHandler):',
            '    def _schedule_reindex(self) -> None:',
            '        with self._lock:',
            '            if self._timer is not None:',
            '                self._timer.cancel()',
            '            self._timer = threading.Timer(',
            '                DEBOUNCE_SECONDS, self._watcher._trigger_reindex',
            '            )',
            '            self._timer.daemon = True',
            '            self._timer.start()',
          ].join('\n'),
          explanation: 'Uses threading.Timer for debouncing -- multiple rapid file changes within 2 seconds are collapsed into a single reindex. Both vector index and knowledge graph have separate debounce timers (2s and 5s).',
          plainExplanation: 'When a file changes, Mimir waits 2 seconds to see if more files change. If they do, it waits again. This prevents re-reading files multiple times during a big save.',
        },
        {
          file: 'watcher.py',
          line: 211,
          title: 'Incremental Reindex Trigger',
          code: [
            'def _trigger_reindex(self) -> None:',
            '    result = incremental_reindex(',
            '        project_root=self._project_root,',
            '        watched_dirs=self._watched_dirs,',
            '        knowledge_dir=self._knowledge_dir,',
            '    )',
            '    self._reindex_count += 1',
            '    self._last_reindex_result = result',
          ].join('\n'),
          explanation: 'Calls incremental_reindex() from indexing.py, which uses SHA-256 hash comparison to detect changed files and only re-indexes those.',
          plainExplanation: 'The actual re-reading only happens for files whose fingerprint changed -- unchanged files are never touched.',
        },
      ],
      dependencyTraces: [
        { from: 'watcher.py', to: 'indexing.py', type: 'imports', line: 12 },
        { from: 'watcher.py', to: 'knowledge_graph.py', type: 'imports', line: 19 },
        { from: 'watcher.py', to: 'config.py', type: 'calls', line: 1 },
      ],
    },
    {
      title: 'Manifest DB (Index State)',
      file: 'indexing.py',
      line: 82,
      description: 'JSON manifest tracking which files are indexed, their SHA-256 hashes, and document counts. Stored at .knowledge/llamaindex/manifest.json. Enables O(changed) incremental updates.',
      plainDescription: "Mimir's notebook -- it records every file it has read, along with a fingerprint for each. Next time, it just checks the notebook to know what to skip.",
      keyExports: ['load_manifest()', 'save_manifest()', 'add_to_manifest()', 'detect_changed_files()'],
      codeExamples: [
        {
          file: 'indexing.py',
          line: 322,
          title: 'SHA-256 Change Detection',
          code: [
            'def detect_changed_files(project_root, watched_dirs):',
            '    previous_state = load_hash_state(project_root)',
            '    previous_hashes = previous_state.get("file_hashes", {})',
            '',
            '    current_hashes = {}',
            '    for file_path in all_files:',
            '        file_hash = compute_file_hash(file_path)',
            '        current_hashes[rel_path] = file_hash',
            '',
            '    added = [p for p in current_hashes - previous_hashes]',
            '    modified = [p for p in current_hashes & previous_hashes',
            '                if current_hashes[p] != previous_hashes[p]]',
          ].join('\n'),
          explanation: 'Computes SHA-256 hashes for all files and compares against previously stored hashes. Added files are new; modified files have different hashes. This is more reliable than file timestamps (which change on git checkout).',
          plainExplanation: 'Mimir creates a fingerprint for every file. If the fingerprint is the same, the file has not changed. Only files with new fingerprints get re-read.',
        },
        {
          file: 'indexing.py',
          line: 82,
          title: 'Manifest Structure',
          code: [
            '{',
            '    "version": "1.0",',
            '    "indexed_directories": {',
            '        "/path/to/src": {',
            '            "path": "src",',
            '            "files": ["config.py", "utils.py"],',
            '            "file_count": 2,',
            '            "document_count": 47,',
            '            "last_indexed": "2026-05-08T16:39:00Z",',
            '            "file_hashes": {"config.py": "abc123..."}',
            '        }',
            '    },',
            '    "total_documents": 847,',
            '    "last_updated": "2026-05-08T16:39:00Z"',
            '}',
          ].join('\n'),
          explanation: 'The manifest is the single source of truth for the index state. It maps each directory to its files, counts, and hashes. On restart, Mimir reads the manifest to know exactly what is already indexed.',
          plainExplanation: 'The manifest is like a library catalog -- it lists every "book" (file), how many "pages" (documents) each has, and a fingerprint to detect changes.',
        },
      ],
      dependencyTraces: [
        { from: 'indexing.py', to: 'config.py', type: 'imports', line: 1 },
      ],
    },
    {
      title: 'Knowledge Graph Extractor',
      file: 'knowledge_graph.py',
      description: 'Extracts structured relationships from source code using Python AST and tree-sitter. Produces nodes (classes, functions, files) and edges (imports, calls, inheritance). Supports Python, TypeScript, JavaScript, Rust, and Go.',
      plainDescription: 'Reads your source code and automatically builds a map: which files import which, which functions call which, and which classes extend which.',
      keyExports: ['extract_code_relationships()', 'incremental_graph_update()', 'PythonASTExtractor', 'TreeSitterExtractor'],
      codeExamples: [
        {
          file: 'knowledge_graph.py',
          line: 371,
          title: 'Python Import Extraction via AST',
          code: [
            'def _imports(self, tree: ast.Module, rel_path: str) -> List[Relationship]:',
            '    rels: List[Relationship] = []',
            '    for node in ast.walk(tree):',
            '        if isinstance(node, ast.Import):',
            '            for alias in node.names:',
            '                rels.append(Relationship(',
            '                    source=rel_path,',
            '                    target=alias.name,',
            '                    relation_type="imports_module",',
            '                    metadata={"line": node.lineno},',
            '                ))',
            '        elif isinstance(node, ast.ImportFrom):',
            '            module = node.module or ""',
            '            for alias in node.names:',
            '                target = f"{module}.{alias.name}" if module else alias.name',
            '                rels.append(Relationship(',
            '                    source=rel_path, target=target,',
            '                    relation_type="imports_from",',
            '                    metadata={"line": node.lineno},',
            '                ))',
            '    return rels',
          ].join('\n'),
          explanation: 'Walks the Python AST looking for import statements. Each import creates a Relationship node with type "imports_module" or "imports_from", recording the source file, target module, and line number.',
          plainExplanation: 'Mimir reads your import statements and creates a map entry for each one -- like noting which roads connect to which cities.',
        },
        {
          file: 'knowledge_graph.py',
          line: 454,
          title: 'Function Call Extraction',
          code: [
            'def _calls(self, tree: ast.Module, rel_path: str) -> List[Relationship]:',
            '    seen: Set[str] = set()',
            '    for node in ast.walk(tree):',
            '        if not isinstance(node, ast.Call):',
            '            continue',
            '        name = self._call_name(node.func)',
            '        if name and name not in seen:',
            '            seen.add(name)',
            '            rels.append(Relationship(',
            '                source=rel_path, target=name,',
            '                relation_type="calls",',
            '                metadata={"line": node.lineno},',
            '            ))',
            '    return rels',
          ].join('\n'),
          explanation: 'Finds all function/method calls in a file and records them as "calls" relationships. Tracks both simple calls (foo()) and qualified chains (self.client.get()). Deduplicates per file.',
          plainExplanation: 'Every time your code calls a function, Mimir records it -- like a flight radar tracking all the routes between airports.',
        },
      ],
      dependencyTraces: [
        { from: 'knowledge_graph.py', to: 'indexing.py', type: 'calls', line: 1241 },
      ],
    },
  ],
  sequence: [
    {
      step: 1,
      module: 'File Watcher',
      action: 'watchdog detects file change -> 2s debounce',
      plainAction: 'Mimir notices a file changed and waits 2 seconds',
      inputs: ['filesystem events'],
      outputs: ['changed_files[]'],
    },
    {
      step: 2,
      module: 'Manifest DB',
      action: 'SHA-256 compare -> skip unchanged',
      plainAction: 'Checks fingerprints to skip unchanged files',
      inputs: ['all file paths', 'stored hashes'],
      outputs: ['changed_files[]', 'unchanged_files[]'],
    },
    {
      step: 3,
      module: 'File Watcher',
      action: 'trigger incremental_reindex() for changed files only',
      plainAction: 'Only re-reads the files that actually changed',
      inputs: ['changed_files[]'],
      outputs: ['updated vectors', 'updated manifest'],
    },
    {
      step: 4,
      module: 'Knowledge Graph',
      action: 'incremental_graph_update() for changed files',
      plainAction: 'Updates the code dependency map',
      inputs: ['changed files'],
      outputs: ['updated relationships JSON'],
    },
  ],
};

// ─── Cross-Cutting: Shared Indexes ───────────────────────────────────────────

export const featureSharedIndexes = {
  title: 'Shared Indexes',
  file: 'shared_index.py',
  icon: '🌐',
  color: '#8b5cf6',
  description: 'SharedIndexRegistry allows multiple projects to query pre-built indexes from a central location. Each index is validated for embedding model compatibility. Results are merged using TaggedNode attribution.',
  plainDescription: 'A team can index a large SDK once and share it across all projects -- like a shared library card catalog everyone can use.',
  keyCode: [
    '// In .mimir/config.json:',
    '{',
    '  "shared_indexes": {',
    '    "react-docs": "~/.mimir/shared-indexes/react/llamaindex",',
    '    "stripe-sdk": "~/.mimir/shared-indexes/stripe/llamaindex"',
    '  }',
    '}',
    '',
    '// merge_results() combines local + shared results by score',
    '// Each result carries a source tag: [YOUR CODE] or [STRIPE SDK]',
  ].join('\n'),
  dependencyTraces: [
    { from: 'shared_index.py', to: 'config.py', type: 'imports', line: 1 },
    { from: 'mcp_server_llamaindex.py', to: 'shared_index.py', type: 'imports', line: 99 },
  ],
};

// ─── Cross-Cutting: SDK Cache ────────────────────────────────────────────────

export const featureSDKCache = {
  title: 'SDK Documentation Cache',
  file: 'sdk_cache.py',
  icon: '📚',
  color: '#ec4899',
  description: 'Local TTL-based cache for SDK docs fetched from Context7 API. 7-day default TTL. Eliminates repeated API calls and token expenditure.',
  plainDescription: 'Mimir remembers documentation it has already fetched so it does not have to download it again every time.',
  keyCode: [
    '// TTL-based caching with automatic Context7 fetch',
    'cache = SDKCache(project_root)',
    'docs = cache.get("stripe", "checkout sessions")  # fetch + cache',
    'docs = cache.get("stripe", "checkout sessions")  # cache hit!',
  ].join('\n'),
  dependencyTraces: [
    { from: 'sdk_cache.py', to: 'config.py', type: 'imports', line: 44 },
    { from: 'mcp_server_llamaindex.py', to: 'sdk_cache.py', type: 'imports', line: 612 },
  ],
};

// ─── Cross-Cutting: Metrics ──────────────────────────────────────────────────

export const featureMetrics = {
  title: 'Cost & Usage Metrics',
  file: 'metrics.py',
  icon: '📊',
  color: '#f59e0b',
  description: 'JSONL-based cost tracking for every query type. Tracks prompt/completion/embedding tokens and calculates real costs per model. Includes traditional cost comparison for savings reporting.',
  plainDescription: 'Mimir tracks how much every search and query costs -- like a receipt for your AI spending.',
  keyCode: [
    'tracker = get_tracker()',
    'metrics = tracker.record_query(',
    '    query_type="rag",',
    '    model="google/gemini-2.0-flash-exp",',
    '    tokens_in=2100,',
    '    tokens_out=245,',
    '    docs_retrieved=5,',
    ')',
    'print(f"Cost: {metrics.cost:.4f}")',
  ].join('\n'),
  dependencyTraces: [
    { from: 'metrics.py', to: 'config.py', type: 'imports', line: 200 },
    { from: 'mcp_server_llamaindex.py', to: 'metrics.py', type: 'imports', line: 98 },
  ],
};

// ─── Full Layer Array ────────────────────────────────────────────────────────

export const architectureLayers: ArchitectureLayer[] = [
  layerUserClient,
  layerOrchestration,
  layerRetrieval,
  layerInfrastructure,
];

// ─── File Dependency Map ─────────────────────────────────────────────────────

export interface FileDep {
  file: string;
  imports: string[];
  importedBy: string[];
}

export const fileDependencyMap: FileDep[] = [
  {
    file: 'config.py (src/mimir/)',
    imports: [],
    importedBy: [
      'indexing.py',
      'knowledge_graph.py (indirect via indexing)',
      'openspace_bridge.py',
      'sdk_cache.py',
      'shared_index.py',
      'metrics.py',
      'watcher.py (indirect)',
      'mcp_server_llamaindex.py',
    ],
  },
  {
    file: 'indexing.py (src/mimir/)',
    imports: ['config.py', 'utils.py'],
    importedBy: [
      'watcher.py',
      'mcp_server_llamaindex.py',
      'knowledge_graph.py (from_index mode)',
    ],
  },
  {
    file: 'knowledge_graph.py (src/mimir/)',
    imports: ['config.py (indirect)', 'utils.py', 'indexing.py (from_index)'],
    importedBy: ['watcher.py', 'mcp_server_llamaindex.py (via CLI)'],
  },
  {
    file: 'openspace_bridge.py (src/mimir/)',
    imports: ['config.py', 'indexing.py (indirect)'],
    importedBy: ['mcp_server_llamaindex.py'],
  },
  {
    file: 'mcp_server_llamaindex.py (root)',
    imports: [
      'config.py',
      'indexing.py',
      'knowledge_graph.py',
      'openspace_bridge.py',
      'sdk_cache.py',
      'shared_index.py',
      'metrics.py',
      'watcher.py',
      'langgraph/workflows/rag.py',
      'langgraph/workflows/knowledge_agent.py',
    ],
    importedBy: [],
  },
  {
    file: 'watcher.py (src/mimir/)',
    imports: ['indexing.py', 'knowledge_graph.py', 'config.py'],
    importedBy: ['mcp_server_llamaindex.py'],
  },
  {
    file: 'shared_index.py (src/mimir/)',
    imports: ['config.py'],
    importedBy: ['mcp_server_llamaindex.py'],
  },
  {
    file: 'sdk_cache.py (src/mimir/)',
    imports: ['config.py'],
    importedBy: ['mcp_server_llamaindex.py'],
  },
  {
    file: 'metrics.py (src/mimir/)',
    imports: ['config.py'],
    importedBy: ['mcp_server_llamaindex.py'],
  },
  {
    file: 'langgraph/workflows/rag.py',
    imports: ['mcp_server_llamaindex.py (calls MCP tools)'],
    importedBy: ['mcp_server_llamaindex.py'],
  },
  {
    file: 'langgraph/workflows/knowledge_agent.py',
    imports: ['mcp_server_llamaindex.py (calls MCP tools)'],
    importedBy: ['mcp_server_llamaindex.py'],
  },
];